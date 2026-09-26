"""Focused completeness audit for corrected sprint extraction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config_loader import load_config
from .metric_audit import PROJECT_ROOT, run_real_data_audit
from .metric_extractor import sprint_attempt_components
from .percentile_audit import run_percentile_audit
from .raw_schema import HARDWARE_RAW_SCHEMA, SOURCE_ROW_COLUMN


def run_sprint_audit(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    debug = project_root / "output/debug"
    old_path = debug / "canonical_metrics.csv"
    baseline_path = debug / "canonical_metrics_pre_sprint_correction.csv"
    changes_path = debug / "sprint_20y_changes.csv"
    if baseline_path.is_file():
        old = pd.read_csv(baseline_path)
    elif old_path.is_file():
        old = pd.read_csv(old_path)
        # Recover the original values when an earlier audit run already rewrote canonical output.
        if changes_path.is_file():
            prior_changes = pd.read_csv(changes_path)
            old = old.merge(prior_changes[["roster_row", "old_dash_20y"]],
                            on="roster_row", how="left")
            old["dash_20y"] = old["old_dash_20y"].combine_first(old["dash_20y"])
            old = old.drop(columns="old_dash_20y")
        old.to_csv(baseline_path, index=False)
    else:
        old = pd.DataFrame()
    config = load_config(project_root / "config/config.json")
    sprint_config = config.get("sprint_mapping", {})
    sprint_config = sprint_config if isinstance(sprint_config, dict) else {}
    tolerance = float(sprint_config.get("complete_attempt_tolerance_seconds", 0.01))

    raw_audit = run_real_data_audit(project_root)
    corrected = raw_audit["canonical"]
    attempts = raw_audit["hardware_attempts"]
    sprint = attempts.loc[attempts["_canonical_drill"] == "sprints"]
    attempt_records: list[dict[str, object]] = []
    for _, row in sprint.iterrows():
        item = sprint_attempt_components(row, tolerance)
        item.update({"source_row": row[SOURCE_ROW_COLUMN], "roster_row": row["_roster_row"],
                     "athlete": row[HARDWARE_RAW_SCHEMA.athlete_name_index],
                     "assessment_date": row["_assessment_date"],
                     "source_label": row[HARDWARE_RAW_SCHEMA.drill_name_index]})
        item["all_fields_valid"] = all(item[key] is not None
                                        for key in ("first_split", "second_split", "total_time"))
        item["inconsistent_total"] = bool(item["all_fields_valid"] and not item["complete_20y"])
        attempt_records.append(item)
    attempt_frame = pd.DataFrame(attempt_records)
    attempt_frame.to_csv(debug / "sprint_completeness_audit.csv", index=False)

    new = corrected[["roster_row", "assessment_date", "full_name", "dash_10y", "dash_20y"]].copy()
    new["assessment_date"] = new["assessment_date"].astype(str)
    if old.empty:
        changes = new.assign(old_dash_20y=float("nan"), changed=True)
    else:
        previous = old[["roster_row", "assessment_date", "dash_20y"]].rename(
            columns={"dash_20y": "old_dash_20y"})
        previous["assessment_date"] = previous["assessment_date"].astype(str)
        changes = new.merge(previous, on=["roster_row", "assessment_date"], how="left")
        same_numeric = changes["dash_20y"].sub(changes["old_dash_20y"]).abs().le(1e-12)
        changes["changed"] = ~(
            same_numeric |
            (changes["dash_20y"].isna() & changes["old_dash_20y"].isna())
        )
    changed = changes.loc[changes["changed"]].copy()
    changed.to_csv(debug / "sprint_20y_changes.csv", index=False)

    label_summary = attempt_frame.groupby("source_label").agg(
        total_attempts=("source_row", "count"),
        complete_20y_attempts=("complete_20y", "sum"),
        inconsistent_attempts=("inconsistent_total", "sum"),
    ).reset_index()
    label_summary["incomplete_attempts"] = (
        label_summary["total_attempts"] - label_summary["complete_20y_attempts"])
    label_summary.to_csv(debug / "sprint_completeness_by_label.csv", index=False)

    invalid_relationship = new.loc[new["dash_20y"].notna() & new["dash_10y"].notna()
                                   & new["dash_20y"].le(new["dash_10y"])]
    invalid_relationship.to_csv(debug / "sprint_20y_not_greater_than_10y.csv", index=False)
    percentile_audit = run_percentile_audit(project_root)
    summary = {
        "total_sprint_attempts": len(attempt_frame),
        "complete_20y_attempts": int(attempt_frame["complete_20y"].sum()),
        "incomplete_attempts": int((~attempt_frame["complete_20y"]).sum()),
        "athletes_affected_by_incomplete_attempts": int(
            attempt_frame.loc[~attempt_frame["complete_20y"], "roster_row"].nunique()),
        "athletes_with_changed_dash_20y": len(changed),
        "athletes_now_missing_dash_20y": int(
            (changed["old_dash_20y"].notna() & changed["dash_20y"].isna()).sum()),
        "remaining_dash_20y_le_dash_10y": len(invalid_relationship),
        "inconsistent_split_sum_attempts": int(attempt_frame["inconsistent_total"].sum()),
    }
    pd.DataFrame([summary]).to_csv(debug / "sprint_correction_summary.csv", index=False)
    return {"summary": summary, "changes": changed, "by_label": label_summary,
            "inconsistent": attempt_frame.loc[attempt_frame["inconsistent_total"]],
            "invalid_relationship": invalid_relationship,
            "percentile_audit": percentile_audit}


def main() -> int:
    audit = run_sprint_audit()
    print(pd.Series(audit["summary"]).to_string())
    print("\nBy sprint label\n" + audit["by_label"].to_string(index=False))
    print("\nChanged 20Y values\n" + audit["changes"].to_string(index=False))
    print("\nInconsistent attempts\n" + audit["inconsistent"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
