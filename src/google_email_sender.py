"""Safe Gmail MIME construction and explicitly invoked delivery engine."""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import replace
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Final, Iterable

from .email_delivery import DeliveryLog, delivery_fingerprint, delivery_record
from .email_planner import EmailPlan, EmailPlanStatus, is_valid_email


TRANSIENT_HTTP_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


class EmailSendError(RuntimeError):
    pass


def validate_sendable_plan(plan: EmailPlan, max_total_attachment_bytes: int) -> tuple[bool, str]:
    if plan.status != EmailPlanStatus.READY:
        return False, f"Plan status is {plan.status}, not READY"
    if not is_valid_email(plan.recipient):
        return False, "Recipient email is missing or invalid"
    if not plan.attachment_paths:
        return False, "No report attachments are present"
    if not (len(plan.athlete_names) == len(plan.assessment_dates) == len(plan.attachment_paths)):
        return False, "Athlete, assessment-date, and attachment counts do not match"
    if len(set(plan.attachment_paths)) != len(plan.attachment_paths):
        return False, "Duplicate attachment path"
    total = 0
    for path in plan.attachment_paths:
        if path.suffix.casefold() != ".pdf":
            return False, f"Attachment is not a PDF: {path.name}"
        if not path.is_file() or path.stat().st_size == 0:
            return False, f"Attachment is missing or empty: {path.name}"
        total += path.stat().st_size
    if total > max_total_attachment_bytes:
        return False, (f"Total attachment size {total} bytes exceeds configured conservative "
                       f"maximum {max_total_attachment_bytes} bytes")
    return True, ""


def build_mime_message(plan: EmailPlan) -> EmailMessage:
    """Construct a To-addressed message; From is intentionally left to authenticated Gmail."""
    message = EmailMessage()
    message["To"] = plan.recipient
    message["Subject"] = plan.subject
    message.set_content(plan.plain_body)
    if plan.html_body:
        message.add_alternative(plan.html_body, subtype="html")
    for path in plan.attachment_paths:
        message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf",
                               filename=path.name)
    return message


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "resp", None)
    value = getattr(response, "status", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def gmail_send_message(
    service, message: EmailMessage, *, max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Send once with bounded retries only for recognized transient HTTP failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    for attempt in range(1, max_attempts + 1):
        try:
            result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            if _http_status(exc) not in TRANSIENT_HTTP_STATUSES or attempt == max_attempts:
                raise
            sleep(float(2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def new_batch_id() -> str:
    from datetime import datetime, timezone
    return f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"


def send_live_batch(
    service, plans: Iterable[EmailPlan], delivery_log: DeliveryLog, *,
    max_total_attachment_bytes: int, max_attempts: int = 3, force_resend: bool = False,
    batch_id: str | None = None, sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    """Send validated plans and persist every outcome immediately."""
    run_id = batch_id or new_batch_id()
    successful = delivery_log.successful_fingerprints()
    results: list[dict[str, object]] = []
    for plan in plans:
        valid, reason = validate_sendable_plan(plan, max_total_attachment_bytes)
        if not valid:
            record = delivery_record(plan, batch_id=run_id, mode="LIVE", status="BLOCKED",
                                     error_code="PLAN_BLOCKED", error_message=reason,
                                     force_resend=force_resend)
            delivery_log.append(record); results.append(record)
            continue
        fingerprint = delivery_fingerprint(plan)
        if fingerprint in successful and not force_resend:
            record = delivery_record(plan, batch_id=run_id, mode="LIVE",
                                     status="SKIPPED_DUPLICATE", fingerprint=fingerprint)
            delivery_log.append(record); results.append(record)
            continue
        try:
            response = gmail_send_message(service, build_mime_message(plan),
                                          max_attempts=max_attempts, sleep=sleep)
            record = delivery_record(plan, batch_id=run_id, mode="LIVE", status="SENT",
                                     fingerprint=fingerprint,
                                     gmail_message_id=str(response.get("id", "")),
                                     force_resend=force_resend)
            successful.add(fingerprint)
        except Exception as exc:
            record = delivery_record(plan, batch_id=run_id, mode="LIVE", status="FAILED",
                                     fingerprint=fingerprint,
                                     error_code=type(exc).__name__, error_message=str(exc),
                                     force_resend=force_resend)
        delivery_log.append(record); results.append(record)
    return results


def send_one_test_message(
    service, plans: Iterable[EmailPlan], test_recipient: str, delivery_log: DeliveryLog, *,
    max_total_attachment_bytes: int, max_attempts: int = 3,
    batch_id: str | None = None, sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Send exactly one plan only to an explicitly configured safe test recipient."""
    if not is_valid_email(test_recipient):
        raise EmailSendError("A valid explicit test_recipient is required; no fallback is allowed")
    original = next((plan for plan in plans if plan.status == EmailPlanStatus.READY), None)
    if original is None:
        raise EmailSendError("No READY email plan is available for a controlled test send")
    test_plan = replace(
        original, recipient=test_recipient.strip(), normalized_recipient=test_recipient.strip().casefold(),
        subject=f"[TEST] {original.subject}",
        plain_body=("TEST MESSAGE: This was redirected to a controlled test recipient.\n\n" +
                    original.plain_body),
        html_body=("<p><strong>TEST MESSAGE:</strong> Redirected to a controlled test recipient.</p>" +
                   original.html_body) if original.html_body else None,
    )
    valid, reason = validate_sendable_plan(test_plan, max_total_attachment_bytes)
    run_id = batch_id or new_batch_id()
    if not valid:
        record = delivery_record(test_plan, batch_id=run_id, mode="TEST", status="BLOCKED",
                                 error_code="PLAN_BLOCKED", error_message=reason,
                                 original_recipient=original.recipient or "")
        delivery_log.append(record)
        return record
    try:
        response = gmail_send_message(service, build_mime_message(test_plan),
                                      max_attempts=max_attempts, sleep=sleep)
        record = delivery_record(test_plan, batch_id=run_id, mode="TEST", status="TEST_SENT",
                                 fingerprint=delivery_fingerprint(original),
                                 gmail_message_id=str(response.get("id", "")),
                                 original_recipient=original.recipient or "")
    except Exception as exc:
        record = delivery_record(test_plan, batch_id=run_id, mode="TEST", status="FAILED",
                                 fingerprint=delivery_fingerprint(original),
                                 error_code=type(exc).__name__, error_message=str(exc),
                                 original_recipient=original.recipient or "")
    delivery_log.append(record)
    return record
