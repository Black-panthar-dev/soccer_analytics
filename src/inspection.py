"""Non-mutating inspection reports for Phase 1 input files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .loader import load_hardware_csv, load_juggling_csv, load_roster_csv
from .raw_schema import SOURCE_ROW_COLUMN


# These are inspection candidates from the supplied specification, not final mappings.
OBSERVED_HARDWARE_COLUMNS = {
    "athlete_name": 1,
    "email": 2,
    "drill": 3,
    "team_text": 7,
    "date_time": 10,
}

_DURATION_PATTERN = re.compile(
    r"^\s*(?:\d+(?:\.\d+)?\s*s)?\s*(?:\d+\s*ms)?\s*$", re.IGNORECASE
)


def _non_missing_text(series: pd.Series) -> pd.Series:
    return series.dropna().astype(str)


def infer_likely_type(series: pd.Series) -> str:
    """Infer a descriptive type without converting or assigning semantics."""
    values = _non_missing_text(series)
    if values.empty:
        return "empty"
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all():
        integral = (numeric % 1 == 0).all()
        return "integer-like" if integral else "numeric-like"
    if values.map(lambda value: bool(_DURATION_PATTERN.fullmatch(value))).all():
        return "duration-like text"
    parsed_dates = pd.to_datetime(values, errors="coerce", format="mixed")
    if parsed_dates.notna().mean() >= 0.9:
        return "date/time-like text"
    if numeric.notna().any():
        return "mixed numeric/text"
    return "text"


def profile_hardware_columns(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Return a profile for every positional hardware column."""
    profiles: list[dict[str, Any]] = []
    for column in (item for item in frame.columns if isinstance(item, int)):
        values = _non_missing_text(frame[column])
        examples = list(dict.fromkeys(values.tolist()))[:8]
        profiles.append(
            {
                "index": column,
                "non_null_count": int(frame[column].notna().sum()),
                "sample_values": examples[:5],
                "unique_examples": examples,
                "unique_count": int(values.nunique()),
                "likely_type": infer_likely_type(frame[column]),
            }
        )
    return profiles


def inspect_hardware(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarize raw hardware structure using observation-only candidates."""
    name_column = OBSERVED_HARDWARE_COLUMNS["athlete_name"]
    drill_column = OBSERVED_HARDWARE_COLUMNS["drill"]
    drill_values = sorted(_non_missing_text(frame[drill_column]).unique().tolist())
    samples_by_drill: dict[str, list[dict[str, Any]]] = {}
    for drill in drill_values:
        rows = frame.loc[frame[drill_column].astype("string") == drill].head(2)
        samples_by_drill[drill] = rows.to_dict(orient="records")
    return {
        "row_count": len(frame),
        "column_count": len([column for column in frame if isinstance(column, int)]),
        "unique_athlete_count_observed": int(frame[name_column].dropna().nunique()),
        "unique_drill_names_observed": drill_values,
        "sample_rows_by_drill": samples_by_drill,
        "column_profiles": profile_hardware_columns(frame),
        "candidate_columns_observation_only": OBSERVED_HARDWARE_COLUMNS,
    }


def _full_names(frame: pd.DataFrame) -> pd.Series:
    first = frame["First Name"].astype("string").str.strip()
    last = frame["Last Name"].astype("string").str.strip()
    return (first.fillna("") + " " + last.fillna("")).str.strip().replace("", pd.NA)


def inspect_roster(frame: pd.DataFrame) -> dict[str, Any]:
    """Return the requested roster data-quality summary."""
    names = _full_names(frame)
    return {
        "row_count": len(frame),
        "full_name_count": int(names.notna().sum()),
        "unique_age_groups": sorted(_non_missing_text(frame["Age Group"]).unique()),
        "unique_teams": sorted(_non_missing_text(frame["Team Name"]).unique()),
        "duplicate_full_name_count": int(names.duplicated(keep=False).sum()),
        "missing_parent_contact_count": int(frame["Parent Contact"].isna().sum()),
        "missing_birthday_count": int(frame["Birthday"].isna().sum()),
        "invalid_birthday_count": int(
            (frame["Birthday"].notna() & frame["_birthday_parsed"].isna()).sum()
        ),
    }


def inspect_juggling(frame: pd.DataFrame) -> dict[str, Any]:
    """Return the requested juggling data-quality summary."""
    names = _full_names(frame)
    return {
        "row_count": len(frame),
        "duplicate_full_name_count": int(names.duplicated(keep=False).sum()),
        "missing_dominant_count": int(frame["Dominant"].isna().sum()),
        "missing_non_dominant_count": int(frame["Non-Dominant"].isna().sum()),
        "missing_thighs_count": int(frame["Thighs"].isna().sum()),
    }


def inspect_sources(project_root: Path) -> dict[str, Any]:
    """Load and inspect all configured development source paths."""
    root = Path(project_root)
    hardware = load_hardware_csv(
        root / "data/hardware/STLDA 8_15 DATA - STLDA 8_15 Data.csv"
    )
    roster = load_roster_csv(root / "data/roster/STLDA MASTER COPY - Sheet1.csv")
    juggling = load_juggling_csv(
        root / "data/juggling/Copy of STLDA Juggle Scores - Sheet1.csv"
    )
    return {
        "hardware": inspect_hardware(hardware),
        "roster": inspect_roster(roster),
        "juggling": inspect_juggling(juggling),
    }


def main() -> int:
    """Print a JSON inspection report without writing generated artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    args = parser.parse_args()
    print(json.dumps(inspect_sources(args.project_root), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
