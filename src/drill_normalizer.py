"""Explicit, non-fuzzy normalization of raw hardware drill labels."""

from __future__ import annotations

import pandas as pd


DEFAULT_DRILL_ALIASES: dict[str, str] = {
    "90 Degree Passing": "passing_90",
    "180 Degree Passing": "passing_180",
    "180 Degree passing": "passing_180",
    "5-10-2005": "shuttle_5_10_5",
    "Figure 8": "figure8",
    "Sprints": "sprints",
    "Sprints Assessments": "sprints",
}


def drill_aliases_from_config(config: dict[str, object]) -> dict[str, str]:
    """Read an explicit raw-label mapping, falling back to shipped aliases."""
    configured = config.get("drill_aliases")
    if not isinstance(configured, dict):
        return DEFAULT_DRILL_ALIASES.copy()
    return {str(raw): str(canonical) for raw, canonical in configured.items()}


def normalize_drill_name(value: object,
                         aliases: dict[str, str] | None = None) -> str | None:
    """Return a canonical ID only for an explicitly configured exact alias."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    mapping = DEFAULT_DRILL_ALIASES if aliases is None else aliases
    return mapping.get(str(value).strip())
