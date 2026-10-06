"""Generate honest real-data Phase II history and delta audit outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .assessment_history import (
    AGE_GROUP_SOURCE, ASSESSMENT_DATE_SOURCE, JUGGLING_DATE_LIMITATION,
    assessments_from_canonical, get_assessments_for_athlete,
    get_latest_assessment, get_previous_assessment,
)
from .client_overrides import apply_roster_overrides
from .config_loader import load_config
from .loader import load_hardware_csv, load_juggling_csv, load_roster_csv
from .matcher import build_canonical_roster, match_hardware_identities, match_juggling_identities
from .metric_extractor import METRIC_COLUMNS, extract_canonical_assessments
from .performance_delta import delta_records


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_phase2_audit(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = Path(project_root)
    config = load_config(root / "config/config.json")
    paths = config["paths"]
    inputs = config["input_files"]
    hardware = load_hardware_csv(root / paths["hardware_input"] / inputs["hardware"])
    roster = apply_roster_overrides(
        load_roster_csv(root / paths["roster_input"] / inputs["roster"]), config)
    juggling = load_juggling_csv(root / paths["juggling_input"] / inputs["juggling"])
    result = extract_canonical_assessments(
        hardware, roster, juggling,
        match_hardware_identities(hardware, roster), match_juggling_identities(juggling, roster),
        sprint_tolerance_seconds=float(config["sprint_mapping"]["complete_attempt_tolerance_seconds"]),
    )
    assessments = assessments_from_canonical(result.canonical)
    audit_rows: list[dict[str, object]] = []
    for item in assessments:
        row = {
            "athlete_id": item.athlete_id, "athlete": item.athlete_name,
            "assessment_date": item.assessment_date, "age_group": item.age_group,
            "team": item.team, "age_group_source": AGE_GROUP_SOURCE,
            "assessment_date_source": ASSESSMENT_DATE_SOURCE,
        }
        row.update(item.raw_metrics)
        row.update({f"{metric}_available": item.availability[metric] for metric in METRIC_COLUMNS})
        row.update({f"source_{key}": value for key, value in item.source_metadata.items()
                    if key != "assessment_date_source"})
        audit_rows.append(row)

    delta_rows: list[dict[str, object]] = []
    roster_ids = build_canonical_roster(roster)["roster_row"].tolist()
    distribution = {"0": 0, "1": 0, "2+": 0}
    for athlete_id in roster_ids:
        history = get_assessments_for_athlete(assessments, athlete_id)
        distribution["0" if not history else "1" if len(history) == 1 else "2+"] += 1
        latest = get_latest_assessment(history)
        if latest is not None:
            delta_rows.extend(delta_records(latest, get_previous_assessment(history)))

    output = root / "output/phase2/debug"
    output.mkdir(parents=True, exist_ok=True)
    history_path = output / "historical_assessment_audit.csv"
    delta_path = output / "delta_audit.csv"
    pd.DataFrame(audit_rows).to_csv(history_path, index=False)
    pd.DataFrame(delta_rows).to_csv(delta_path, index=False)
    summary = {
        "roster_athletes": len(roster_ids), "historical_assessment_records": len(assessments),
        "athletes_0_assessments": distribution["0"], "athletes_1_assessment": distribution["1"],
        "athletes_2plus_assessments": distribution["2+"],
        "distinct_assessment_dates": len({item.assessment_date for item in assessments}),
        "assessment_date_source": ASSESSMENT_DATE_SOURCE,
        "age_group_source": AGE_GROUP_SOURCE,
        "juggling_date_limitation": JUGGLING_DATE_LIMITATION,
    }
    pd.DataFrame([summary]).to_csv(output / "phase2_audit_summary.csv", index=False)
    return {"summary": summary, "assessments": assessments, "deltas": delta_rows,
            "history_path": history_path, "delta_path": delta_path}


def main() -> int:
    result = run_phase2_audit()
    print(pd.Series(result["summary"]).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
