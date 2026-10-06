from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.email_delivery import DeliveryLog, delivery_fingerprint, delivery_record
from src.email_planner import EmailPlan, EmailPlanStatus
from src.email_send_cli import main as cli_main
from src.google_email_sender import (
    EmailSendError, build_mime_message, gmail_send_message, send_live_batch,
    send_one_test_message, validate_sendable_plan,
)


def pdf(path: Path, content: bytes = b"%PDF-1.4 fixture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def fresh_log(path: Path) -> DeliveryLog:
    path.unlink(missing_ok=True)
    return DeliveryLog(path)


def plan(tmp: Path, *, recipient: str = "parent@example.com", count: int = 1,
         html: bool = True) -> EmailPlan:
    names = tuple(f"Athlete {index}" for index in range(1, count + 1))
    paths = tuple(pdf(tmp / f"report{index}.pdf", f"%PDF report {index}".encode())
                  for index in range(1, count + 1))
    return EmailPlan(recipient, recipient.casefold(), names,
                     tuple("2026-08-15" for _ in names), paths, "Assessment Report",
                     "Plain assessment body", "<p>HTML assessment body</p>" if html else None,
                     EmailPlanStatus.READY, ())


class FakeExecute:
    def __init__(self, service): self.service = service
    def execute(self):
        self.service.calls += 1
        if self.service.errors:
            raise self.service.errors.pop(0)
        return {"id": f"gmail-{self.service.calls}"}


class FakeSend:
    def __init__(self, service): self.service = service
    def send(self, **kwargs):
        self.service.requests.append(kwargs)
        return FakeExecute(self.service)


class FakeUsers:
    def __init__(self, service): self.service = service
    def messages(self): return FakeSend(self.service)


class FakeService:
    def __init__(self, errors=None):
        self.errors = list(errors or [])
        self.calls = 0
        self.requests = []
    def users(self): return FakeUsers(self)


class HttpFailure(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.resp = type("Response", (), {"status": status})()


def decoded_message(service: FakeService):
    raw = service.requests[-1]["body"]["raw"]
    return BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))


def test_one_and_multiple_attachment_mime_messages(test_workspace: Path) -> None:
    one = build_mime_message(plan(test_workspace / "one"))
    many = build_mime_message(plan(test_workspace / "many", count=3))
    assert len(list(one.iter_attachments())) == 1
    assert len(list(many.iter_attachments())) == 3
    assert all(item.get_content_type() == "application/pdf" for item in many.iter_attachments())


def test_plain_html_and_sender_not_spoofed(test_workspace: Path) -> None:
    message = build_mime_message(plan(test_workspace))
    assert message["From"] is None
    bodies = {part.get_content_type(): part.get_content() for part in message.walk()
              if part.get_content_type() in {"text/plain", "text/html"}}
    assert "Plain assessment body" in bodies["text/plain"]
    assert "HTML assessment body" in bodies["text/html"]


def test_test_send_requires_recipient_rewrites_and_sends_exactly_one(test_workspace: Path) -> None:
    service, log = FakeService(), fresh_log(test_workspace / "delivery.csv")
    with pytest.raises(EmailSendError, match="test_recipient"):
        send_one_test_message(service, [plan(test_workspace / "missing")], "", log,
                              max_total_attachment_bytes=1_000_000)
    result = send_one_test_message(service, [plan(test_workspace / "valid")],
        "developer@example.com", log, max_total_attachment_bytes=1_000_000)
    message = decoded_message(service)
    assert service.calls == 1 and result["status"] == "TEST_SENT"
    assert message["To"] == "developer@example.com"
    assert message["Subject"].startswith("[TEST]")
    assert "parent@example.com" not in message.get_body(preferencelist=("plain",)).get_content()
    assert result["original_recipient"] == "parent@example.com"


def test_fingerprint_deterministic_and_path_independent(test_workspace: Path) -> None:
    first = plan(test_workspace / "machine_a", count=2)
    second = plan(test_workspace / "machine_b", count=2)
    assert delivery_fingerprint(first) == delivery_fingerprint(first)
    assert delivery_fingerprint(first) == delivery_fingerprint(second)


def test_successful_duplicate_skipped_and_message_id_logged(test_workspace: Path) -> None:
    service, item = FakeService(), plan(test_workspace / "reports")
    log = fresh_log(test_workspace / "delivery.csv")
    first = send_live_batch(service, [item], log, max_total_attachment_bytes=1_000_000,
                            batch_id="batch-one")
    second = send_live_batch(service, [item], log, max_total_attachment_bytes=1_000_000,
                             batch_id="batch-two")
    assert first[0]["status"] == "SENT" and first[0]["gmail_message_id"] == "gmail-1"
    assert second[0]["status"] == "SKIPPED_DUPLICATE"
    assert service.calls == 1


def test_failed_send_retries_on_next_batch(test_workspace: Path) -> None:
    item, log = plan(test_workspace / "reports"), fresh_log(test_workspace / "delivery.csv")
    failed = send_live_batch(FakeService([HttpFailure(400)]), [item], log,
                             max_total_attachment_bytes=1_000_000)
    successful_service = FakeService()
    retried = send_live_batch(successful_service, [item], log, max_total_attachment_bytes=1_000_000)
    assert failed[0]["status"] == "FAILED"
    assert retried[0]["status"] == "SENT" and successful_service.calls == 1


def test_partial_batch_rerun_skips_prior_success(test_workspace: Path) -> None:
    first = plan(test_workspace / "first", recipient="one@example.com")
    second = plan(test_workspace / "second", recipient="two@example.com")
    log = fresh_log(test_workspace / "delivery.csv")
    send_live_batch(FakeService(), [first], log, max_total_attachment_bytes=1_000_000)
    service = FakeService()
    results = send_live_batch(service, [first, second], log, max_total_attachment_bytes=1_000_000)
    assert [result["status"] for result in results] == ["SKIPPED_DUPLICATE", "SENT"]
    assert service.calls == 1


def test_force_resend_is_explicit_and_logged(test_workspace: Path) -> None:
    item, log, service = plan(test_workspace / "reports"), fresh_log(test_workspace / "delivery.csv"), FakeService()
    send_live_batch(service, [item], log, max_total_attachment_bytes=1_000_000)
    result = send_live_batch(service, [item], log, max_total_attachment_bytes=1_000_000,
                             force_resend=True)[0]
    assert result["status"] == "SENT" and result["force_resend"] == "true"
    assert service.calls == 2


def test_shared_parent_remains_one_gmail_message(test_workspace: Path) -> None:
    service = FakeService()
    item = plan(test_workspace / "siblings", count=2)
    send_live_batch(service, [item], fresh_log(test_workspace / "delivery.csv"),
                    max_total_attachment_bytes=1_000_000)
    assert service.calls == 1
    assert len(list(decoded_message(service).iter_attachments())) == 2


def test_transient_retry_is_bounded_and_permanent_not_retried(test_workspace: Path) -> None:
    message = build_mime_message(plan(test_workspace))
    transient = FakeService([HttpFailure(503), HttpFailure(503), HttpFailure(503)])
    with pytest.raises(HttpFailure):
        gmail_send_message(transient, message, max_attempts=3, sleep=lambda _: None)
    assert transient.calls == 3
    permanent = FakeService([HttpFailure(400)])
    with pytest.raises(HttpFailure):
        gmail_send_message(permanent, message, max_attempts=3, sleep=lambda _: None)
    assert permanent.calls == 1


def test_oversized_and_missing_attachments_are_blocked(test_workspace: Path) -> None:
    oversized = plan(test_workspace / "large")
    valid, reason = validate_sendable_plan(oversized, 1)
    assert not valid and "exceeds" in reason
    missing = plan(test_workspace / "missing")
    missing.attachment_paths[0].unlink()
    valid, reason = validate_sendable_plan(missing, 1_000_000)
    assert not valid and "missing" in reason


def test_cli_no_mode_and_cancelled_confirmation_never_authenticate(
    test_workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = Mock(side_effect=AssertionError("must not authenticate"))
    monkeypatch.setattr("src.email_send_cli.get_gmail_service", auth)
    assert cli_main(["--project-root", str(test_workspace)]) == 0
    monkeypatch.setattr("src.email_send_cli._load_settings", lambda _: {
        "live_send_enabled": True, "max_total_attachment_bytes": 1_000_000,
        "google_credentials_path": "credentials.json", "google_token_path": "token.json"})
    monkeypatch.setattr("src.email_send_cli._load_plans", lambda _: [plan(test_workspace / "reports")])
    assert cli_main(["--live-send", "--project-root", str(test_workspace)],
                    input_func=lambda _: "y") == 2
    auth.assert_not_called()


def test_cli_exact_confirmation_is_required_and_allows_explicit_send(
    test_workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    item, service = plan(test_workspace / "reports"), FakeService()
    delivery_path = test_workspace / "output/phase2/email/delivery_log.csv"
    delivery_path.unlink(missing_ok=True)
    monkeypatch.setattr("src.email_send_cli._load_settings", lambda _: {
        "live_send_enabled": True, "max_total_attachment_bytes": 1_000_000,
        "max_transient_attempts": 3, "google_credentials_path": "credentials.json",
        "google_token_path": "token.json"})
    monkeypatch.setattr("src.email_send_cli._load_plans", lambda _: [item])
    monkeypatch.setattr("src.email_send_cli.get_gmail_service", lambda *_: service)
    result = cli_main(["--live-send", "--project-root", str(test_workspace)],
                      input_func=lambda _: "SEND 1 EMAILS")
    assert result == 0 and service.calls == 1


def test_delivery_errors_redact_credential_tokens(test_workspace: Path) -> None:
    item = plan(test_workspace / "reports")
    record = delivery_record(item, batch_id="batch", mode="LIVE", status="FAILED",
                             error_message="client_secret=verysecret refresh_token: tokenvalue")
    assert "verysecret" not in record["error_message"]
    assert "tokenvalue" not in record["error_message"]
    assert record["error_message"].count("[REDACTED]") == 2


def test_force_resend_requires_live_flag() -> None:
    with pytest.raises(SystemExit):
        cli_main(["--force-resend"])


def _many_plans(test_workspace: Path, count: int = 207) -> list[EmailPlan]:
    return [plan(test_workspace / f"group_{index:03d}",
                 recipient=f"parent{index}@example.com") for index in range(count)]


def test_207_group_interruption_after_50_skips_successes_on_restart(test_workspace: Path) -> None:
    plans = _many_plans(test_workspace)
    log = fresh_log(test_workspace / "delivery.csv")
    for item in plans[:50]:
        log.append(delivery_record(item, batch_id="interrupted", mode="LIVE", status="SENT",
                                   fingerprint=delivery_fingerprint(item), gmail_message_id="mock-id"))
    service = FakeService()
    results = send_live_batch(service, plans, log, max_total_attachment_bytes=1_000_000,
                              batch_id="restart")
    assert sum(result["status"] == "SKIPPED_DUPLICATE" for result in results) == 50
    assert sum(result["status"] == "SENT" for result in results) == 157
    assert service.calls == 157


def test_207_group_failed_item_remains_retryable_after_interruption(test_workspace: Path) -> None:
    plans = _many_plans(test_workspace)
    log = fresh_log(test_workspace / "delivery.csv")
    for item in plans[:40]:
        log.append(delivery_record(item, batch_id="interrupted", mode="LIVE", status="SENT",
                                   fingerprint=delivery_fingerprint(item), gmail_message_id="mock-id"))
    failed = plans[40]
    log.append(delivery_record(failed, batch_id="interrupted", mode="LIVE", status="FAILED",
                               fingerprint=delivery_fingerprint(failed), error_code="MockFailure",
                               error_message="safe mock error"))
    service = FakeService()
    results = send_live_batch(service, plans, log, max_total_attachment_bytes=1_000_000,
                              batch_id="restart")
    assert sum(result["status"] == "SKIPPED_DUPLICATE" for result in results) == 40
    assert sum(result["status"] == "SENT" for result in results) == 167
    assert results[40]["status"] == "SENT"
    assert service.calls == 167


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_each_transient_gmail_status_uses_bounded_retry(test_workspace: Path, status: int) -> None:
    service = FakeService([HttpFailure(status), HttpFailure(status)])
    result = gmail_send_message(service, build_mime_message(plan(test_workspace)),
                                max_attempts=3, sleep=lambda _: None)
    assert result["id"] == "gmail-3" and service.calls == 3


@pytest.mark.parametrize("status", [400, 401, 403])
def test_permanent_and_auth_gmail_statuses_are_not_retried(test_workspace: Path, status: int) -> None:
    service = FakeService([HttpFailure(status)])
    with pytest.raises(HttpFailure):
        gmail_send_message(service, build_mime_message(plan(test_workspace)),
                           max_attempts=3, sleep=lambda _: None)
    assert service.calls == 1
