from __future__ import annotations

import math

import pandas as pd
import pytest

from src.matcher import match_hardware_identities, match_juggling_identities
from src.metric_extractor import (
    METRIC_COLUMNS, extract_5_10_5, extract_canonical_assessments,
    extract_figure8_metrics, extract_juggling_metrics, extract_passing_metrics,
    extract_sprint_metrics, sprint_attempt_components, select_fastest_time, select_highest_score,
)
from src.raw_schema import SOURCE_ROW_COLUMN


def roster() -> pd.DataFrame:
    return pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "TEST TIME": "", "Team Name": "Roster Team",
        "First Name": "Ada", "Last Name": "Lovelace", "Gender": "F", "Birthday": "1/1/2010",
        "_birthday_parsed": pd.Timestamp("2010-01-01"), "Age Group": "U10", "Parent Contact": "ada@example.com"}])


def hw_row(row: int, drill: str, total: object = pd.NA, hit: object = pd.NA,
           first: object = pd.NA, date: str = "August 15, 2026 - 01:00 PM",
           name: str = "Ada Lovelace", email: str = "ada@example.com",
           extra: dict[int, object] | None = None) -> dict[object, object]:
    result = {SOURCE_ROW_COLUMN: row, **{i: pd.NA for i in range(34)}}
    result.update({1: name, 2: email, 3: drill, 10: date, 12: total, 14: hit, 21: first})
    result.update(extra or {})
    return result


def rows(*items: dict[object, object]) -> pd.DataFrame:
    return pd.DataFrame(items)


def juggling(dominant: object = 10, non_dominant: object = 8, thighs: object = 6,
             first: str = "Ada", last: str = "Lovelace") -> pd.DataFrame:
    return pd.DataFrame([{SOURCE_ROW_COLUMN: 2, "First Name": first, "Last Name": last,
                          "Dominant": dominant, "Non-Dominant": non_dominant, "Thighs": thighs}])


def run(hardware: pd.DataFrame, jug: pd.DataFrame | None = None):
    people = roster()
    jug = juggling() if jug is None else jug
    return extract_canonical_assessments(hardware, people, jug,
        match_hardware_identities(hardware, people), match_juggling_identities(jug, people))


@pytest.mark.parametrize("label", ["Sprints", "Sprints Assessments"])
def test_sprint_labels_use_first_split_and_total(label: str) -> None:
    result = extract_sprint_metrics(rows(hw_row(1, label, total="3s 900ms", first="1s 950ms", extra={22: "1s 950ms"})))
    assert result == {"dash_10y": pytest.approx(1.95), "dash_20y": pytest.approx(3.9)}


def test_sprint_attempts_select_metrics_independently_and_ignore_unused_fields() -> None:
    frame = rows(hw_row(1, "Sprints", "3s 900ms", first="2s", extra={20: "0d", 22: "1s 900ms"}),
                 hw_row(2, "Sprints Assessments", "4s", first="1s 950ms", extra={20: "1ms", 22: "2s 50ms"}))
    result = run(frame).canonical.iloc[0]
    assert result["dash_10y"] == pytest.approx(1.95)
    assert result["dash_20y"] == pytest.approx(3.9)
    assert "Sprints|Sprints Assessments" == result["source_drill_labels"]


def test_5_10_5_fastest_total_only() -> None:
    frame = rows(hw_row(1, "5-10-2005", "5s", extra={20: "1ms", 21: "0d"}),
                 hw_row(2, "5-10-2005", "4s 500ms", extra={20: "0d", 21: "1ms"}))
    assert extract_5_10_5(frame)["shuttle_5_10_5"] == pytest.approx(4.5)


def test_incomplete_sprint_supplies_10y_but_not_20y() -> None:
    result = extract_sprint_metrics(rows(hw_row(1, "Sprints Assessments", "2s", first="2s")))
    assert result["dash_10y"] == 2.0
    assert result["dash_20y"] is None


def test_fast_incomplete_total_cannot_beat_complete_20y() -> None:
    frame = rows(hw_row(1, "Sprints Assessments", "2s", first="2s"),
                 hw_row(2, "Sprints", "4s", first="1s 9ms", extra={22: "2s 991ms"}))
    result = extract_sprint_metrics(frame)
    assert result["dash_10y"] == pytest.approx(1.009)
    assert result["dash_20y"] == 4.0


def test_complete_sprint_tolerance_and_inconsistent_total() -> None:
    within = pd.Series(hw_row(1, "Sprints", "4s 5ms", first="2s", extra={22: "2s"}))
    outside = pd.Series(hw_row(2, "Sprints", "4s 11ms", first="2s", extra={22: "2s"}))
    assert sprint_attempt_components(within)["complete_20y"]
    assert not sprint_attempt_components(outside)["complete_20y"]


def test_5_10_5_invalid_total_unavailable() -> None:
    assert extract_5_10_5(rows(hw_row(1, "5-10-2005", "0d")))["shuttle_5_10_5"] is None


@pytest.mark.parametrize(("times", "best", "worst"), [
    (["7s", "8s"], 7.0, 8.0), (["7s", "9s", "8s"], 7.0, 9.0),
    (["7s"], 7.0, None),
])
def test_figure8_min_max_rules(times: list[str], best: float, worst: float | None) -> None:
    result = extract_figure8_metrics(rows(*(hw_row(i, "Figure 8", value, extra={20: "0d", 21: "1ms"})
                                            for i, value in enumerate(times, 1))))
    assert result["figure8_best"] == best
    assert result["figure8_worst"] == worst


def test_single_figure8_warns_and_does_not_copy_worst() -> None:
    result = run(rows(hw_row(1, "Figure 8", "7s")))
    assert math.isnan(result.canonical.iloc[0]["figure8_worst"])
    assert any(issue.category == "single_figure8_attempt" for issue in result.issues)


@pytest.mark.parametrize(("label", "metric"), [
    ("90 Degree Passing", "passing_90"), ("180 Degree Passing", "passing_180"),
    ("180 Degree passing", "passing_180"),
])
def test_passing_uses_highest_hit_for_all_aliases(label: str, metric: str) -> None:
    frame = rows(hw_row(1, label, total="1ms", hit="7", extra={13: 999, 15: 999, 20: "0d"}),
                 hw_row(2, label, total="0d", hit="9", extra={13: 0, 15: 0, 20: "bad"}))
    assert extract_passing_metrics(frame, metric)[metric] == 9


def test_juggling_supplied_scores_and_missingness() -> None:
    result = extract_juggling_metrics(juggling(10, pd.NA, 3))
    assert result["juggling_dominant"] == 10
    assert result["juggling_thighs"] == 3
    assert result["juggling_non_dominant"] is None
    assert not any("left" in name or "right" in name for name in METRIC_COLUMNS)


def test_date_boundary_roster_authority_and_fallback_match() -> None:
    frame = rows(hw_row(1, "Sprints", "4s", first="2s", email="old@example.com", extra={22: "2s"}),
                 hw_row(2, "Sprints", "3s", first="1s", date="August 16, 2026 - 01:00 PM",
                        email="old@example.com", extra={22: "2s"}))
    result = run(frame).canonical.sort_values("assessment_date")
    assert len(result) == 2
    assert result["dash_20y"].tolist() == [4.0, 3.0]
    assert set(result["team_name"]) == {"Roster Team"}
    assert set(result["age_group"]) == {"U10"}
    assert set(result["match_method"]) == {"unique_name_fallback"}
    assert result["juggling_dominant"].isna().all()


def test_unmatched_athlete_excluded() -> None:
    frame = rows(hw_row(1, "Sprints", "4s", first="2s", name="Unknown Person"))
    assert run(frame).canonical.empty


def test_invalid_required_value_warns_but_unused_malformed_value_does_not() -> None:
    invalid = run(rows(hw_row(1, "90 Degree Passing", total="0d", hit="bad", extra={20: "bad"})))
    assert len([i for i in invalid.issues if i.category == "invalid_required_metric_value"]) == 1
    valid = run(rows(hw_row(1, "90 Degree Passing", total="0d", hit="8", extra={20: "bad"})))
    assert not any(i.category == "invalid_required_metric_value" for i in valid.issues)


def test_selection_helpers() -> None:
    assert select_fastest_time(["0d", "2s", "1s 500ms"]) == 1.5
    assert select_highest_score([pd.NA, "2", "5"]) == 5
