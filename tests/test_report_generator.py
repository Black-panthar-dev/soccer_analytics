from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
import pandas as pd
import pytest

from src.config_loader import load_config
from src.radar_chart import RADAR_METRICS
from src.report_generator import (
    format_athlete_name, format_birthday, render_page1_report,
    report_layout_from_config, wrap_text_to_width, _font, _font_fitting_width,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/Sogility GO Elite Athlete Assessment FINAL.png"
LOGO = ROOT / "logos/STLDA LOGO.png"


def athlete(value: object = 50) -> dict[str, object]:
    row: dict[str, object] = {"first_name": "Amelia", "last_name": "Loehr",
        "birthday": "1/1/2019", "team_name": "2018/19G Elite Navy Current", "age_group": "U8"}
    for metric in RADAR_METRICS:
        row[f"{metric}_percentile"] = value
        row[f"{metric}_age_group_average_percentile"] = 60
    return row


@pytest.fixture
def layout():
    return report_layout_from_config(load_config(ROOT / "config/config.json"))


@pytest.fixture
def complete_preview(test_workspace: Path, layout):
    path = test_workspace / "complete.png"
    result = render_page1_report(athlete(), TEMPLATE, LOGO, path, layout)
    return result


def test_approved_template_loads_at_actual_dimensions() -> None:
    with Image.open(TEMPLATE) as image:
        assert image.size == (1920, 1080)


def test_output_dimensions_and_valid_mode_match_template(complete_preview) -> None:
    with Image.open(complete_preview.path) as image:
        assert image.size == (1920, 1080)
        assert image.mode == "RGBA"


def test_athlete_name_format_and_insertion_metadata(complete_preview) -> None:
    assert format_athlete_name("Amelia", "Loehr") == "LOEHR, AMELIA"
    assert complete_preview.athlete_display_name == "LOEHR, AMELIA"


def test_birthday_formatting_and_missing() -> None:
    assert format_birthday("1/1/2019") == "01/01/2019"
    assert format_birthday(pd.NA) == "N/A"
    assert format_birthday("bad") == "N/A"


def test_team_wrapping_respects_width() -> None:
    image = Image.new("RGBA", (500, 200))
    draw = ImageDraw.Draw(image)
    font = _font(20)
    lines = wrap_text_to_width("A Very Long Elite Soccer Team Name", font, 130, draw)
    assert len(lines) > 1
    assert all(draw.textbbox((0, 0), line, font=font)[2] <= 130 for line in lines)


def test_long_legend_name_font_fits_available_slot() -> None:
    image = Image.new("RGBA", (500, 200))
    draw = ImageDraw.Draw(image)
    font = _font_fitting_width("KORNBERGER, GRACELYNN", 18, 240, draw)
    assert draw.textbbox((0, 0), "KORNBERGER, GRACELYNN", font=font)[2] <= 240


def test_long_identity_name_font_fits_info_box() -> None:
    image = Image.new("RGBA", (500, 200))
    draw = ImageDraw.Draw(image)
    font = _font_fitting_width("KORNBERGER, GRACELYNN", 24, 302, draw, minimum_size=16)
    assert draw.textbbox((0, 0), "KORNBERGER, GRACELYNN", font=font)[2] <= 302


def test_long_team_is_wrapped_in_preview(test_workspace: Path, layout) -> None:
    row = athlete()
    row["team_name"] = "A Very Long Elite Soccer Team Name"
    result = render_page1_report(row, TEMPLATE, LOGO, test_workspace / "long_team.png", layout)
    assert len(result.wrapped_team_lines) > 1


def test_baked_club_logo_region_is_unchanged(complete_preview, layout) -> None:
    with Image.open(TEMPLATE) as original, Image.open(complete_preview.path) as output:
        assert ImageChops.difference(original.crop(layout.club_logo_bounds).convert("RGB"),
                                     output.crop(layout.club_logo_bounds).convert("RGB")).getbbox() is None


def test_dynamic_club_logo_architecture_remains_available(test_workspace: Path, layout) -> None:
    output_path = test_workspace / "dynamic_logo.png"
    render_page1_report(athlete(), TEMPLATE, LOGO, output_path, layout, place_club_logo=True)
    with Image.open(TEMPLATE) as original, Image.open(output_path) as output:
        assert ImageChops.difference(original.crop(layout.club_logo_bounds).convert("RGB"),
                                     output.crop(layout.club_logo_bounds).convert("RGB")).getbbox() is not None


def test_sogility_logo_region_is_unchanged(complete_preview) -> None:
    sogility_bounds = (1540, 20, 1680, 150)
    with Image.open(TEMPLATE) as original, Image.open(complete_preview.path) as output:
        assert ImageChops.difference(original.crop(sogility_bounds).convert("RGBA"),
                                     output.crop(sogility_bounds).convert("RGBA")).getbbox() is None


def test_radar_region_is_replaced_and_receives_overlay(complete_preview, layout) -> None:
    bounds = layout.radar_overlay_bounds
    with Image.open(TEMPLATE) as original, Image.open(complete_preview.path) as output:
        assert ImageChops.difference(original.crop(bounds).convert("RGB"),
                                     output.crop(bounds).convert("RGB")).getbbox() is not None
    assert not complete_preview.radar_region_replaced


def test_clean_template_has_no_baked_polygon_with_zero_dynamic_values(test_workspace: Path, layout) -> None:
    result = render_page1_report(athlete(0), TEMPLATE, LOGO, test_workspace / "zero.png", layout)
    with Image.open(result.path) as output:
        crop = output.crop(layout.radar_overlay_bounds).convert("RGB")
        green_away_from_center = 0
        center = crop.width // 2, crop.height // 2
        for y in range(crop.height):
            for x in range(crop.width):
                red, green, blue = crop.getpixel((x, y))
                if green > 190 and red < 100 and blue < 120 and abs(x-center[0]) + abs(y-center[1]) > 30:
                    green_away_from_center += 1
        assert green_away_from_center < 20


def test_missing_metric_renders_as_gap(test_workspace: Path, layout) -> None:
    row = athlete()
    row["juggling_dominant_percentile"] = pd.NA
    result = render_page1_report(row, TEMPLATE, LOGO, test_workspace / "missing.png", layout)
    assert result.radar_missing_metrics == ("juggling_dominant",)


def test_missing_age_group_prevents_preview(test_workspace: Path, layout) -> None:
    row = athlete()
    row["age_group"] = pd.NA
    with pytest.raises(ValueError, match="age group"):
        render_page1_report(row, TEMPLATE, LOGO, test_workspace / "invalid.png", layout)


def test_layout_coordinates_loaded_from_config(layout) -> None:
    assert layout.radar_center == (891, 590)
    assert layout.radar_radius == 328
    assert layout.club_logo_bounds == (1690, 35, 1870, 145)


def test_complete_data_athlete_has_no_radar_gaps(complete_preview) -> None:
    assert complete_preview.radar_missing_metrics == ()
