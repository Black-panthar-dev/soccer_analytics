"""Strict reusable parsing for hardware duration text."""

from __future__ import annotations

import re

import pandas as pd


_DURATION_PATTERN = re.compile(
    r"^\s*(?:(?P<seconds>\d+(?:\.\d+)?)\s*s(?:\s+(?P<milliseconds>\d+)\s*ms)?|"
    r"(?P<milliseconds_only>\d+)\s*ms)\s*$",
    re.IGNORECASE,
)


def parse_duration_to_seconds(value: object) -> float | None:
    """Parse `seconds`, `seconds + milliseconds`, or `milliseconds` only.

    Missing, blank, negative, and unrelated/malformed values return ``None``.
    No invalid value is ever coerced to zero.
    """
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _DURATION_PATTERN.fullmatch(text)
    if match is None:
        return None
    if match.group("milliseconds_only") is not None:
        return int(match.group("milliseconds_only")) / 1000.0
    seconds = float(match.group("seconds"))
    milliseconds = int(match.group("milliseconds") or 0)
    if milliseconds >= 1000:
        return None
    return seconds + milliseconds / 1000.0


def format_seconds(value: float | None, decimal_places: int = 3) -> str:
    """Format seconds for display without changing stored calculation values."""
    if value is None:
        return ""
    return f"{value:.{decimal_places}f}"
