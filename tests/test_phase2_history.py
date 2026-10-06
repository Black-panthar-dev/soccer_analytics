from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.assessment_history import (
    AthleteAssessment, assessments_from_canonical, get_assessment_by_date,
    get_assessments_for_athlete, get_latest_assessment, get_previous_assessment,
)
from src.matcher import match_hardware_identities, match_juggling_identities
from src.metric_extractor import METRIC_COLUMNS, extract_canonical_assessments
from src.performance_delta import DeltaStatus, calculate_metric_delta, compare_assessments
from src.raw_schema import SOURCE_ROW_COLUMN


def roster() -> pd.DataFrame:
    return pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "TEST TIME": "", "Team Name": "Team",
        "First Name": "Athlete", "Last Name": "G", "Gender": "F", "Birthday": "1/1/2010",
        "_birthday_parsed": pd.Timestamp("2010-01-01"), "Age Group": "U10",
        "Parent Contact": "parent@example.com"}])


def hw(row: int, drill: str, day: int, *, total: object = pd.NA, hit: object = pd.NA,
       first: object = pd.NA, second: object = pd.NA) -> dict[object, object]:
    record = {SOURCE_ROW_COLUMN: row, **{index: pd.NA for index in range(34)}}
    record.update({1: "Athlete G", 2: "parent@example.com", 3: drill,
                   10: f"August {day}, 2026 - 01:00 PM", 12: total, 14: hit,
                   21: first, 22: second})
    return record


def juggling() -> pd.DataFrame:
    return pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "First Name": "Athlete", "Last Name": "G",
                          "Dominant": 10, "Non-Dominant": 8, "Thighs": 6}])


def extract(*rows: dict[object, object]):
    hardware = pd.DataFrame(rows)
    people, jug = roster(), juggling()
    return extract_canonical_assessments(
        hardware, people, jug, match_hardware_identities(hardware, people),
        match_juggling_identities(jug, people),
    )


def assessment(day: int, **metrics: float | None) -> AthleteAssessment:
    values = {metric: None for metric in METRIC_COLUMNS}
    values.update(metrics)
    return AthleteAssessment(2, "Athlete G", date(2026, 8, day), "U10", "Team", values,
                             {key: value is not None for key, value in values.items()}, {}, {})


def test_different_dates_stay_separate_and_same_day_attempts_combine() -> None:
    result = extract(
        hw(1, "Sprints", 15, total="4s", first="2s", second="2s"),
        hw(2, "Sprints Assessments", 15, total="3s 900ms", first="1s 950ms", second="1s 950ms"),
        hw(3, "Sprints", 20, total="3s 800ms", first="1s 900ms", second="1s 900ms"),
        hw(4, "Sprints", 20, total="3s 700ms", first="1s 850ms", second="1s 850ms"),
    )
    canonical = result.canonical.sort_values("assessment_date")
    assert len(canonical) == 2
    assert canonical["dash_10y"].tolist() == pytest.approx([1.95, 1.85])
    assert canonical["dash_20y"].tolist() == pytest.approx([3.9, 3.7])
    assert canonical["attempt_counts"].str.contains("sprints:2").all()
    assert canonical[["juggling_dominant", "juggling_non_dominant", "juggling_thighs"]].isna().all().all()


def test_incomplete_20y_stays_invalid_within_each_date() -> None:
    result = extract(hw(1, "Sprints", 15, total="2s", first="2s"),
                     hw(2, "Sprints", 20, total="4s", first="2s", second="2s"))
    rows = result.canonical.sort_values("assessment_date")
    assert pd.isna(rows.iloc[0]["dash_20y"])
    assert rows.iloc[1]["dash_20y"] == 4.0


def test_figure8_selection_is_independent_by_date() -> None:
    result = extract(hw(1, "Figure 8", 15, total="8s"),
                     hw(2, "Figure 8", 20, total="7s"),
                     hw(3, "Figure 8", 20, total="9s"))
    earlier, later = result.canonical.sort_values("assessment_date").to_dict("records")
    assert earlier["figure8_best"] == 8.0 and pd.isna(earlier["figure8_worst"])
    assert later["figure8_best"] == 7.0 and later["figure8_worst"] == 9.0


def test_history_selection_helpers_and_date_normalization() -> None:
    items = [assessment(20, dash_10y=1.8), assessment(15, dash_10y=2.0)]
    assert [item.assessment_date.day for item in get_assessments_for_athlete(items, 2)] == [15, 20]
    assert get_latest_assessment(items, 2).assessment_date.day == 20
    assert get_previous_assessment(items, 2).assessment_date.day == 15
    assert get_assessment_by_date(items, 2, "2026-08-15").raw_metrics["dash_10y"] == 2.0
    assert get_previous_assessment([items[0]], 2) is None


@pytest.mark.parametrize(("metric", "current", "previous", "performance", "status"), [
    ("dash_10y", 1.8, 2.0, 0.2, DeltaStatus.IMPROVED),
    ("dash_10y", 2.2, 2.0, -0.2, DeltaStatus.DECLINED),
    ("passing_90", 12.0, 10.0, 2.0, DeltaStatus.IMPROVED),
    ("passing_90", 8.0, 10.0, -2.0, DeltaStatus.DECLINED),
    ("juggling_dominant", 10.0000000001, 10.0, 0.0, DeltaStatus.UNCHANGED),
])
def test_direction_aware_delta(metric: str, current: float, previous: float,
                               performance: float, status: str) -> None:
    delta = calculate_metric_delta(metric, current, previous, tolerance=1e-6)
    assert delta.raw_delta == pytest.approx(current - previous)
    assert delta.performance_delta == pytest.approx(performance)
    assert delta.status == status


@pytest.mark.parametrize(("current", "previous"), [(None, 4.0), (4.0, None), (None, None)])
def test_missing_delta_is_na_and_never_zero(current: float | None, previous: float | None) -> None:
    delta = calculate_metric_delta("dash_20y", current, previous)
    assert delta.raw_delta is None and delta.performance_delta is None
    assert delta.status == DeltaStatus.NOT_AVAILABLE


def test_compare_only_same_athlete_and_previous_none_is_safe() -> None:
    current = assessment(20, passing_180=8)
    deltas = compare_assessments(current, None)
    assert len(deltas) == 10 and all(item.status == "N/A" for item in deltas)
    other = AthleteAssessment(99, "Other", date(2026, 8, 15), None, None,
                              current.raw_metrics, current.availability, {}, {})
    with pytest.raises(ValueError):
        compare_assessments(current, other)


def test_phase1_canonical_values_round_trip_unchanged_into_history_model() -> None:
    canonical = extract(hw(1, "90 Degree Passing", 15, hit=7),
                        hw(2, "90 Degree Passing", 15, hit=11)).canonical
    history = assessments_from_canonical(canonical)
    assert len(history) == 1
    for metric in METRIC_COLUMNS:
        expected = canonical.iloc[0][metric]
        actual = history[0].raw_metrics[metric]
        assert (actual is None and pd.isna(expected)) or actual == expected
