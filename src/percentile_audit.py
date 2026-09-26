"""Real-data percentile audit and invariant checks for Phase 1."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config_loader import load_config
from .metric_audit import PROJECT_ROOT, run_real_data_audit
from .metric_extractor import METRIC_COLUMNS
from .percentiles import build_age_group_percentiles, metric_directions, write_percentile_debug_outputs


def _sanity_checks(frame: pd.DataFrame, config: dict[str, object]) -> pd.DataFrame:
    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, details: str) -> None:
        checks.append({"check": name, "passed": passed, "details": details})

    directions = metric_directions(config)
    for metric in ("dash_10y", "figure8_best", "figure8_worst"):
        passed = True
        for _, group in frame.dropna(subset=["age_group", metric]).groupby("age_group"):
            best = group.loc[group[metric] == group[metric].min(), f"{metric}_percentile"]
            passed &= not best.empty and best.eq(group[f"{metric}_percentile"].max()).all()
        record(f"fastest_{metric}_has_highest_percentile", passed, "Checked within each age group")
    for metric in ("passing_90", "passing_180"):
        passed = True
        for _, group in frame.dropna(subset=["age_group", metric]).groupby("age_group"):
            best = group.loc[group[metric] == group[metric].max(), f"{metric}_percentile"]
            passed &= not best.empty and best.eq(group[f"{metric}_percentile"].max()).all()
        record(f"highest_{metric}_has_highest_percentile", passed, "Checked within each age group")
    juggling_ok = all(frame.loc[frame[m].isna(), f"{m}_percentile"].isna().all()
                      for m in METRIC_COLUMNS[-3:])
    record("missing_juggling_stays_missing", juggling_ok, "No missing juggling raw value became percentile zero")

    age_only_ok = True
    team_independent = True
    for metric in METRIC_COLUMNS:
        for age_group, group in frame.dropna(subset=["age_group"]).groupby("age_group"):
            expected_count = int(group[metric].notna().sum())
            expected_average = group[metric].mean()
            age_only_ok &= group[f"{metric}_cohort_count"].eq(expected_count).all()
            if expected_count:
                age_only_ok &= group[f"{metric}_age_group_average"].eq(expected_average).all()
            if group["team_name"].nunique(dropna=False) > 1:
                team_independent &= group[f"{metric}_cohort_count"].eq(expected_count).all()
    record("age_group_is_only_cohort_key", age_only_ok, "Counts and averages recomputed by age group only")
    record("team_does_not_split_cohort", team_independent, "Multi-team age groups share the same cohort count")
    result = pd.DataFrame(checks)
    failures = result.loc[~result["passed"]]
    if not failures.empty:
        raise RuntimeError("Percentile sanity checks failed: " + ", ".join(failures["check"]))
    return result


def run_percentile_audit(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    config = load_config(project_root / "config/config.json")
    raw_audit = run_real_data_audit(project_root)
    result = build_age_group_percentiles(raw_audit["canonical"], config)  # type: ignore[arg-type]
    sanity = _sanity_checks(result.assessments, config)
    write_percentile_debug_outputs(result, project_root / "output")
    debug = project_root / "output/debug"
    sanity.to_csv(debug / "percentile_sanity_checks.csv", index=False)

    frame = result.assessments
    percentile_columns = [f"{metric}_percentile" for metric in METRIC_COLUMNS]
    available_per_athlete = frame[percentile_columns].notna().sum(axis=1)
    valid_age = frame["age_group"].notna() & frame["age_group"].astype(str).str.strip().ne("")
    age_sizes = frame.loc[valid_age].groupby("age_group").size().rename("athletes").reset_index()
    availability = pd.DataFrame({"metric": METRIC_COLUMNS,
        "percentile_available": [int(frame[f"{m}_percentile"].notna().sum()) for m in METRIC_COLUMNS],
        "percentile_missing": [int(frame[f"{m}_percentile"].isna().sum()) for m in METRIC_COLUMNS]})

    special: list[dict[str, object]] = []
    for age_group, group in frame.loc[valid_age].groupby("age_group"):
        for metric in METRIC_COLUMNS:
            values = group[metric].dropna()
            if len(values) == 1 or (len(values) > 1 and values.nunique() == 1):
                special.append({"age_group": age_group, "metric": metric, "valid_count": len(values),
                                "case": "n_equals_1" if len(values) == 1 else "all_identical"})
    special_frame = pd.DataFrame(special, columns=["age_group", "metric", "valid_count", "case"])
    special_frame.to_csv(debug / "percentile_special_cases.csv", index=False)
    availability.to_csv(debug / "percentile_availability.csv", index=False)

    representative = (frame.loc[valid_age].sort_values(["age_group", "full_name"])
                      .groupby("age_group", group_keys=False).head(2).head(10))
    representative.to_csv(debug / "representative_percentiles.csv", index=False)
    positive_counts = result.benchmarks.loc[result.benchmarks["valid_count"] > 0, "valid_count"]
    summary = {
        "athletes_with_age_group": int(valid_age.sum()),
        "athletes_without_age_group": int((~valid_age).sum()),
        "smallest_positive_metric_cohort": int(positive_counts.min()) if not positive_counts.empty else 0,
        "n_equals_1_cohorts": int((special_frame["case"] == "n_equals_1").sum()),
        "all_identical_cohorts": int((special_frame["case"] == "all_identical").sum()),
        "athletes_all_10_percentiles": int((available_per_athlete == 10).sum()),
        "athletes_partial_percentiles": int(((available_per_athlete > 0) & (available_per_athlete < 10)).sum()),
        "athletes_no_percentiles": int((available_per_athlete == 0).sum()),
    }
    pd.DataFrame([summary]).to_csv(debug / "percentile_audit_summary.csv", index=False)
    age_sizes.to_csv(debug / "age_group_sizes.csv", index=False)
    return {"summary": summary, "age_sizes": age_sizes, "benchmarks": result.benchmarks,
            "availability": availability, "representative": representative,
            "special_cases": special_frame, "sanity": sanity}


def main() -> int:
    audit = run_percentile_audit()
    print(pd.Series(audit["summary"]).to_string())
    print("\nAge-group sizes\n" + audit["age_sizes"].to_string(index=False))
    print("\nBenchmarks\n" + audit["benchmarks"].to_string(index=False))
    print("\nAvailability\n" + audit["availability"].to_string(index=False))
    print("\nSpecial cases\n" + audit["special_cases"].to_string(index=False))
    print("\nSanity checks\n" + audit["sanity"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
