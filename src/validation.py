"""Structured, non-destructive Phase 1 validation and eligibility rules."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from .matcher import MatchStatus, build_canonical_roster
from .drill_normalizer import DEFAULT_DRILL_ALIASES, normalize_drill_name
from .normalizer import normalize_email, normalize_name
from .raw_schema import HARDWARE_RAW_SCHEMA, SOURCE_ROW_COLUMN
from .time_parser import parse_duration_to_seconds


class Severity:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


@dataclass
class ValidationIssue:
    severity: str
    category: str
    source: str
    message: str
    source_row: object = None
    athlete_name: object = None
    roster_row: object = None
    details: dict[str, object] = field(default_factory=dict)
    blocks_report: bool = False
    blocks_run: bool = False
    issue_id: str = ""

    def record(self) -> dict[str, object]:
        record = asdict(self)
        record["details"] = json.dumps(self.details, ensure_ascii=False, default=str)
        return record


KNOWN_DRILLS = set(DEFAULT_DRILL_ALIASES)
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9_-]+")


def safe_report_filename(full_name: object) -> str:
    """Derive a stable, filesystem-safe future PDF name."""
    text = "" if pd.isna(full_name) else unicodedata.normalize("NFKD", str(full_name))
    text = text.encode("ascii", "ignore").decode("ascii")
    stem = _UNSAFE_FILENAME.sub("_", text.strip()).strip("_-") or "Unknown_Athlete"
    return f"{stem}_Report.pdf"


def detect_filename_collisions(canonical: pd.DataFrame) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for _, row in canonical.iterrows():
        key = safe_report_filename(row["full_name"]).casefold()
        grouped.setdefault(key, []).append(int(row["roster_row"]))
    return {name: rows for name, rows in grouped.items() if len(set(rows)) > 1}


def validate_identity(hardware_matches: pd.DataFrame, juggling_matches: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    blocking = {
        MatchStatus.UNMATCHED: "unmatched_hardware_identity",
        MatchStatus.AMBIGUOUS_NAME: "ambiguous_hardware_identity",
        MatchStatus.NAME_EMAIL_CONFLICT: "name_email_conflict",
        MatchStatus.INVALID_IDENTITY: "invalid_hardware_identity",
    }
    for _, row in hardware_matches.iterrows():
        status = row["status"]
        if status in blocking:
            issues.append(ValidationIssue(Severity.BLOCKING, blocking[status], "hardware",
                str(row["reason"]), row["source_row"], row["source_name"], blocks_report=True,
                details={"source_email": row["source_email"]}))
        elif status == MatchStatus.UNIQUE_NAME_FALLBACK and row["normalized_source_email"] != normalize_email(row["matched_email"]):
            issues.append(ValidationIssue(Severity.WARNING, "hardware_email_mismatch", "hardware",
                "Unique-name fallback accepted; source email differs from authoritative roster email",
                row["source_row"], row["source_name"], row["matched_roster_row"],
                {"source_email": row["source_email"], "roster_email": row["matched_email"]}))
    for _, row in juggling_matches.iterrows():
        if row["status"] in {MatchStatus.UNMATCHED, MatchStatus.AMBIGUOUS_NAME, MatchStatus.INVALID_IDENTITY}:
            category = "unmatched_juggling_identity" if row["status"] == MatchStatus.UNMATCHED else "ambiguous_juggling_identity"
            issues.append(ValidationIssue(Severity.WARNING, category, "juggling", str(row["reason"]),
                row["source_row"], row["source_name"], blocks_report=False))
    return issues


def validate_roster(roster: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    canonical = build_canonical_roster(roster)
    raw_duplicates = canonical["full_name"].duplicated(keep=False)
    normalized_duplicates = canonical["normalized_name"].notna() & canonical["normalized_name"].duplicated(keep=False)
    for _, row in canonical.loc[raw_duplicates].iterrows():
        issues.append(ValidationIssue(Severity.ERROR, "duplicate_full_name", "roster",
            "Full name appears on multiple roster rows", row["roster_row"], row["full_name"], row["roster_row"], blocks_report=True))
    for _, row in canonical.loc[normalized_duplicates].iterrows():
        issues.append(ValidationIssue(Severity.ERROR, "duplicate_normalized_name", "roster",
            "Normalized name appears on multiple roster rows", row["roster_row"], row["full_name"], row["roster_row"], blocks_report=True))
    for index, row in roster.iterrows():
        roster_row = row[SOURCE_ROW_COLUMN]
        name = canonical.loc[index, "full_name"]
        if pd.isna(row["Birthday"]):
            issues.append(ValidationIssue(Severity.WARNING, "missing_birthday", "roster", "Birthday is missing",
                roster_row, name, roster_row))
        elif pd.isna(row["_birthday_parsed"]):
            issues.append(ValidationIssue(Severity.WARNING, "invalid_birthday", "roster", "Birthday could not be parsed",
                roster_row, name, roster_row, {"value": row["Birthday"]}))
        if pd.isna(row["Age Group"]) or not str(row["Age Group"]).strip():
            issues.append(ValidationIssue(Severity.BLOCKING, "missing_age_group", "roster",
                "Age group is required for report cohort eligibility", roster_row, name, roster_row, blocks_report=True))
        if pd.isna(row["Team Name"]) or not str(row["Team Name"]).strip():
            issues.append(ValidationIssue(Severity.WARNING, "missing_team", "roster", "Authoritative roster team is missing",
                roster_row, name, roster_row))
        elif str(row["Team Name"]) != str(row["Team Name"]).strip() or str(row["Team Name"]).rstrip().endswith("-"):
            issues.append(ValidationIssue(Severity.WARNING, "suspicious_team", "roster",
                "Team name contains suspicious trailing whitespace or punctuation", roster_row, name, roster_row,
                {"value": row["Team Name"]}))
        if pd.isna(row["Parent Contact"]) or not str(row["Parent Contact"]).strip():
            issues.append(ValidationIssue(Severity.WARNING, "missing_parent_contact", "roster",
                "Authoritative parent/contact email is missing", roster_row, name, roster_row))
    return issues


def validate_hardware(hardware: pd.DataFrame, hardware_matches: pd.DataFrame,
                      known_drills: set[str] | None = None,
                      drill_aliases: dict[str, str] | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = HARDWARE_RAW_SCHEMA
    aliases = (DEFAULT_DRILL_ALIASES if drill_aliases is None else drill_aliases)
    known = set(aliases) if known_drills is None else known_drills
    parsed_dates: dict[str, set[object]] = {}
    first_rows: dict[str, object] = {}
    for _, row in hardware.iterrows():
        source_row = row[SOURCE_ROW_COLUMN]
        name, email = row[schema.athlete_name_index], row[schema.athlete_email_index]
        norm_name = normalize_name(name)
        if norm_name is None:
            issues.append(ValidationIssue(Severity.BLOCKING, "missing_hardware_name", "hardware",
                "Hardware athlete name is missing", source_row, name, blocks_report=True))
        if normalize_email(email) is None:
            issues.append(ValidationIssue(Severity.WARNING, "missing_hardware_email", "hardware",
                "Hardware athlete email is missing", source_row, name))
        drill = row[schema.drill_name_index]
        if pd.isna(drill) or str(drill).strip() not in known or normalize_drill_name(drill, aliases) is None:
            issues.append(ValidationIssue(Severity.WARNING, "unknown_drill", "hardware",
                "Raw drill name is missing or unsupported", source_row, name, details={"value": drill}))
        timestamp = row[schema.assessment_timestamp_index]
        parsed = pd.to_datetime(timestamp, format="%B %d, %Y - %I:%M %p", errors="coerce")
        if pd.isna(parsed):
            issues.append(ValidationIssue(Severity.WARNING, "malformed_assessment_timestamp", "hardware",
                "Assessment timestamp could not be parsed", source_row, name, details={"value": timestamp}))
        elif norm_name:
            parsed_dates.setdefault(norm_name, set()).add(parsed.date())
            first_rows.setdefault(norm_name, source_row)
        for column in schema.timing_value_indexes:
            value = row[column]
            if not pd.isna(value) and parse_duration_to_seconds(value) is None:
                issues.append(ValidationIssue(Severity.WARNING, "malformed_duration", "hardware",
                    "Timing-like value has an unsupported format", source_row, name,
                    details={"column_index": column, "value": value}))
    match_by_name = hardware_matches.drop_duplicates("normalized_source_name").set_index("normalized_source_name")
    for norm_name, dates in parsed_dates.items():
        if len(dates) > 1:
            match = match_by_name.loc[norm_name] if norm_name in match_by_name.index else None
            issues.append(ValidationIssue(Severity.WARNING, "multiple_assessment_dates", "hardware",
                "Athlete has hardware records on multiple assessment dates", first_rows[norm_name],
                match["source_name"] if match is not None else norm_name,
                match["matched_roster_row"] if match is not None else None,
                {"dates": sorted(str(value) for value in dates)}))
    return issues


def validate_juggling(juggling: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, row in juggling.iterrows():
        name = " ".join(str(row[c]).strip() for c in ("First Name", "Last Name") if not pd.isna(row[c])).strip()
        missing = [field for field in ("Dominant", "Non-Dominant", "Thighs") if pd.isna(row[field])]
        for field_name in missing:
            issues.append(ValidationIssue(Severity.WARNING, f"missing_juggling_{field_name.lower().replace('-', '_')}",
                "juggling", f"Juggling {field_name} score is missing", row[SOURCE_ROW_COLUMN], name))
        if len(missing) == 3:
            issues.append(ValidationIssue(Severity.WARNING, "missing_all_juggling", "juggling",
                "All three juggling scores are missing", row[SOURCE_ROW_COLUMN], name))
    return issues


def validate_logos(config: dict[str, object], project_root: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    logos_dir = Path(project_root) / str(config.get("paths", {}).get("logos", "logos"))  # type: ignore[union-attr]
    defaults = config.get("logo_defaults", {})
    default_logo = defaults.get("team_logo") if isinstance(defaults, dict) else None
    references: list[tuple[str, object]] = [("default", default_logo)] if default_logo else []
    mappings = config.get("team_logos", {})
    if isinstance(mappings, dict):
        references.extend((str(team), filename) for team, filename in mappings.items())
    for team, filename in references:
        if not filename or not (logos_dir / str(filename)).is_file():
            issues.append(ValidationIssue(Severity.WARNING, "missing_logo_file", "config",
                "Configured logo file does not exist", details={"team": team, "file": filename}))
    return issues


def validate_filenames(canonical: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_row = canonical.set_index("roster_row")
    for filename, rows in detect_filename_collisions(canonical).items():
        for roster_row in rows:
            issues.append(ValidationIssue(Severity.ERROR, "filename_collision", "roster",
                "Multiple roster athletes map to the same future report filename", roster_row,
                by_row.loc[roster_row, "full_name"], roster_row,
                {"filename": filename, "colliding_roster_rows": rows}, blocks_report=True))
    return issues


def assign_issue_ids(issues: Iterable[ValidationIssue]) -> list[ValidationIssue]:
    result = list(issues)
    for index, issue in enumerate(result, 1):
        issue.issue_id = f"VAL-{index:06d}"
    return result


def issues_frame(issues: Iterable[ValidationIssue]) -> pd.DataFrame:
    columns = ["issue_id", "severity", "category", "source", "source_row", "athlete_name",
               "roster_row", "message", "details", "blocks_report", "blocks_run"]
    return pd.DataFrame.from_records([issue.record() for issue in issues], columns=columns)


def is_athlete_report_eligible(roster_row: object, issues: Iterable[ValidationIssue]) -> tuple[bool, list[str]]:
    reasons = [issue.message for issue in issues if issue.blocks_report and issue.roster_row == roster_row]
    return not reasons, reasons


def write_validation_outputs(issues: list[ValidationIssue], output_directory: Path) -> tuple[Path, Path]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    details_path = output / "validation_details.csv"
    summary_path = output / "validation_summary.csv"
    details = issues_frame(issues)
    details.to_csv(details_path, index=False)
    if details.empty:
        summary = pd.DataFrame(columns=["severity", "category", "issue_count", "blocking_report_count", "blocking_run_count"])
    else:
        summary = details.groupby(["severity", "category"], dropna=False).agg(
            issue_count=("issue_id", "count"), blocking_report_count=("blocks_report", "sum"),
            blocking_run_count=("blocks_run", "sum")).reset_index()
    summary.to_csv(summary_path, index=False)
    return summary_path, details_path
