"""Recipient grouping, editable templates, and non-sending dry-run output."""

from __future__ import annotations

import html
import json
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping

import pandas as pd


ALLOWED_PLACEHOLDERS: Final[frozenset[str]] = frozenset({
    "athlete_name", "athlete_names", "assessment_date", "assessment_dates", "report_count",
})
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class EmailPlanStatus:
    READY: Final[str] = "READY"
    SKIPPED_NO_EMAIL: Final[str] = "SKIPPED_NO_EMAIL"
    INVALID_EMAIL: Final[str] = "INVALID_EMAIL"
    MISSING_REPORT: Final[str] = "MISSING_REPORT"
    AMBIGUOUS_RECIPIENT: Final[str] = "AMBIGUOUS_RECIPIENT"
    ERROR: Final[str] = "ERROR"


@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    greeting: str
    single_report_body: str
    multiple_report_body: str
    closing: str
    single_report_html: str | None = None
    multiple_report_html: str | None = None


@dataclass(frozen=True)
class EmailPlan:
    recipient: str | None
    normalized_recipient: str | None
    athlete_names: tuple[str, ...]
    assessment_dates: tuple[str, ...]
    attachment_paths: tuple[Path, ...]
    subject: str
    plain_body: str
    html_body: str | None
    status: str
    issues: tuple[str, ...]


def normalize_recipient(value: object) -> tuple[str | None, str | None]:
    """Return clean delivery address and normalized grouping key."""
    if pd.isna(value) or not str(value).strip() or str(value).strip().casefold() == "n/a":
        return None, None
    clean = str(value).strip()
    return clean, clean.casefold()


def is_valid_email(value: str | None) -> bool:
    return bool(value and EMAIL_PATTERN.fullmatch(value))


def load_email_template(path: Path) -> EmailTemplate:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Email template is missing, unreadable, or malformed: {path}") from exc
    required = ("subject", "greeting", "single_report_body", "multiple_report_body", "closing")
    missing = [key for key in required if not isinstance(data.get(key), str)]
    if missing:
        raise ValueError(f"Email template requires text fields: {missing}")
    template = EmailTemplate(*(data[key] for key in required),
                             data.get("single_report_html"), data.get("multiple_report_html"))
    for value in template.__dict__.values():
        if isinstance(value, str):
            _validate_placeholders(value)
    return template


def _validate_placeholders(template: str) -> None:
    try:
        fields = {field for _, field, _, _ in string.Formatter().parse(template) if field}
    except ValueError as exc:
        raise ValueError(f"Invalid email template formatting: {exc}") from exc
    unsupported = fields - ALLOWED_PLACEHOLDERS
    if unsupported:
        raise ValueError(f"Unsupported email template placeholder(s): {sorted(unsupported)}")


def _natural_join(values: list[str]) -> str:
    if len(values) < 2:
        return values[0] if values else ""
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _template_values(names: list[str], dates: list[str]) -> dict[str, object]:
    return {
        "athlete_name": names[0] if len(names) == 1 else _natural_join(names),
        "athlete_names": _natural_join(names),
        "assessment_date": dates[0] if len(set(dates)) == 1 else _natural_join(dates),
        "assessment_dates": _natural_join(list(dict.fromkeys(dates))),
        "report_count": len(names),
    }


def _render_content(template: EmailTemplate, names: list[str], dates: list[str]) -> tuple[str, str, str | None]:
    values = _template_values(names, dates)
    subject = template.subject.format_map(values)
    body_template = template.single_report_body if len(names) == 1 else template.multiple_report_body
    plain = "\n\n".join(part.format_map(values) for part in
                          (template.greeting, body_template, template.closing) if part)
    html_template = template.single_report_html if len(names) == 1 else template.multiple_report_html
    html_body = None
    if html_template:
        # The configured HTML body is intentional markup. Escape only substituted
        # data, while treating shared plain-text fields as text with safe breaks.
        html_values = {key: html.escape(str(value)) for key, value in values.items()}
        rendered_body = html_template.format_map(html_values)
        text_parts = (
            f"<p>{html.escape(template.greeting).replace(chr(10), '<br>')}</p>"
            if template.greeting else "",
            rendered_body,
            f"<p>{html.escape(template.closing).replace(chr(10), '<br>')}</p>"
            if template.closing else "",
        )
        html_body = "".join(text_parts)
    return subject, plain, html_body


def build_email_plans(manifest: pd.DataFrame, template: EmailTemplate) -> list[EmailPlan]:
    """Build plans only from successful manifest rows; never scans filenames."""
    successful = manifest.loc[manifest["generation_status"].eq("success")].copy()
    grouped: dict[str, list[pd.Series]] = {}
    invalid_rows: list[tuple[pd.Series, str, str | None]] = []
    ambiguous_roster_rows: set[object] = set()
    if "roster_row" in successful:
        for roster_row, athlete_rows in successful.groupby("roster_row", dropna=False):
            keys = {normalize_recipient(value)[1] for value in athlete_rows["recipient_email"]}
            keys.discard(None)
            if len(keys) > 1:
                ambiguous_roster_rows.add(roster_row)
    for _, row in successful.iterrows():
        recipient, normalized = normalize_recipient(row.get("recipient_email"))
        if row.get("roster_row") in ambiguous_roster_rows:
            invalid_rows.append((row, EmailPlanStatus.AMBIGUOUS_RECIPIENT, recipient))
        elif recipient is None:
            invalid_rows.append((row, EmailPlanStatus.SKIPPED_NO_EMAIL, None))
        elif not is_valid_email(recipient):
            invalid_rows.append((row, EmailPlanStatus.INVALID_EMAIL, recipient))
        else:
            grouped.setdefault(normalized or "", []).append(row)

    plans: list[EmailPlan] = []
    for row, status, recipient in invalid_rows:
        assessment = pd.to_datetime(row.get("assessment_date"), errors="coerce")
        date_text = "N/A" if pd.isna(assessment) else assessment.strftime("%Y-%m-%d")
        plans.append(EmailPlan(recipient, recipient.casefold() if recipient else None,
            (str(row["athlete_name"]),), (date_text,), (), "", "", None, status,
            ("Recipient email is missing" if status == EmailPlanStatus.SKIPPED_NO_EMAIL else
             "Athlete maps to multiple recipient addresses" if status == EmailPlanStatus.AMBIGUOUS_RECIPIENT
             else "Recipient email syntax is invalid",)))
    for normalized, rows in sorted(grouped.items()):
        names = [str(row["athlete_name"]) for row in rows]
        dates = [pd.to_datetime(row.get("assessment_date"), errors="coerce").strftime("%m/%d/%Y")
                 if not pd.isna(pd.to_datetime(row.get("assessment_date"), errors="coerce")) else "N/A"
                 for row in rows]
        recipient = str(rows[0]["recipient_email"]).strip()
        paths = [Path(str(row["pdf_path"])) for row in rows]
        issues: list[str] = []
        if len(set(paths)) != len(paths):
            issues.append("Duplicate report attachment path maps to multiple manifest rows")
        unique_paths = list(dict.fromkeys(paths))
        missing = [path for path in unique_paths if not path.is_file() or path.stat().st_size == 0]
        if missing:
            issues.extend(f"Missing or empty report: {path}" for path in missing)
        status = (EmailPlanStatus.MISSING_REPORT if missing else
                  EmailPlanStatus.ERROR if issues else EmailPlanStatus.READY)
        try:
            subject, plain, html_body = _render_content(template, names, dates)
        except (KeyError, ValueError) as exc:
            subject, plain, html_body, status = "", "", None, EmailPlanStatus.ERROR
            issues.append(f"Template rendering failed: {exc}")
        iso_dates = tuple(pd.to_datetime(row.get("assessment_date"), errors="coerce").strftime("%Y-%m-%d")
                          if not pd.isna(pd.to_datetime(row.get("assessment_date"), errors="coerce"))
                          else "N/A" for row in rows)
        plans.append(EmailPlan(recipient, normalized, tuple(names), iso_dates, tuple(unique_paths),
                               subject, plain, html_body, status, tuple(issues)))
    return plans


def write_dry_run_outputs(plans: list[EmailPlan], output_directory: Path) -> dict[str, Path]:
    """Persist plan/audit previews without authenticating or sending."""
    output = Path(output_directory)
    previews = output / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    records = []
    for index, plan in enumerate(plans, 1):
        preview_path = previews / f"email_group_{index:03d}.txt"
        preview_path.write_text(
            f"DRY RUN - NO EMAIL SENT\n\nTo: {plan.recipient or 'N/A'}\n"
            f"Subject: {plan.subject or 'N/A'}\nStatus: {plan.status}\n\n{plan.plain_body}\n",
            encoding="utf-8",
        )
        records.append({
            "recipient": plan.recipient, "athlete_count": len(plan.athlete_names),
            "athlete_names": " | ".join(plan.athlete_names),
            "attachment_count": len(plan.attachment_paths),
            "attachment_paths": " | ".join(str(path) for path in plan.attachment_paths),
            "subject": plan.subject, "status": plan.status, "issues": " | ".join(plan.issues),
            "preview_path": str(preview_path),
        })
    csv_path, markdown_path = output / "dry_run_email_plan.csv", output / "dry_run_email_plan.md"
    frame = pd.DataFrame(records)
    frame.to_csv(csv_path, index=False)
    lines = ["# Email dry-run plan", "", "No email was authenticated or sent.", ""]
    for index, plan in enumerate(plans, 1):
        lines.extend((f"## Group {index:03d}: {plan.status}", "",
                      f"- Recipient: {plan.recipient or 'N/A'}",
                      f"- Athletes: {', '.join(plan.athlete_names)}",
                      f"- Attachments: {len(plan.attachment_paths)}",
                      f"- Subject: {plan.subject or 'N/A'}",
                      f"- Issues: {', '.join(plan.issues) or 'None'}", ""))
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path, "previews": previews}


def dry_run_email_planning(manifest: pd.DataFrame, template: EmailTemplate,
                           output_directory: Path) -> tuple[list[EmailPlan], dict[str, Path]]:
    """Explicitly non-sending entry point: no Gmail service is accepted or invoked."""
    plans = build_email_plans(manifest, template)
    return plans, write_dry_run_outputs(plans, output_directory)
