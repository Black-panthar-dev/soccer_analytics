from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.client_overrides import apply_roster_overrides
from src.config_loader import load_config
from src.loader import load_roster_csv
from src.matcher import build_canonical_roster
from src.metric_extractor import METRIC_COLUMNS
from src.percentiles import build_age_group_percentiles
from src.validation import validate_roster


ROOT = Path(__file__).resolve().parents[1]
ROSTER_PATH = ROOT / "data/roster/STLDA MASTER COPY - Sheet1.csv"


def override_config(enabled: bool = True) -> dict[str, object]:
    entries = [{"normalized_name": "kya sachs", "age_group": "U9", "reason": "test"}] if enabled else []
    return {"client_overrides": {"roster_age_groups": entries}}


def percentile_config() -> dict[str, object]:
    lower = {"dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best", "figure8_worst"}
    return {"assessment": {"minimum_cohort_size": None},
            "percentiles": {"tie_method": "average", "single_member_percentile": 50,
                            "all_identical_percentile": 50},
            "metrics": {metric: {"direction": "lower" if metric in lower else "higher"}
                        for metric in METRIC_COLUMNS}}


def test_source_csv_remains_byte_for_byte_unchanged() -> None:
    before = ROSTER_PATH.read_bytes()
    raw = load_roster_csv(ROSTER_PATH)
    apply_roster_overrides(raw, load_config(ROOT / "config/config.json"))
    assert ROSTER_PATH.read_bytes() == before
    assert pd.isna(raw.loc[(raw["First Name"] == "Kya") & (raw["Last Name"] == "Sachs"), "Age Group"]).all()


def test_configured_age_group_override_is_applied_to_copy() -> None:
    raw = load_roster_csv(ROSTER_PATH)
    overridden = apply_roster_overrides(raw, override_config())
    kya = overridden.loc[(overridden["First Name"] == "Kya") & (overridden["Last Name"] == "Sachs")].iloc[0]
    assert kya["Age Group"] == "U9"
    assert overridden.attrs["applied_client_overrides"][0]["override_value"] == "U9"


def test_override_removes_missing_age_group_report_block() -> None:
    raw = load_roster_csv(ROSTER_PATH)
    overridden = apply_roster_overrides(raw, override_config())
    kya_row = int(overridden.loc[overridden["First Name"] == "Kya", "_source_row"].iloc[0])
    assert not any(issue.category == "missing_age_group" and issue.roster_row == kya_row
                   for issue in validate_roster(overridden))


def test_kya_joins_only_u9_percentile_cohort() -> None:
    raw = load_roster_csv(ROSTER_PATH)
    canonical = build_canonical_roster(apply_roster_overrides(raw, override_config()))
    canonical = canonical.loc[canonical["full_name"].isin(["Kya Sachs", "Asher Robben", "Amelia Loehr"])].copy()
    for metric in METRIC_COLUMNS:
        canonical[metric] = pd.NA
    canonical.loc[canonical["full_name"] == "Kya Sachs", "figure8_best"] = 20.0
    canonical.loc[canonical["full_name"] == "Asher Robben", "figure8_best"] = 30.0
    canonical.loc[canonical["full_name"] == "Amelia Loehr", "figure8_best"] = 1.0
    result = build_age_group_percentiles(canonical, percentile_config()).assessments
    kya = result.loc[result["full_name"] == "Kya Sachs"].iloc[0]
    assert kya["age_group"] == "U9"
    assert kya["figure8_best_cohort_count"] == 2
    assert kya["figure8_best_age_group_average"] == 25.0
    assert kya["figure8_best_percentile"] == 100.0


def test_removing_override_restores_missing_age_group_behavior() -> None:
    raw = load_roster_csv(ROSTER_PATH)
    without = build_canonical_roster(apply_roster_overrides(raw, override_config(False)))
    kya = without.loc[without["full_name"] == "Kya Sachs"].iloc[0]
    assert pd.isna(kya["age_group"])
    canonical = pd.DataFrame([{"full_name": "Kya Sachs", "age_group": kya["age_group"],
                               **{metric: (20.0 if metric == "figure8_best" else pd.NA)
                                  for metric in METRIC_COLUMNS}}])
    result = build_age_group_percentiles(canonical, percentile_config()).assessments.iloc[0]
    assert pd.isna(result["figure8_best_percentile"])
