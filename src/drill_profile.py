"""Evidence-only positional profiling by canonical hardware drill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .config_loader import load_config
from .drill_normalizer import drill_aliases_from_config, normalize_drill_name
from .loader import load_hardware_csv
from .raw_schema import HARDWARE_RAW_SCHEMA, SOURCE_ROW_COLUMN
from .time_parser import parse_duration_to_seconds


PROFILE_COLUMNS = tuple(range(11, 34))
EVENT_COLUMNS = tuple(range(20, 34))
COUNTER_COLUMNS = tuple(range(13, 20))


def _pattern(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return "empty"
    if values.map(lambda value: parse_duration_to_seconds(value) is not None).all():
        return "duration"
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all():
        return "integer" if (numeric % 1 == 0).all() else "numeric"
    return "text/mixed"


def profile_drills(hardware: pd.DataFrame,
                   aliases: dict[str, str]) -> dict[str, object]:
    """Summarize raw fields without assigning metric semantics."""
    frame = hardware.copy()
    frame["_canonical_drill"] = frame[HARDWARE_RAW_SCHEMA.drill_name_index].map(
        lambda value: normalize_drill_name(value, aliases)
    )
    profiles: dict[str, object] = {}
    for canonical, rows in frame.dropna(subset=["_canonical_drill"]).groupby("_canonical_drill"):
        event_counts = rows[list(EVENT_COLUMNS)].notna().sum(axis=1)
        completeness = rows[list(PROFILE_COLUMNS)].notna().sum(axis=1)
        representatives = rows.loc[completeness.sort_values(ascending=False).index[:3]]
        column_profiles: dict[str, object] = {}
        for column in PROFILE_COLUMNS:
            values = rows[column].dropna()
            column_profiles[str(column)] = {
                "non_null_count": int(values.size),
                "pattern": _pattern(rows[column]),
                "examples": list(dict.fromkeys(values.astype(str).tolist()))[:8],
            }
        counters: dict[str, object] = {}
        for column in COUNTER_COLUMNS:
            values = pd.to_numeric(rows[column], errors="coerce").dropna()
            counters[str(column)] = {
                "non_null_count": int(rows[column].notna().sum()),
                "unique_values": sorted(values.unique().tolist())[:30],
                "min": float(values.min()) if not values.empty else None,
                "max": float(values.max()) if not values.empty else None,
            }
        profiles[str(canonical)] = {
            "raw_drill_names": sorted(rows[HARDWARE_RAW_SCHEMA.drill_name_index].dropna().unique().tolist()),
            "row_count": len(rows),
            "populated_columns": [int(c) for c in range(34) if rows[c].notna().any()],
            "timing_event_entries_min": int(event_counts.min()),
            "timing_event_entries_max": int(event_counts.max()),
            "timing_event_entries_median": float(event_counts.median()),
            "columns_11_33": column_profiles,
            "counters_13_19": counters,
            "representative_complete_rows": representatives[
                [SOURCE_ROW_COLUMN, HARDWARE_RAW_SCHEMA.drill_name_index, *PROFILE_COLUMNS]
            ].to_dict("records"),
        }
    return profiles


def run_profile(project_root: Path) -> dict[str, object]:
    root = Path(project_root)
    config = load_config(root / "config/config.json")
    aliases = drill_aliases_from_config(config)
    hardware = load_hardware_csv(root / "data/hardware/STLDA 8_15 DATA - STLDA 8_15 Data.csv")
    return {"drill_aliases": aliases, "profiles": profile_drills(hardware, aliases)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    print(json.dumps(run_profile(args.project_root), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
