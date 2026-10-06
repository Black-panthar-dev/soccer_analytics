"""Persistent delivery fingerprints and incrementally written delivery audit log."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Iterable, Mapping

from .email_planner import EmailPlan


DELIVERY_LOG_COLUMNS: Final[tuple[str, ...]] = (
    "batch_id", "timestamp", "recipient", "original_recipient", "athlete_names",
    "assessment_dates", "attachment_names", "attachment_count", "delivery_fingerprint",
    "mode", "status", "gmail_message_id", "error_code", "error_message", "force_resend",
)
_SECRET_PATTERN = re.compile(
    r"(?i)(access_token|refresh_token|client_secret|id_token)(\s*[\"']?\s*[:=]\s*[\"']?)([^\s,}\"']+)"
)


def redact_secrets(value: object) -> str:
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", str(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def delivery_fingerprint(plan: EmailPlan) -> str:
    """Hash delivery identity/content without incorporating machine-specific paths or wording."""
    reports = [{
        "athlete": athlete.casefold().strip(),
        "assessment_date": date,
        "pdf_sha256": sha256_file(path),
    } for athlete, date, path in zip(plan.athlete_names, plan.assessment_dates,
                                     plan.attachment_paths)]
    reports.sort(key=lambda item: (item["athlete"], item["assessment_date"], item["pdf_sha256"]))
    payload = {"recipient": (plan.normalized_recipient or "").casefold(), "reports": reports}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DeliveryLog:
    """CSV ledger that flushes each result before the next message is attempted."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def successful_fingerprints(self) -> set[str]:
        if not self.path.is_file():
            return set()
        with self.path.open("r", newline="", encoding="utf-8") as source:
            return {row["delivery_fingerprint"] for row in csv.DictReader(source)
                    if row.get("status") == "SENT" and row.get("delivery_fingerprint")}

    def failed_fingerprints(self) -> set[str]:
        if not self.path.is_file():
            return set()
        with self.path.open("r", newline="", encoding="utf-8") as source:
            return {row["delivery_fingerprint"] for row in csv.DictReader(source)
                    if row.get("status") == "FAILED" and row.get("delivery_fingerprint")}

    def append(self, record: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.is_file() and self.path.stat().st_size > 0
        safe = {column: record.get(column, "") for column in DELIVERY_LOG_COLUMNS}
        with self.path.open("a", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=DELIVERY_LOG_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow(safe)
            target.flush()


def delivery_record(
    plan: EmailPlan, *, batch_id: str, mode: str, status: str,
    fingerprint: str = "", gmail_message_id: str = "", error_code: str = "",
    error_message: str = "", original_recipient: str = "", force_resend: bool = False,
) -> dict[str, object]:
    return {
        "batch_id": batch_id, "timestamp": datetime.now(timezone.utc).isoformat(),
        "recipient": plan.recipient or "", "original_recipient": original_recipient,
        "athlete_names": " | ".join(plan.athlete_names),
        "assessment_dates": " | ".join(plan.assessment_dates),
        "attachment_names": " | ".join(path.name for path in plan.attachment_paths),
        "attachment_count": len(plan.attachment_paths), "delivery_fingerprint": fingerprint,
        "mode": mode, "status": status, "gmail_message_id": gmail_message_id,
        "error_code": error_code, "error_message": redact_secrets(error_message),
        "force_resend": str(bool(force_resend)).lower(),
    }
