from __future__ import annotations

import math
import pandas as pd
import pytest

from src.metric_extractor import METRIC_COLUMNS
from src.percentiles import (
    build_age_group_percentiles, calculate_benchmark_percentile,
    calculate_metric_percentiles, metric_directions,
)


LOWER = {"dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best", "figure8_worst"}


def config(**percentile_overrides: object) -> dict[str, object]:
    return {
        "assessment": {"minimum_cohort_size": None, "cohort_fields": ["age_group"]},
        "percentiles": {"tie_method": "average", "single_member_percentile": 50.0,
                        **percentile_overrides},
        "metrics": {metric: {"direction": "lower" if metric in LOWER else "higher"}
                    for metric in METRIC_COLUMNS},
    }


def athletes(values: list[object], metric: str = "dash_10y",
             age_groups: list[object] | None = None) -> pd.DataFrame:
    count = len(values)
    frame = pd.DataFrame({"roster_row": range(1, count + 1),
        "full_name": [f"Athlete {i}" for i in range(1, count + 1)],
        "age_group": age_groups or ["U8"] * count,
        "team_name": ["A" if i % 2 else "B" for i in range(count)],
        "gender": ["F" if i % 2 else "M" for i in range(count)]})
    for name in METRIC_COLUMNS:
        frame[name] = pd.NA
    frame[metric] = values
    return frame


def test_higher_simple_cohort_endpoints_and_middle() -> None:
    result = calculate_metric_percentiles(pd.Series([10, 20, 30]), "higher")
    assert result.tolist() == [0.0, 50.0, 100.0]


def test_lower_simple_cohort_endpoints_and_middle() -> None:
    result = calculate_metric_percentiles(pd.Series([1.0, 2.0, 3.0]), "lower")
    assert result.tolist() == [100.0, 50.0, 0.0]


@pytest.mark.parametrize("metric", ["figure8_best", "figure8_worst"])
def test_figure8_metrics_are_lower_is_better(metric: str) -> None:
    result = build_age_group_percentiles(athletes([5, 10], metric), config()).assessments
    assert result[f"{metric}_percentile"].tolist() == [100.0, 0.0]


@pytest.mark.parametrize(("direction", "expected"), [
    ("higher", [0.0, 50.0, 50.0, 100.0]),
    ("lower", [100.0, 50.0, 50.0, 0.0]),
])
def test_ties_use_average_rank(direction: str, expected: list[float]) -> None:
    assert calculate_metric_percentiles(pd.Series([10, 20, 20, 30]), direction).tolist() == expected


def test_ties_and_results_are_independent_of_row_order() -> None:
    original = athletes([10, 20, 20, 30], "passing_90")
    shuffled = original.sample(frac=1, random_state=42)
    first = build_age_group_percentiles(original, config()).assessments.set_index("roster_row")
    second = build_age_group_percentiles(shuffled, config()).assessments.set_index("roster_row")
    pd.testing.assert_series_equal(first["passing_90_percentile"].sort_index(),
                                   second["passing_90_percentile"].sort_index())


def test_missing_excluded_from_percentile_average_and_count() -> None:
    result = build_age_group_percentiles(athletes([1.0, pd.NA, 3.0]), config()).assessments
    assert result["dash_10y_percentile"].tolist()[0] == 100.0
    assert pd.isna(result.loc[1, "dash_10y_percentile"])
    assert result.loc[2, "dash_10y_percentile"] == 0.0
    assert set(result["dash_10y_age_group_average"]) == {2.0}
    assert set(result["dash_10y_cohort_count"]) == {2}


def test_age_groups_are_independent() -> None:
    result = build_age_group_percentiles(
        athletes([1, 3, 100, 200], age_groups=["U8", "U8", "U9", "U9"]), config()).assessments
    assert result["dash_10y_percentile"].tolist() == [100.0, 0.0, 100.0, 0.0]


def test_team_and_gender_do_not_split_cohort() -> None:
    result = build_age_group_percentiles(athletes([1, 2, 3]), config()).assessments
    assert result["dash_10y_percentile"].tolist() == [100.0, 50.0, 0.0]
    assert set(result["dash_10y_cohort_count"]) == {3}


def test_missing_authoritative_age_group_gets_no_percentiles() -> None:
    result = build_age_group_percentiles(athletes([1, 2], age_groups=[pd.NA, "U8"]), config()).assessments
    assert pd.isna(result.loc[0, "dash_10y_percentile"])
    assert pd.isna(result.loc[0, "dash_10y_cohort_count"])
    assert result.loc[1, "dash_10y_percentile"] == 50.0


def test_single_member_cohort_is_configured_midpoint() -> None:
    assert calculate_metric_percentiles(pd.Series([10]), "higher", single_member_percentile=50).iloc[0] == 50
    assert calculate_metric_percentiles(pd.Series([10]), "higher", single_member_percentile=40).iloc[0] == 40


def test_all_identical_is_midpoint() -> None:
    assert calculate_metric_percentiles(pd.Series([7, 7, 7]), "lower").tolist() == [50, 50, 50]
    assert calculate_metric_percentiles(pd.Series([7, 7]), "lower", single_member_percentile=40).tolist() == [50, 50]


def test_zero_valid_values_unavailable() -> None:
    assert calculate_metric_percentiles(pd.Series([pd.NA, None]), "higher").isna().all()


def test_two_member_cohort_has_endpoints() -> None:
    assert calculate_metric_percentiles(pd.Series([4, 8]), "higher").tolist() == [0, 100]


@pytest.mark.parametrize(("metric", "values", "average"), [
    ("dash_10y", [1.0, 2.0, 3.0], 2.0),
    ("passing_90", [2, 4, 9], 5.0),
])
def test_raw_average_is_arithmetic_not_direction_adjusted(metric: str, values: list[float], average: float) -> None:
    result = build_age_group_percentiles(athletes(values, metric), config())
    row = result.benchmarks.query("age_group == 'U8' and metric == @metric").iloc[0]
    assert row["raw_average"] == average
    assert row["valid_count"] == 3


def test_direction_configuration_changes_ranking() -> None:
    frame = athletes([1, 3], "dash_10y")
    lower = build_age_group_percentiles(frame, config()).assessments["dash_10y_percentile"].tolist()
    changed = config()
    changed["metrics"]["dash_10y"]["direction"] = "higher"  # type: ignore[index]
    higher = build_age_group_percentiles(frame, changed).assessments["dash_10y_percentile"].tolist()
    assert lower == [100, 0] and higher == [0, 100]


def test_all_ten_metric_directions_configured() -> None:
    directions = metric_directions(config())
    assert set(directions) == set(METRIC_COLUMNS)
    assert {m for m, d in directions.items() if d == "lower"} == LOWER


def test_minimum_cohort_size_can_suppress_ranking_without_losing_benchmark() -> None:
    configured = config()
    configured["assessment"]["minimum_cohort_size"] = 3  # type: ignore[index]
    result = build_age_group_percentiles(athletes([1, 2]), configured)
    assert result.assessments["dash_10y_percentile"].isna().all()
    assert result.benchmarks.query("metric == 'dash_10y'").iloc[0]["valid_count"] == 2


def test_percentiles_recalculate_when_corrected_sprint_becomes_missing() -> None:
    before = build_age_group_percentiles(athletes([2.0, 4.0], "dash_20y"), config()).assessments
    after = build_age_group_percentiles(athletes([pd.NA, 4.0], "dash_20y"), config()).assessments
    assert before["dash_20y_percentile"].tolist() == [100.0, 0.0]
    assert pd.isna(after.loc[0, "dash_20y_percentile"])
    assert after.loc[1, "dash_20y_percentile"] == 50.0


@pytest.mark.parametrize(("direction", "expected"), [
    ("higher", 75.0), ("lower", 25.0),
])
def test_benchmark_between_observed_values_interpolates(direction: str, expected: float) -> None:
    assert calculate_benchmark_percentile(3, pd.Series([1, 2, 4]), direction) == pytest.approx(expected)


@pytest.mark.parametrize(("direction", "expected"), [
    ("higher", 50.0), ("lower", 50.0),
])
def test_benchmark_exact_observed_value(direction: str, expected: float) -> None:
    assert calculate_benchmark_percentile(2, pd.Series([1, 2, 4]), direction) == expected


def test_benchmark_tied_observed_value_uses_average_rank() -> None:
    cohort = pd.Series([10, 20, 20, 30])
    assert calculate_benchmark_percentile(20, cohort, "higher") == 50.0
    assert calculate_benchmark_percentile(20, cohort, "lower") == 50.0


@pytest.mark.parametrize("benchmark,cohort", [(None, pd.Series([1, 2])), (2, pd.Series(dtype=float))])
def test_missing_benchmark_or_cohort_is_unavailable(benchmark: object, cohort: pd.Series) -> None:
    assert math.isnan(calculate_benchmark_percentile(benchmark, cohort, "higher"))


def test_benchmark_calculation_does_not_change_athlete_percentiles() -> None:
    cohort = pd.Series([1.0, 2.0, 4.0])
    before = calculate_metric_percentiles(cohort, "lower")
    calculate_benchmark_percentile(cohort.mean(), cohort, "lower")
    after = calculate_metric_percentiles(cohort, "lower")
    pd.testing.assert_series_equal(before, after)


def test_age_group_average_percentile_is_added_to_flat_output() -> None:
    result = build_age_group_percentiles(athletes([1.0, 2.0, 4.0]), config()).assessments
    assert result["dash_10y_age_group_average_percentile"].nunique() == 1
    assert result.loc[0, "dash_10y_age_group_average_percentile"] == pytest.approx(41.6666667)
