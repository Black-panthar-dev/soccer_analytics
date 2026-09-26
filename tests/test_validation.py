from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.matcher import MatchStatus
from src.raw_schema import SOURCE_ROW_COLUMN
from src.validation import (
    ValidationIssue, assign_issue_ids, detect_filename_collisions, is_athlete_report_eligible,
    safe_report_filename, validate_filenames, validate_hardware, validate_identity,
    validate_juggling, validate_logos, validate_roster, write_validation_outputs,
)


def match(status: str, source_email: str = "a@x.com", matched_email: str = "a@x.com") -> pd.DataFrame:
    return pd.DataFrame([{"source_row": 1, "source_name": "Ada Lovelace", "source_email": source_email,
        "normalized_source_name": "ada lovelace", "normalized_source_email": source_email,
        "matched_roster_row": 2, "matched_full_name": "Ada Lovelace", "matched_email": matched_email,
        "matched_team": "Team", "matched_age_group": "U10", "match_method": status,
        "status": status, "reason": "test reason"}])


def empty_matches() -> pd.DataFrame:
    return pd.DataFrame(columns=match(MatchStatus.EXACT_NAME_EMAIL).columns)


def roster(**overrides: object) -> pd.DataFrame:
    row = {SOURCE_ROW_COLUMN: 2, "TEST TIME": "now", "Team Name": "Team", "First Name": "Ada",
           "Last Name": "Lovelace", "Gender": "F", "Birthday": "1/1/2010",
           "_birthday_parsed": pd.Timestamp("2010-01-01"), "Age Group": "U10", "Parent Contact": "a@x.com"}
    row.update(overrides)
    return pd.DataFrame([row])


def hardware(values: dict[object, object] | None = None) -> pd.DataFrame:
    row = {SOURCE_ROW_COLUMN: 1, **{i: pd.NA for i in range(34)}}
    row.update({1: "Ada Lovelace", 2: "a@x.com", 3: "Sprints", 10: "August 15, 2026 - 01:00 PM", 12: "4s 1ms"})
    row.update(values or {})
    return pd.DataFrame([row])


def test_exact_match_has_no_identity_warning() -> None:
    assert validate_identity(match(MatchStatus.EXACT_NAME_EMAIL), empty_matches()) == []


def test_fallback_warns_and_stays_eligible() -> None:
    issues = validate_identity(match(MatchStatus.UNIQUE_NAME_FALLBACK, "old@x.com", "new@x.com"), empty_matches())
    assert len(issues) == 1 and not issues[0].blocks_report
    assert is_athlete_report_eligible(2, issues)[0]


def test_shared_parent_email_not_an_error() -> None:
    people = pd.concat([roster(), roster(**{SOURCE_ROW_COLUMN: 3, "First Name": "Grace"})], ignore_index=True)
    assert not any("email" in issue.category for issue in validate_roster(people))


def test_unmatched_hardware_blocks() -> None:
    assert validate_identity(match(MatchStatus.UNMATCHED), empty_matches())[0].blocks_report


def test_ambiguous_hardware_blocks() -> None:
    assert validate_identity(match(MatchStatus.AMBIGUOUS_NAME), empty_matches())[0].blocks_report


def test_conflict_blocks() -> None:
    assert validate_identity(match(MatchStatus.NAME_EMAIL_CONFLICT), empty_matches())[0].blocks_report


def test_missing_birthday_warns_not_blocks() -> None:
    issues = validate_roster(roster(Birthday=pd.NA, _birthday_parsed=pd.NaT))
    assert issues[0].category == "missing_birthday" and not issues[0].blocks_report


def test_missing_age_group_blocks() -> None:
    issues = validate_roster(roster(**{"Age Group": pd.NA}))
    assert next(i for i in issues if i.category == "missing_age_group").blocks_report


def test_missing_team_warns() -> None:
    issue = next(i for i in validate_roster(roster(**{"Team Name": pd.NA})) if i.category == "missing_team")
    assert not issue.blocks_report


def test_missing_juggling_field_warns() -> None:
    frame = pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "First Name": "Ada", "Last Name": "Lovelace",
                           "Dominant": pd.NA, "Non-Dominant": 2, "Thighs": 3}])
    assert [i.category for i in validate_juggling(frame)] == ["missing_juggling_dominant"]


def test_all_juggling_fields_missing() -> None:
    frame = pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "First Name": "Ada", "Last Name": "Lovelace",
                           "Dominant": pd.NA, "Non-Dominant": pd.NA, "Thighs": pd.NA}])
    assert sum(i.category == "missing_all_juggling" for i in validate_juggling(frame)) == 1


def test_unknown_drill_detection() -> None:
    assert any(i.category == "unknown_drill" for i in validate_hardware(hardware({3: "Mystery"}), match(MatchStatus.EXACT_NAME_EMAIL)))


def test_known_drill_aliases_accepted() -> None:
    for drill in ("180 Degree Passing", "180 Degree passing", "5-10-2005", "Sprints", "Sprints Assessments"):
        assert not any(i.category == "unknown_drill" for i in validate_hardware(hardware({3: drill}), match(MatchStatus.EXACT_NAME_EMAIL)))


def test_malformed_timestamp() -> None:
    assert any(i.category == "malformed_assessment_timestamp" for i in validate_hardware(hardware({10: "bad"}), match(MatchStatus.EXACT_NAME_EMAIL)))


def test_malformed_duration() -> None:
    assert any(i.category == "malformed_duration" for i in validate_hardware(hardware({20: "0d"}), match(MatchStatus.EXACT_NAME_EMAIL)))


def test_multiple_assessment_dates() -> None:
    frame = pd.concat([hardware(), hardware({SOURCE_ROW_COLUMN: 2, 10: "August 16, 2026 - 01:00 PM"})], ignore_index=True)
    assert any(i.category == "multiple_assessment_dates" for i in validate_hardware(frame, match(MatchStatus.EXACT_NAME_EMAIL)))


def test_filename_sanitization() -> None:
    assert safe_report_filename("Johnny Smith") == "Johnny_Smith_Report.pdf"


def test_filename_collision_detection() -> None:
    canonical = pd.DataFrame([{"roster_row": 2, "full_name": "John Smith"}, {"roster_row": 3, "full_name": "John  Smith"}])
    assert detect_filename_collisions(canonical)
    assert len(validate_filenames(canonical)) == 2


def test_missing_logo_warns(test_workspace: Path) -> None:
    config = {"paths": {"logos": "logos"}, "logo_defaults": {"team_logo": "missing.png"}, "team_logos": {}}
    assert validate_logos(config, test_workspace)[0].category == "missing_logo_file"


def test_validation_csv_files(test_workspace: Path) -> None:
    issues = assign_issue_ids([ValidationIssue("WARNING", "test", "test", "message")])
    summary, details = write_validation_outputs(issues, test_workspace)
    assert summary.is_file() and details.is_file()
    assert pd.read_csv(details).loc[0, "issue_id"] == "VAL-000001"
