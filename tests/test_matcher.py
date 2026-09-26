from __future__ import annotations

import pandas as pd
import pytest

from src.matcher import MatchStatus, build_canonical_roster, match_hardware_identities, match_juggling_identities
from src.normalizer import normalize_name
from src.raw_schema import SOURCE_ROW_COLUMN


def roster(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame([
        {SOURCE_ROW_COLUMN: index + 2, "TEST TIME": "now", "Team Name": "Team A",
         "First Name": first, "Last Name": last, "Gender": "X", "Birthday": "1/1/2010",
         "Age Group": "U10", "Parent Contact": email}
        for index, (first, last, email) in enumerate(rows)
    ])


def hardware(name: object, email: object) -> pd.DataFrame:
    return pd.DataFrame([{SOURCE_ROW_COLUMN: 1, 1: name, 2: email}])


def juggling(first: object, last: object, scores: tuple[object, object, object] = (1, 2, 3)) -> pd.DataFrame:
    return pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "First Name": first, "Last Name": last,
                          "Dominant": scores[0], "Non-Dominant": scores[1], "Thighs": scores[2]}])


@pytest.mark.parametrize("name,email", [
    ("John Smith", "parent@example.com"),
    ("JOHN SMITH", "PARENT@EXAMPLE.COM"),
    (" John Smith ", " parent@example.com "),
    ("John   Smith", "parent@example.com"),
])
def test_exact_name_email_normalization(name: str, email: str) -> None:
    result = match_hardware_identities(hardware(name, email), roster(("John", "Smith", "parent@example.com")))
    assert result.loc[0, "status"] == MatchStatus.EXACT_NAME_EMAIL


def test_unique_name_fallback() -> None:
    result = match_hardware_identities(hardware("John Smith", "unknown@example.com"), roster(("John", "Smith", "real@example.com")))
    assert result.loc[0, "status"] == MatchStatus.UNIQUE_NAME_FALLBACK


def test_duplicate_name_is_ambiguous() -> None:
    result = match_hardware_identities(hardware("John Smith", "unknown@example.com"), roster(
        ("John", "Smith", "one@example.com"), ("John", "Smith", "two@example.com")))
    assert result.loc[0, "status"] == MatchStatus.AMBIGUOUS_NAME


def test_unmatched_name() -> None:
    result = match_hardware_identities(hardware("Nobody Here", "none@example.com"), roster(("John", "Smith", "x@example.com")))
    assert result.loc[0, "status"] == MatchStatus.UNMATCHED


def test_genuine_name_email_conflict() -> None:
    result = match_hardware_identities(hardware("John Smith", "jane@example.com"), roster(
        ("John", "Smith", "john@example.com"), ("Jane", "Jones", "jane@example.com")))
    assert result.loc[0, "status"] == MatchStatus.NAME_EMAIL_CONFLICT


def test_siblings_can_share_parent_email() -> None:
    people = roster(("John", "Smith", "parent@example.com"), ("Jane", "Smith", "parent@example.com"))
    result = match_hardware_identities(hardware("John Smith", "parent@example.com"), people)
    assert result.loc[0, "status"] == MatchStatus.EXACT_NAME_EMAIL
    assert result.loc[0, "matched_full_name"] == "John Smith"


def test_shared_email_alone_does_not_match_or_conflict() -> None:
    people = roster(("John", "Smith", "parent@example.com"), ("Jane", "Smith", "parent@example.com"))
    result = match_hardware_identities(hardware("Someone Else", "parent@example.com"), people)
    assert result.loc[0, "status"] == MatchStatus.UNMATCHED


def test_apostrophe_normalization() -> None:
    assert normalize_name("D\u2019Angelo") == normalize_name("D'Angelo")
    assert normalize_name("D\u00e2\u20ac\u2122Angelo") == normalize_name("D'Angelo")


def test_hyphen_is_preserved() -> None:
    assert normalize_name("Anne-Marie Smith") == "anne-marie smith"
    assert normalize_name("Anne Marie Smith") != normalize_name("Anne-Marie Smith")


def test_canonical_roster_uses_clean_team() -> None:
    canonical = build_canonical_roster(roster(("John", "Smith", "x@example.com")))
    assert canonical.loc[0, "team_name"] == "Team A"


def test_juggling_unique_name_match() -> None:
    result = match_juggling_identities(juggling("John", "Smith"), roster(("John", "Smith", "x@example.com")))
    assert result.loc[0, "status"] == MatchStatus.UNIQUE_NAME_MATCH


def test_juggling_unmatched() -> None:
    result = match_juggling_identities(juggling("Nobody", "Here"), roster(("John", "Smith", "x@example.com")))
    assert result.loc[0, "status"] == MatchStatus.UNMATCHED


def test_juggling_ambiguity() -> None:
    result = match_juggling_identities(juggling("John", "Smith"), roster(
        ("John", "Smith", "one@example.com"), ("John", "Smith", "two@example.com")))
    assert result.loc[0, "status"] == MatchStatus.AMBIGUOUS_NAME


def test_missing_juggling_scores_do_not_affect_identity() -> None:
    result = match_juggling_identities(juggling("John", "Smith", (pd.NA, pd.NA, pd.NA)), roster(("John", "Smith", "x@example.com")))
    assert result.loc[0, "status"] == MatchStatus.UNIQUE_NAME_MATCH


def test_fuzzy_matching_does_not_occur() -> None:
    result = match_hardware_identities(hardware("Jon Smith", "unknown@example.com"), roster(("John", "Smith", "x@example.com")))
    assert result.loc[0, "status"] == MatchStatus.UNMATCHED
