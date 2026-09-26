"""Run the Phase 1 validation audit and write CSV outputs."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config_loader import load_config
from .client_overrides import apply_roster_overrides
from .drill_normalizer import drill_aliases_from_config
from .loader import load_hardware_csv, load_juggling_csv, load_roster_csv
from .main import configure_logging
from .matcher import MatchStatus, build_canonical_roster, match_hardware_identities, match_juggling_identities
from .validation import (
    Severity, assign_issue_ids, is_athlete_report_eligible, validate_filenames,
    validate_hardware, validate_identity, validate_juggling, validate_logos,
    validate_roster, write_validation_outputs,
)


def run_validation_audit(project_root: Path) -> dict[str, object]:
    root = Path(project_root)
    config = load_config(root / "config/config.json")
    hardware = load_hardware_csv(root / "data/hardware/STLDA 8_15 DATA - STLDA 8_15 Data.csv")
    roster = apply_roster_overrides(
        load_roster_csv(root / "data/roster/STLDA MASTER COPY - Sheet1.csv"), config)
    juggling = load_juggling_csv(root / "data/juggling/Copy of STLDA Juggle Scores - Sheet1.csv")
    hardware_matches = match_hardware_identities(hardware, roster)
    juggling_matches = match_juggling_identities(juggling, roster)
    canonical = build_canonical_roster(roster)

    issues = assign_issue_ids([
        *validate_identity(hardware_matches, juggling_matches),
        *validate_roster(roster),
        *validate_hardware(hardware, hardware_matches, drill_aliases=drill_aliases_from_config(config)),
        *validate_juggling(juggling),
        *validate_logos(config, root),
        *validate_filenames(canonical),
    ])
    summary_path, details_path = write_validation_outputs(issues, root / "output")

    accepted = hardware_matches.loc[hardware_matches["status"].isin(
        [MatchStatus.EXACT_NAME_EMAIL, MatchStatus.UNIQUE_NAME_FALLBACK]
    )]
    eligible_rows: set[int] = set()
    blocked: list[dict[str, object]] = []
    for value in accepted["matched_roster_row"].dropna().unique():
        roster_row = int(value)
        eligible, reasons = is_athlete_report_eligible(roster_row, issues)
        if eligible:
            eligible_rows.add(roster_row)
        else:
            athlete = canonical.loc[canonical["roster_row"] == roster_row, "full_name"].iloc[0]
            blocked.append({"athlete_name": athlete, "roster_row": roster_row, "reasons": reasons})
    for issue in issues:
        if issue.blocks_report and issue.roster_row is None:
            blocked.append({"athlete_name": issue.athlete_name, "source_row": issue.source_row,
                            "source": issue.source, "reasons": [issue.message]})

    counts = lambda frame: frame["status"].value_counts().to_dict()
    categories: dict[str, int] = {}
    for issue in issues:
        if issue.severity == Severity.WARNING:
            categories[issue.category] = categories.get(issue.category, 0) + 1
    result = {
        "roster_athletes": len(canonical),
        "hardware_athletes": len(hardware_matches),
        "juggling_athletes": len(juggling_matches),
        "hardware_matches": counts(hardware_matches),
        "juggling_matches": counts(juggling_matches),
        "missing_birthday": sum(i.category == "missing_birthday" for i in issues),
        "missing_age_group": sum(i.category == "missing_age_group" for i in issues),
        "missing_team": sum(i.category == "missing_team" for i in issues),
        "missing_juggling_dominant": sum(i.category == "missing_juggling_dominant" for i in issues),
        "missing_juggling_non_dominant": sum(i.category == "missing_juggling_non_dominant" for i in issues),
        "missing_juggling_thighs": sum(i.category == "missing_juggling_thighs" for i in issues),
        "missing_all_juggling": sum(i.category == "missing_all_juggling" for i in issues),
        "multiple_assessment_date_athletes": sum(i.category == "multiple_assessment_dates" for i in issues),
        "report_eligible_athletes": len(eligible_rows),
        "blocking_athletes": blocked,
        "non_blocking_warning_count": sum(i.severity == Severity.WARNING and not i.blocks_report for i in issues),
        "warning_counts_by_category": categories,
        "filename_collisions": sum(i.category == "filename_collision" for i in issues),
        "validation_summary": str(summary_path),
        "validation_details": str(details_path),
    }
    logging.getLogger(__name__).info("Validation audit complete: %s", json.dumps(result, default=str))
    return result


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    print(json.dumps(run_validation_audit(args.project_root), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
