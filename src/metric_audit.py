"""Run and persist the Phase 1 canonical-metric real-data audit."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .loader import load_hardware_csv, load_juggling_csv, load_roster_csv
from .config_loader import load_config
from .client_overrides import apply_roster_overrides
from .matcher import match_hardware_identities, match_juggling_identities
from .metric_extractor import (METRIC_COLUMNS, extract_canonical_assessments,
                               sprint_attempt_components, write_canonical_debug_output)
from .raw_schema import HARDWARE_RAW_SCHEMA, SOURCE_ROW_COLUMN
from .time_parser import parse_duration_to_seconds
from .validation import assign_issue_ids, issues_frame


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _winner_row(rows: pd.DataFrame, column: int, lowest: bool = True) -> object:
    parsed = rows[column].map(parse_duration_to_seconds)
    valid = parsed.dropna()
    if valid.empty:
        return pd.NA
    return rows.loc[valid.idxmin() if lowest else valid.idxmax(), SOURCE_ROW_COLUMN]


def _complete_sprint_winner(rows: pd.DataFrame, tolerance: float) -> object:
    candidates = [(row[SOURCE_ROW_COLUMN], item["total_time"])
                  for _, row in rows.iterrows()
                  if (item := sprint_attempt_components(row, tolerance))["complete_20y"]]
    return min(candidates, key=lambda value: value[1])[0] if candidates else pd.NA


def run_real_data_audit(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    config = load_config(project_root / "config/config.json")
    sprint_config = config.get("sprint_mapping", {})
    sprint_config = sprint_config if isinstance(sprint_config, dict) else {}
    tolerance = float(sprint_config.get("complete_attempt_tolerance_seconds", 0.01))
    hardware = load_hardware_csv(project_root / "data/hardware/STLDA 8_15 DATA - STLDA 8_15 Data.csv")
    raw_roster = load_roster_csv(project_root / "data/roster/STLDA MASTER COPY - Sheet1.csv")
    roster = apply_roster_overrides(raw_roster, config)
    juggling = load_juggling_csv(project_root / "data/juggling/Copy of STLDA Juggle Scores - Sheet1.csv")
    hardware_matches = match_hardware_identities(hardware, roster)
    juggling_matches = match_juggling_identities(juggling, roster)
    result = extract_canonical_assessments(
        hardware, roster, juggling, hardware_matches, juggling_matches,
        sprint_tolerance_seconds=tolerance,
    )
    debug = project_root / "output/debug"
    debug.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(roster.attrs.get("applied_client_overrides", [])).to_csv(
        debug / "applied_client_overrides.csv", index=False)
    write_canonical_debug_output(result.canonical, project_root / "output")
    issues = issues_frame(assign_issue_ids(result.issues))
    issues.to_csv(debug / "metric_extraction_issues.csv", index=False)

    availability = pd.DataFrame({
        "metric": METRIC_COLUMNS,
        "available": [int(result.canonical[m].notna().sum()) for m in METRIC_COLUMNS],
        "missing": [int(result.canonical[m].isna().sum()) for m in METRIC_COLUMNS],
    })
    availability.to_csv(debug / "metric_availability.csv", index=False)

    representative = result.canonical.sort_values(
        by=list(METRIC_COLUMNS), key=lambda column: column.isna()
    ).head(10)
    representative.to_csv(debug / "representative_metrics.csv", index=False)

    sprint_examples: list[dict[str, object]] = []
    figure_examples: list[dict[str, object]] = []
    prepared = result.hardware_attempts
    for (roster_row, date), group in prepared.groupby(["_roster_row", "_assessment_date"]):
        sprint = group.loc[group["_canonical_drill"] == "sprints"]
        if len(sprint) > 1:
            labels = sorted(set(str(v) for v in sprint[HARDWARE_RAW_SCHEMA.drill_name_index]))
            row10 = _winner_row(sprint, HARDWARE_RAW_SCHEMA.sprint_first_split_index)
            row20 = _complete_sprint_winner(sprint, tolerance)
            sprint_examples.append({"roster_row": roster_row, "assessment_date": date,
                "athlete": sprint.iloc[0][HARDWARE_RAW_SCHEMA.athlete_name_index],
                "attempts": len(sprint), "labels": "|".join(labels),
                "dash_10y_source_row": row10, "dash_20y_source_row": row20,
                "metrics_from_different_attempts": row10 != row20})
        figure = group.loc[group["_canonical_drill"] == "figure8"]
        valid_count = sum(parse_duration_to_seconds(v) is not None
                          for v in figure.get(HARDWARE_RAW_SCHEMA.total_time_index, []))
        if valid_count >= 2:
            figure_examples.append({"roster_row": roster_row, "assessment_date": date,
                "athlete": figure.iloc[0][HARDWARE_RAW_SCHEMA.athlete_name_index],
                "valid_attempts": valid_count,
                "best_source_row": _winner_row(figure, HARDWARE_RAW_SCHEMA.total_time_index),
                "worst_source_row": _winner_row(figure, HARDWARE_RAW_SCHEMA.total_time_index, False)})
    sprint_frame = pd.DataFrame(sprint_examples)
    figure_frame = pd.DataFrame(figure_examples)
    sprint_frame.to_csv(debug / "sprint_merge_examples.csv", index=False)
    figure_frame.to_csv(debug / "figure8_min_max_examples.csv", index=False)
    result.canonical.loc[result.canonical["juggling_dominant"].isna()].head(10).to_csv(
        debug / "missing_juggling_examples.csv", index=False)

    excluded = hardware_matches.loc[~hardware_matches["status"].isin({"exact_name_email", "unique_name_fallback"})]
    excluded.to_csv(debug / "excluded_hardware_identities.csv", index=False)
    mixed_sprint_groups = sprint_frame.loc[sprint_frame.get("labels", pd.Series(dtype=object)) == "Sprints|Sprints Assessments"]
    summary: dict[str, object] = {
        "matched_athlete_assessments": len(result.canonical),
        "sprint_attempts_merged": int(len(prepared.loc[prepared["_canonical_drill"] == "sprints"])),
        "sprint_attempts_in_mixed_label_groups": int(pd.to_numeric(
            mixed_sprint_groups.get("attempts", pd.Series(dtype=float)), errors="coerce").sum()),
        "athletes_with_both_sprint_labels": len(mixed_sprint_groups),
        "athletes_with_one_figure8_attempt": int(sum(i.category == "single_figure8_attempt" for i in result.issues)),
        "athletes_with_3plus_figure8_attempts": int(sum(int(v) >= 3 for v in figure_frame.get("valid_attempts", []))),
        "invalid_required_metric_values": int(sum(i.category == "invalid_required_metric_value" for i in result.issues)),
        "excluded_unmatched_hardware_identities": len(excluded),
    }
    pd.DataFrame([summary]).to_csv(debug / "metric_audit_summary.csv", index=False)
    return {"summary": summary, "availability": availability, "representative": representative,
            "canonical": result.canonical,
            "hardware_attempts": result.hardware_attempts,
            "sprint_examples": sprint_frame, "figure_examples": figure_frame, "issues": issues}


def main() -> int:
    audit = run_real_data_audit()
    print(pd.Series(audit["summary"]).to_string())
    print("\nAvailability\n" + audit["availability"].to_string(index=False))
    print("\nRepresentative records\n" + audit["representative"].to_string(index=False))
    print("\nSprint examples\n" + audit["sprint_examples"].head(10).to_string(index=False))
    print("\nFigure 8 examples\n" + audit["figure_examples"].head(10).to_string(index=False))
    print("\nMetric extraction issues\n" + audit["issues"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
