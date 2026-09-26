"""Age-group raw benchmarks and deterministic metric percentiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final
import math

import pandas as pd

from .metric_extractor import METRIC_COLUMNS


VALID_DIRECTIONS: Final[set[str]] = {"lower", "higher"}


@dataclass
class PercentileResult:
    assessments: pd.DataFrame
    benchmarks: pd.DataFrame


def metric_directions(config: dict[str, object]) -> dict[str, str]:
    """Read and validate the direction of every canonical metric."""
    configured = config.get("metrics")
    if not isinstance(configured, dict):
        raise ValueError("Config must contain a metrics object")
    directions: dict[str, str] = {}
    for metric in METRIC_COLUMNS:
        entry = configured.get(metric)
        direction = entry.get("direction") if isinstance(entry, dict) else None
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"Metric {metric} must configure direction as lower or higher")
        directions[metric] = str(direction)
    return directions


def calculate_metric_percentiles(values: pd.Series, direction: str,
                                 tie_method: str = "average",
                                 single_member_percentile: float = 50.0,
                                 all_identical_percentile: float = 50.0,
                                 minimum_cohort_size: int | None = None) -> pd.Series:
    """Rank valid values on a 0–100 endpoint scale; preserve missing values."""
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"Unsupported metric direction: {direction}")
    if tie_method != "average":
        raise ValueError(f"Unsupported percentile tie method: {tie_method}")
    numeric = pd.to_numeric(values, errors="coerce")
    output = pd.Series(float("nan"), index=values.index, dtype=float)
    valid = numeric.dropna()
    count = len(valid)
    if count == 0 or (minimum_cohort_size is not None and count < minimum_cohort_size):
        return output
    if count == 1:
        output.loc[valid.index] = float(single_member_percentile)
        return output
    if valid.nunique(dropna=True) == 1:
        output.loc[valid.index] = float(all_identical_percentile)
        return output
    ranks = valid.rank(method=tie_method, ascending=True)
    if direction == "higher":
        percentiles = ((ranks - 1.0) / (count - 1.0)) * 100.0
    else:
        percentiles = ((count - ranks) / (count - 1.0)) * 100.0
    output.loc[valid.index] = percentiles.astype(float)
    return output


def calculate_benchmark_percentile(
    raw_benchmark_value: object,
    cohort_raw_values: pd.Series,
    direction: str,
    *,
    tie_method: str = "average",
    single_member_percentile: float = 50.0,
    all_identical_percentile: float = 50.0,
) -> float:
    """Locate a raw benchmark on the cohort's unchanged percentile scale.

    Exact observed values receive that value's average-rank percentile. Values
    between observations are linearly interpolated between the two neighboring
    raw-value percentile positions. No synthetic cohort member is introduced.
    """
    benchmark = pd.to_numeric(raw_benchmark_value, errors="coerce")
    if pd.isna(benchmark) or not math.isfinite(float(benchmark)):
        return float("nan")
    numeric = pd.to_numeric(cohort_raw_values, errors="coerce").dropna()
    if numeric.empty:
        return float("nan")
    positioned = calculate_metric_percentiles(
        numeric, direction, tie_method, single_member_percentile,
        all_identical_percentile, None,
    )
    points = (pd.DataFrame({"raw": numeric.astype(float), "percentile": positioned})
              .groupby("raw", as_index=False)["percentile"].first()
              .sort_values("raw"))
    x = float(benchmark)
    exact = points.loc[points["raw"].eq(x), "percentile"]
    if not exact.empty:
        return float(exact.iloc[0])
    lower = points.loc[points["raw"] < x].tail(1)
    upper = points.loc[points["raw"] > x].head(1)
    if lower.empty:
        return float(points.iloc[0]["percentile"])
    if upper.empty:
        return float(points.iloc[-1]["percentile"])
    x0, y0 = float(lower.iloc[0]["raw"]), float(lower.iloc[0]["percentile"])
    x1, y1 = float(upper.iloc[0]["raw"]), float(upper.iloc[0]["percentile"])
    return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0)


def build_age_group_percentiles(canonical: pd.DataFrame,
                                config: dict[str, object]) -> PercentileResult:
    """Add raw averages, counts, and percentiles using only roster age group."""
    directions = metric_directions(config)
    percentile_config = config.get("percentiles", {})
    percentile_config = percentile_config if isinstance(percentile_config, dict) else {}
    assessment_config = config.get("assessment", {})
    assessment_config = assessment_config if isinstance(assessment_config, dict) else {}
    tie_method = str(percentile_config.get("tie_method") or "average")
    single = float(percentile_config.get("single_member_percentile", 50.0))
    identical = float(percentile_config.get("all_identical_percentile", 50.0))
    minimum_raw = assessment_config.get("minimum_cohort_size")
    minimum = None if minimum_raw is None else int(minimum_raw)
    if minimum is not None and minimum < 1:
        raise ValueError("minimum_cohort_size must be null or a positive integer")

    result = canonical.copy()
    valid_age = result["age_group"].notna() & result["age_group"].astype(str).str.strip().ne("")
    benchmark_records: list[dict[str, object]] = []
    age_groups = sorted(result.loc[valid_age, "age_group"].unique(), key=str)
    for metric in METRIC_COLUMNS:
        result[f"{metric}_percentile"] = float("nan")
        result[f"{metric}_age_group_average"] = float("nan")
        result[f"{metric}_age_group_average_percentile"] = float("nan")
        result[f"{metric}_cohort_count"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        numeric = pd.to_numeric(result[metric], errors="coerce")
        for age_group in age_groups:
            cohort_index = result.index[valid_age & result["age_group"].eq(age_group)]
            cohort_values = numeric.loc[cohort_index]
            valid_count = int(cohort_values.notna().sum())
            raw_average = float(cohort_values.mean()) if valid_count else float("nan")
            benchmark_records.append({"age_group": age_group, "metric": metric,
                                      "raw_average": raw_average, "valid_count": valid_count})
            result.loc[cohort_index, f"{metric}_age_group_average"] = raw_average
            benchmark_percentile = calculate_benchmark_percentile(
                raw_average, cohort_values, directions[metric], tie_method=tie_method,
                single_member_percentile=single,
                all_identical_percentile=identical,
            )
            result.loc[cohort_index, f"{metric}_age_group_average_percentile"] = benchmark_percentile
            result.loc[cohort_index, f"{metric}_cohort_count"] = valid_count
            result.loc[cohort_index, f"{metric}_percentile"] = calculate_metric_percentiles(
                cohort_values, directions[metric], tie_method, single, identical, minimum)
    benchmarks = pd.DataFrame.from_records(
        benchmark_records, columns=["age_group", "metric", "raw_average", "valid_count"]
    )
    return PercentileResult(result, benchmarks)


def write_percentile_debug_outputs(result: PercentileResult,
                                   output_directory: Path) -> tuple[Path, Path]:
    debug = Path(output_directory) / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    metrics_path = debug / "percentile_metrics.csv"
    benchmarks_path = debug / "age_group_benchmarks.csv"
    result.assessments.to_csv(metrics_path, index=False)
    result.benchmarks.to_csv(benchmarks_path, index=False)
    return metrics_path, benchmarks_path
