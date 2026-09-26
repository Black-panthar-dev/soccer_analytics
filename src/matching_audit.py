"""Run deterministic identity matching and write development audit CSVs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .loader import load_hardware_csv, load_juggling_csv, load_roster_csv
from .config_loader import load_config
from .client_overrides import apply_roster_overrides
from .matcher import (
    MatchStatus,
    match_hardware_identities,
    match_juggling_identities,
    write_matching_debug_outputs,
)


def run_matching_audit(project_root: Path) -> dict[str, object]:
    root = Path(project_root)
    config = load_config(root / "config/config.json")
    hardware = load_hardware_csv(root / "data/hardware/STLDA 8_15 DATA - STLDA 8_15 Data.csv")
    roster = apply_roster_overrides(
        load_roster_csv(root / "data/roster/STLDA MASTER COPY - Sheet1.csv"), config)
    juggling = load_juggling_csv(root / "data/juggling/Copy of STLDA Juggle Scores - Sheet1.csv")
    hardware_results = match_hardware_identities(hardware, roster)
    juggling_results = match_juggling_identities(juggling, roster)
    hardware_path, juggling_path = write_matching_debug_outputs(
        hardware_results, juggling_results, root / "output"
    )
    unresolved_statuses = {
        MatchStatus.AMBIGUOUS_NAME, MatchStatus.NAME_EMAIL_CONFLICT,
        MatchStatus.UNMATCHED, MatchStatus.INVALID_IDENTITY,
    }
    unresolved = hardware_results.loc[hardware_results["status"].isin(unresolved_statuses)]
    unresolved_juggling = juggling_results.loc[juggling_results["status"].isin(unresolved_statuses)]
    return {
        "hardware": {
            "unique_identities": len(hardware_results),
            "status_counts": hardware_results["status"].value_counts().to_dict(),
            "unresolved": unresolved[["source_name", "source_email", "status", "reason"]].to_dict("records"),
            "debug_output": str(hardware_path),
        },
        "juggling": {
            "unique_identities": len(juggling_results),
            "status_counts": juggling_results["status"].value_counts().to_dict(),
            "unresolved": unresolved_juggling[["source_name", "source_email", "status", "reason"]].to_dict("records"),
            "debug_output": str(juggling_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    print(json.dumps(run_matching_audit(args.project_root), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
