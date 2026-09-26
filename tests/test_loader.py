from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.loader import (
    SourceLoadError,
    load_hardware_csv,
    load_juggling_csv,
    load_roster_csv,
)
from src.raw_schema import SOURCE_ROW_COLUMN


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_successful_loading(test_workspace: Path) -> None:
    hardware = _write(test_workspace / "hardware.csv", ",".join(str(i) for i in range(34)))
    roster = _write(
        test_workspace / "roster.csv",
        "TEST TIME,Team Name,First Name,Last Name,Gender,Birthday,Age Group,Parent Contact\n"
        "now,Team,Ada,Lovelace,F,12/10/2010,U14,parent@example.com\n",
    )
    juggling = _write(
        test_workspace / "juggling.csv",
        "First Name,Last Name,Dominant,Non-Dominant,Thighs\nAda,Lovelace,10,8,6\n",
    )
    assert load_hardware_csv(hardware).shape == (1, 35)
    assert len(load_roster_csv(roster)) == 1
    assert len(load_juggling_csv(juggling)) == 1


@pytest.mark.parametrize("loader", [load_hardware_csv, load_roster_csv, load_juggling_csv])
def test_missing_file_handling(test_workspace: Path, loader: object) -> None:
    with pytest.raises(FileNotFoundError, match="Required CSV file not found"):
        loader(test_workspace / "missing.csv")  # type: ignore[operator]


@pytest.mark.parametrize("loader", [load_hardware_csv, load_roster_csv, load_juggling_csv])
def test_malformed_csv_handling(test_workspace: Path, loader: object) -> None:
    malformed = _write(test_workspace / "bad.csv", '"unclosed,value\n')
    with pytest.raises(SourceLoadError, match="Could not parse CSV"):
        loader(malformed)  # type: ignore[operator]


def test_roster_header_normalization(test_workspace: Path) -> None:
    path = _write(
        test_workspace / "roster.csv",
        "TEST TIME,Team Name,First Name,Last Name,Gender,Birthday,Age Group ,Parent Contact\n"
        "now,Team,Ada,Lovelace,F,bad-date,U14,a@example.com\n",
    )
    frame = load_roster_csv(path)
    assert "Age Group" in frame.columns
    assert "Age Group " not in frame.columns
    assert frame.attrs["original_columns"][6] == "Age Group "
    assert frame.loc[0, "Birthday"] == "bad-date"
    assert pd.isna(frame.loc[0, "_birthday_parsed"])


def test_hardware_csv_has_no_header(test_workspace: Path) -> None:
    first = ["first-row-value"] + [str(i) for i in range(1, 34)]
    second = ["second-row-value"] + [str(i) for i in range(1, 34)]
    path = _write(test_workspace / "hardware.csv", ",".join(first) + "\n" + ",".join(second))
    frame = load_hardware_csv(path)
    assert len(frame) == 2
    assert frame.loc[0, 0] == "first-row-value"
    assert frame.loc[0, SOURCE_ROW_COLUMN] == 1
    assert frame.attrs["header_row"] is False


def test_missing_values_remain_missing_not_zero(test_workspace: Path) -> None:
    fields = ["value", ""] + [str(i) for i in range(2, 34)]
    path = _write(test_workspace / "hardware.csv", ",".join(fields))
    frame = load_hardware_csv(path)
    assert pd.isna(frame.loc[0, 1])
    assert frame.loc[0, 1] is pd.NA
