"""Explicit client-confirmed overlays applied without mutating source CSV data."""

from __future__ import annotations

import pandas as pd

from .normalizer import normalize_name


def apply_roster_overrides(roster: pd.DataFrame,
                           config: dict[str, object]) -> pd.DataFrame:
    """Return an overridden copy of the roster and preserve the input unchanged."""
    result = roster.copy(deep=True)
    client = config.get("client_overrides", {})
    client = client if isinstance(client, dict) else {}
    overrides = client.get("roster_age_groups", [])
    if overrides is None:
        overrides = []
    if not isinstance(overrides, list):
        raise ValueError("client_overrides.roster_age_groups must be a list")
    names = (result["First Name"].fillna("").astype(str).str.strip() + " " +
             result["Last Name"].fillna("").astype(str).str.strip()).str.strip()
    normalized = names.map(normalize_name)
    applied: list[dict[str, object]] = []
    for entry in overrides:
        if not isinstance(entry, dict):
            raise ValueError("Each roster age-group override must be an object")
        target = normalize_name(entry.get("normalized_name"))
        age_group = entry.get("age_group")
        if target is None or pd.isna(age_group) or not str(age_group).strip():
            raise ValueError("Roster age-group override requires normalized_name and age_group")
        indexes = result.index[normalized == target]
        if len(indexes) != 1:
            raise ValueError(f"Roster override for {target!r} matched {len(indexes)} rows; expected one")
        index = indexes[0]
        original = result.at[index, "Age Group"]
        result.at[index, "Age Group"] = str(age_group).strip()
        applied.append({"normalized_name": target, "field": "Age Group",
                        "original_value": original, "override_value": str(age_group).strip(),
                        "reason": entry.get("reason", "Client-confirmed override")})
    result.attrs.update(roster.attrs)
    result.attrs["applied_client_overrides"] = applied
    return result
