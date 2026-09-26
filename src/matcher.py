"""Deterministic roster-authoritative athlete identity matching."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd

from .normalizer import normalize_email, normalize_name
from .raw_schema import HARDWARE_RAW_SCHEMA, SOURCE_ROW_COLUMN


class MatchStatus:
    EXACT_NAME_EMAIL: Final[str] = "exact_name_email"
    UNIQUE_NAME_FALLBACK: Final[str] = "unique_name_fallback"
    UNIQUE_NAME_MATCH: Final[str] = "unique_name_match"
    AMBIGUOUS_NAME: Final[str] = "ambiguous_name"
    NAME_EMAIL_CONFLICT: Final[str] = "name_email_conflict"
    UNMATCHED: Final[str] = "unmatched"
    INVALID_IDENTITY: Final[str] = "invalid_identity"


RESULT_COLUMNS: Final[list[str]] = [
    "source", "source_row", "source_name", "source_email",
    "normalized_source_name", "normalized_source_email",
    "matched_roster_row", "matched_full_name", "matched_email",
    "matched_team", "matched_age_group", "match_method", "status", "reason",
]


def _full_name(first: object, last: object) -> str | None:
    parts = []
    for value in (first, last):
        if not pd.isna(value) and str(value).strip():
            parts.append(str(value).strip())
    return " ".join(parts) or None


def build_canonical_roster(roster: pd.DataFrame) -> pd.DataFrame:
    """Create the roster-authoritative identity view without changing input data."""
    records: list[dict[str, object]] = []
    for _, row in roster.iterrows():
        full_name = _full_name(row["First Name"], row["Last Name"])
        records.append({
            "roster_row": row[SOURCE_ROW_COLUMN],
            "first_name": row["First Name"],
            "last_name": row["Last Name"],
            "full_name": full_name,
            "normalized_name": normalize_name(full_name),
            "email": row["Parent Contact"],
            "normalized_email": normalize_email(row["Parent Contact"]),
            "birthday": row["Birthday"],
            "age_group": row["Age Group"],
            "gender": row["Gender"],
            "team_name": row["Team Name"],
        })
    return pd.DataFrame.from_records(records)


def _base_result(source: str, source_row: object, name: object, email: object) -> dict[str, object]:
    return {
        "source": source,
        "source_row": source_row,
        "source_name": name,
        "source_email": email,
        "normalized_source_name": normalize_name(name),
        "normalized_source_email": normalize_email(email),
        "matched_roster_row": pd.NA,
        "matched_full_name": pd.NA,
        "matched_email": pd.NA,
        "matched_team": pd.NA,
        "matched_age_group": pd.NA,
        "match_method": pd.NA,
        "status": pd.NA,
        "reason": pd.NA,
    }


def _accept(result: dict[str, object], athlete: pd.Series, status: str, reason: str) -> None:
    result.update({
        "matched_roster_row": athlete["roster_row"],
        "matched_full_name": athlete["full_name"],
        "matched_email": athlete["email"],
        "matched_team": athlete["team_name"],
        "matched_age_group": athlete["age_group"],
        "match_method": status,
        "status": status,
        "reason": reason,
    })


def _match_hardware_identity(name: object, email: object, source_row: object,
                             canonical: pd.DataFrame) -> dict[str, object]:
    result = _base_result("hardware", source_row, name, email)
    norm_name = result["normalized_source_name"]
    norm_email = result["normalized_source_email"]
    if norm_name is None:
        result.update(status=MatchStatus.INVALID_IDENTITY, reason="Source athlete name is missing or blank")
        return result

    name_rows = canonical.loc[canonical["normalized_name"] == norm_name]
    exact_rows = name_rows.loc[name_rows["normalized_email"] == norm_email] if norm_email else canonical.iloc[0:0]
    if len(exact_rows) == 1:
        _accept(result, exact_rows.iloc[0], MatchStatus.EXACT_NAME_EMAIL,
                "Normalized name and email uniquely match the roster")
        return result
    if len(exact_rows) > 1:
        result.update(status=MatchStatus.AMBIGUOUS_NAME,
                      reason="Normalized name and email match multiple roster rows")
        return result

    if len(name_rows) == 1 and norm_email is not None:
        email_rows = canonical.loc[canonical["normalized_email"] == norm_email]
        if not email_rows.empty and not (email_rows["normalized_name"] == norm_name).any():
            result.update(status=MatchStatus.NAME_EMAIL_CONFLICT,
                          reason="Name uniquely identifies one roster athlete, but email belongs only to other roster athlete(s)")
            return result

    if len(name_rows) == 1:
        _accept(result, name_rows.iloc[0], MatchStatus.UNIQUE_NAME_FALLBACK,
                "No unique name-and-email match; normalized name uniquely matches the roster")
    elif name_rows.empty:
        result.update(status=MatchStatus.UNMATCHED, reason="Normalized name was not found in the roster")
    else:
        result.update(status=MatchStatus.AMBIGUOUS_NAME, reason="Normalized name matches multiple roster rows")
    return result


def match_hardware_identities(hardware: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    """Match each unique raw hardware name/email identity to the roster."""
    canonical = build_canonical_roster(roster)
    name_col = HARDWARE_RAW_SCHEMA.athlete_name_index
    email_col = HARDWARE_RAW_SCHEMA.athlete_email_index
    identities = hardware[[SOURCE_ROW_COLUMN, name_col, email_col]].drop_duplicates(
        subset=[name_col, email_col], keep="first"
    )
    records = [
        _match_hardware_identity(row[name_col], row[email_col], row[SOURCE_ROW_COLUMN], canonical)
        for _, row in identities.iterrows()
    ]
    return pd.DataFrame.from_records(records, columns=RESULT_COLUMNS)


def match_juggling_identities(juggling: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    """Match each unique juggling name to exactly one canonical roster athlete."""
    canonical = build_canonical_roster(roster)
    source = juggling.copy()
    source["_full_name"] = [
        _full_name(first, last) for first, last in zip(source["First Name"], source["Last Name"])
    ]
    identities = source[[SOURCE_ROW_COLUMN, "_full_name"]].drop_duplicates(subset=["_full_name"], keep="first")
    records: list[dict[str, object]] = []
    for _, row in identities.iterrows():
        result = _base_result("juggling", row[SOURCE_ROW_COLUMN], row["_full_name"], pd.NA)
        norm_name = result["normalized_source_name"]
        if norm_name is None:
            result.update(status=MatchStatus.INVALID_IDENTITY, reason="Source athlete name is missing or blank")
        else:
            matches = canonical.loc[canonical["normalized_name"] == norm_name]
            if len(matches) == 1:
                _accept(result, matches.iloc[0], MatchStatus.UNIQUE_NAME_MATCH,
                        "Normalized full name uniquely matches the roster")
            elif matches.empty:
                result.update(status=MatchStatus.UNMATCHED, reason="Normalized name was not found in the roster")
            else:
                result.update(status=MatchStatus.AMBIGUOUS_NAME, reason="Normalized name matches multiple roster rows")
        records.append(result)
    return pd.DataFrame.from_records(records, columns=RESULT_COLUMNS)


def write_matching_debug_outputs(hardware_results: pd.DataFrame,
                                 juggling_results: pd.DataFrame,
                                 output_directory: Path) -> tuple[Path, Path]:
    """Write development-only identity audit files under output/debug."""
    debug = Path(output_directory) / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    hardware_path = debug / "hardware_matching.csv"
    juggling_path = debug / "juggling_matching.csv"
    hardware_results.to_csv(hardware_path, index=False)
    juggling_results.to_csv(juggling_path, index=False)
    return hardware_path, juggling_path
