from __future__ import annotations

from pathlib import Path

from PIL import Image
import pandas as pd

from src.config_loader import load_config
from src.metric_extractor import METRIC_COLUMNS
from src.report_generator import (
    PAGE2_METRICS, render_page2_table, render_two_page_preview,
    report_layout_from_config,
)
from src.report_v2_audit import run_report_v2_audit


ROOT = Path(__file__).resolve().parents[1]


def row() -> dict[str, object]:
    value: dict[str, object] = {"first_name": "Kya", "last_name": "Sachs",
        "full_name": "Kya Sachs", "birthday": pd.NA, "team_name": "2017/18G Elite Red Wave",
        "age_group": "U9", "assessment_date": "2026-08-15"}
    for index, metric in enumerate(METRIC_COLUMNS, 1):
        value[metric] = float(index)
        value[f"{metric}_percentile"] = float(index * 5)
        value[f"{metric}_age_group_average"] = float(index + .5)
        value[f"{metric}_age_group_average_percentile"] = 50.0
    return value


def test_final_template_config_replaces_old_template() -> None:
    config = load_config(ROOT / "config/config.json")
    assert config["paths"]["template"].endswith("Assessment FINAL.png")  # type: ignore[index]
    assert "Assessment Clean.png" not in config["paths"]["page1_clean_template"]  # type: ignore[index]
    assert "(2)" not in config["paths"]["page1_clean_template"]  # type: ignore[index]
    assert config["logo_defaults"]["page1_club_logo_overlay"] is False  # type: ignore[index]


def test_page2_contains_all_ten_metrics_and_values(test_workspace: Path) -> None:
    config = load_config(ROOT / "config/config.json")
    result = render_page2_table(row(), test_workspace / "page2.png",
        ROOT / "logos/Sogility_Logo.png", config["page2_layout"])  # type: ignore[arg-type]
    assert len(result.metric_rows) == 10
    assert [item[1] for item in PAGE2_METRICS] == [item["metric"] for item in result.metric_rows]
    assert result.metric_rows[0]["athlete_raw_score"] == "1.000 s"
    assert result.metric_rows[0]["raw_age_group_average"] == "1.500 s"


def test_missing_page2_metric_is_na(test_workspace: Path) -> None:
    config = load_config(ROOT / "config/config.json")
    athlete = row()
    athlete["dash_20y"] = pd.NA
    athlete["dash_20y_percentile"] = pd.NA
    result = render_page2_table(athlete, test_workspace / "missing.png",
        ROOT / "logos/Sogility_Logo.png", config["page2_layout"])  # type: ignore[arg-type]
    dash20 = next(item for item in result.metric_rows if item["metric"] == "20-Yard Dash")
    assert dash20["athlete_raw_score"] == "N/A"
    assert dash20["percentile"] == "N/A"


def test_sogility_logo_loads_and_page2_dimensions(test_workspace: Path) -> None:
    logo = ROOT / "logos/Sogility_Logo.png"
    with Image.open(logo) as image:
        assert image.size == (1920, 1920)
    config = load_config(ROOT / "config/config.json")
    result = render_page2_table(row(), test_workspace / "branded.png", logo,
                                config["page2_layout"])  # type: ignore[arg-type]
    with Image.open(result.path) as image:
        assert image.size == (1920, 1080)


def test_two_page_render_does_not_mutate_upstream_data(test_workspace: Path) -> None:
    config = load_config(ROOT / "config/config.json")
    athlete = row()
    before = athlete.copy()
    result = render_two_page_preview(athlete,
        ROOT / "templates/Sogility GO Elite Athlete Assessment FINAL.png",
        ROOT / "logos/STLDA LOGO.png", ROOT / "logos/Sogility_Logo.png",
        test_workspace / "page1.png", test_workspace / "page2.png",
        report_layout_from_config(config), config["page2_layout"])  # type: ignore[arg-type]
    assert result.page1.dimensions == result.page2.dimensions == (1920, 1080)
    assert athlete == before


def test_manifest_generated_for_four_preview_pairs() -> None:
    manifest = run_report_v2_audit(ROOT)
    assert len(manifest) == 8
    assert set(manifest["athlete"]) == {"Amelia Loehr", "Adelyn O'Boynick", "Abby Hoffmann", "Kya Sachs"}
    assert set(manifest["page"]) == {1, 2}
    assert (ROOT / "output/debug/final_preview/preview_manifest.csv").is_file()
