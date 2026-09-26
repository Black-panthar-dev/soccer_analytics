"""Conservative normalization helpers used for deterministic identity matching."""

from __future__ import annotations

import re
import unicodedata

import pandas as pd


_WHITESPACE = re.compile(r"\s+")
_APOSTROPHES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u02bc": "'", "\uff07": "'"})
_MOJIBAKE_APOSTROPHES = ("\u00e2\u20ac\u2122", "\u00e2\u20ac\u02dc")


def _missing(value: object) -> bool:
    """Return true for scalar missing values without coercing real values."""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def normalize_email(value: object) -> str | None:
    """Trim and case-fold an email; missing and blank values stay missing."""
    if _missing(value):
        return None
    normalized = str(value).strip().casefold()
    return normalized or None


def normalize_name(value: object) -> str | None:
    """Conservatively normalize a name while retaining meaningful punctuation."""
    if _missing(value):
        return None
    normalized = str(value)
    for variant in _MOJIBAKE_APOSTROPHES:
        normalized = normalized.replace(variant, "'")
    normalized = unicodedata.normalize("NFKC", normalized).translate(_APOSTROPHES)
    normalized = _WHITESPACE.sub(" ", normalized.strip()).casefold()
    return normalized or None
