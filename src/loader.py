"""Read-only loaders for the three Phase 1 CSV source types."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from .raw_schema import (
    HARDWARE_RAW_SCHEMA,
    JUGGLING_REQUIRED_COLUMNS,
    ROSTER_REQUIRED_COLUMNS,
    SOURCE_ROW_COLUMN,
)


BIRTHDAY_PARSED_COLUMN: Final[str] = "_birthday_parsed"


class SourceLoadError(ValueError):
    """Raised when an input exists but cannot be loaded safely."""


def _require_file(path: Path) -> Path:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Required CSV file not found: {resolved}")
    return resolved


def _read_csv(path: Path, *, header: int | None) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            path,
            header=header,
            dtype=object,
            keep_default_na=False,
            na_filter=False,
        )
    except (EmptyDataError, ParserError, UnicodeDecodeError) as exc:
        raise SourceLoadError(f"Could not parse CSV file {path}: {exc}") from exc
    if frame.empty and len(frame.columns) == 0:
        raise SourceLoadError(f"CSV file has no usable structure: {path}")
    return frame.map(_empty_to_missing)


def _empty_to_missing(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return pd.NA
    return value


def _normalize_headers(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    original = [str(column) for column in frame.columns]
    normalized = [column.strip() for column in original]
    if len(set(normalized)) != len(normalized):
        raise SourceLoadError(
            f"Header normalization creates duplicate columns in {path}: {normalized}"
        )
    frame.columns = normalized
    frame.attrs["original_columns"] = original
    frame.attrs["normalized_columns"] = normalized
    return frame


def _require_columns(
    frame: pd.DataFrame, required: tuple[str, ...], path: Path, source_name: str
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SourceLoadError(
            f"Structurally invalid {source_name} CSV {path}; "
            f"missing required columns: {missing}"
        )


def load_hardware_csv(path: Path) -> pd.DataFrame:
    """Load a headerless hardware export with zero-based positional columns."""
    source_path = _require_file(path)
    frame = _read_csv(source_path, header=None)
    if frame.shape[1] != HARDWARE_RAW_SCHEMA.column_count:
        raise SourceLoadError(
            f"Structurally invalid hardware CSV {source_path}; expected "
            f"{HARDWARE_RAW_SCHEMA.column_count} columns, found {frame.shape[1]}"
        )
    frame.columns = list(HARDWARE_RAW_SCHEMA.column_indexes)
    frame.insert(0, SOURCE_ROW_COLUMN, range(1, len(frame) + 1))
    frame.attrs.update(
        source_path=str(source_path),
        header_row=False,
        raw_column_indexes=list(HARDWARE_RAW_SCHEMA.column_indexes),
    )
    return frame


def load_roster_csv(path: Path) -> pd.DataFrame:
    """Load the roster, trim header whitespace, and safely parse birthdays."""
    source_path = _require_file(path)
    frame = _normalize_headers(_read_csv(source_path, header=0), source_path)
    _require_columns(frame, ROSTER_REQUIRED_COLUMNS, source_path, "roster")
    frame.insert(0, SOURCE_ROW_COLUMN, range(2, len(frame) + 2))
    frame[BIRTHDAY_PARSED_COLUMN] = frame["Birthday"].map(_parse_date_or_nat)
    frame.attrs["source_path"] = str(source_path)
    return frame


def _parse_date_or_nat(value: object) -> pd.Timestamp | pd.NaT:
    if pd.isna(value):
        return pd.NaT
    try:
        return pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError, OverflowError):
        return pd.NaT


def load_juggling_csv(path: Path) -> pd.DataFrame:
    """Load juggling scores while retaining raw values and missingness."""
    source_path = _require_file(path)
    frame = _normalize_headers(_read_csv(source_path, header=0), source_path)
    _require_columns(frame, JUGGLING_REQUIRED_COLUMNS, source_path, "juggling")
    frame.insert(0, SOURCE_ROW_COLUMN, range(2, len(frame) + 2))
    frame.attrs["source_path"] = str(source_path)
    return frame
