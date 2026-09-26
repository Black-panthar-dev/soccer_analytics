from __future__ import annotations

import pytest

from src.drill_normalizer import normalize_drill_name
from src.time_parser import parse_duration_to_seconds


@pytest.mark.parametrize(("raw", "expected"), [
    ("30s", 30.0),
    ("5s 518ms", 5.518),
    ("4s 75ms", 4.075),
    ("2s 37ms", 2.037),
    ("362ms", 0.362),
    ("  5s   518ms  ", 5.518),
])
def test_duration_valid(raw: str, expected: float) -> None:
    assert parse_duration_to_seconds(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "   ", None, "not a duration", "0d"])
def test_duration_missing_or_malformed(raw: object) -> None:
    assert parse_duration_to_seconds(raw) is None


def test_missing_duration_never_becomes_zero() -> None:
    assert parse_duration_to_seconds(None) is None
    assert parse_duration_to_seconds("") is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("90 Degree Passing", "passing_90"),
    ("180 Degree Passing", "passing_180"),
    ("180 Degree passing", "passing_180"),
    ("5-10-2005", "shuttle_5_10_5"),
    ("Figure 8", "figure8"),
    ("Sprints", "sprints"),
    ("Sprints Assessments", "sprints"),
])
def test_known_drill_normalization(raw: str, expected: str) -> None:
    assert normalize_drill_name(raw) == expected


def test_unknown_drill_is_unrecognized() -> None:
    assert normalize_drill_name("Unknown Drill") is None


def test_drill_normalization_is_not_fuzzy() -> None:
    assert normalize_drill_name("Sprint") is None
    assert normalize_drill_name("180 Degree Passin") is None
