"""Approved-template PNG preview composition (PDF export intentionally absent)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .radar_chart import RADAR_METRICS, RadarRenderConfig, generate_radar_chart


@dataclass(frozen=True)
class ReportLayout:
    athlete_name_position: tuple[int, int]
    birthdate_position: tuple[int, int]
    team_text_box: tuple[int, int, int, int]
    legend_athlete_position: tuple[int, int]
    legend_benchmark_position: tuple[int, int]
    club_logo_bounds: tuple[int, int, int, int]
    radar_center: tuple[int, int]
    radar_radius: int
    radar_overlay_bounds: tuple[int, int, int, int]
    radar_start_angle_degrees: float = 108.0
    athlete_info_font_size: int = 24
    team_font_size: int = 20
    legend_font_size: int = 18
    name_format: str = "last_first"


@dataclass(frozen=True)
class ReportPreviewResult:
    path: Path
    dimensions: tuple[int, int]
    athlete_display_name: str
    birthday_text: str
    wrapped_team_lines: tuple[str, ...]
    radar_missing_metrics: tuple[str, ...]
    radar_region_replaced: bool
    club_logo_bounds: tuple[int, int, int, int]


@dataclass(frozen=True)
class Page2RenderResult:
    path: Path
    dimensions: tuple[int, int]
    metric_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class TwoPagePreviewResult:
    page1: ReportPreviewResult
    page2: Page2RenderResult


def report_layout_from_config(config: Mapping[str, object]) -> ReportLayout:
    raw = config.get("layout")
    if not isinstance(raw, dict):
        raise ValueError("Config must contain a layout object")
    required = ("athlete_name_position", "birthdate_position", "team_text_box",
                "legend_athlete_position", "legend_benchmark_position", "club_logo_bounds",
                "radar_center", "radar_radius", "radar_overlay_bounds")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Layout is missing required coordinates: {missing}")
    return ReportLayout(
        tuple(raw["athlete_name_position"]), tuple(raw["birthdate_position"]),  # type: ignore[arg-type]
        tuple(raw["team_text_box"]), tuple(raw["legend_athlete_position"]),  # type: ignore[arg-type]
        tuple(raw["legend_benchmark_position"]), tuple(raw["club_logo_bounds"]),  # type: ignore[arg-type]
        tuple(raw["radar_center"]), int(raw["radar_radius"]),  # type: ignore[arg-type]
        tuple(raw["radar_overlay_bounds"]),  # type: ignore[arg-type]
        float(raw.get("radar_start_angle_degrees", 108.0)),
        int(raw.get("athlete_info_font_size", 24)), int(raw.get("team_font_size", 20)),
        int(raw.get("legend_font_size", 18)), str(raw.get("name_format", "last_first")),
    )


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = ([r"C:\Windows\Fonts\arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
                  else [r"C:\Windows\Fonts\arial.ttf", "DejaVuSans.ttf"])
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _font_fitting_width(text: str, preferred_size: int, max_width: int,
                        draw: ImageDraw.ImageDraw, *, minimum_size: int = 12,
                        bold: bool = True) -> ImageFont.ImageFont:
    """Choose the largest configured font size that stays inside a fixed label slot."""
    for size in range(preferred_size, minimum_size - 1, -1):
        candidate = _font(size, bold=bold)
        if draw.textbbox((0, 0), text, font=candidate)[2] <= max_width:
            return candidate
    return _font(minimum_size, bold=bold)


def format_athlete_name(first_name: object, last_name: object,
                        name_format: str = "last_first") -> str:
    first = "" if pd.isna(first_name) else str(first_name).strip()
    last = "" if pd.isna(last_name) else str(last_name).strip()
    if name_format == "last_first":
        return ", ".join(part.upper() for part in (last, first) if part)
    if name_format == "first_last":
        return " ".join(part.upper() for part in (first, last) if part)
    raise ValueError(f"Unsupported name format: {name_format}")


def format_birthday(value: object) -> str:
    if pd.isna(value) or not str(value).strip():
        return "N/A"
    parsed = pd.to_datetime(value, errors="coerce")
    return "N/A" if pd.isna(parsed) else parsed.strftime("%m/%d/%Y")


def wrap_text_to_width(text: object, font: ImageFont.ImageFont, max_width: int,
                       draw: ImageDraw.ImageDraw) -> tuple[str, ...]:
    words = [] if pd.isna(text) else str(text).strip().split()
    if not words:
        return ("N/A",)
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def _transparent_logo(path: Path, bounds: tuple[int, int, int, int]) -> Image.Image:
    logo = Image.open(path).convert("RGBA")
    white = Image.new("RGBA", logo.size, "white")
    difference = ImageChops.difference(logo, white).convert("L")
    mask = difference.point(lambda value: 0 if value < 12 else min(255, value * 3))
    content = mask.getbbox()
    if content:
        logo = logo.crop(content)
        mask = mask.crop(content)
    logo.putalpha(mask)
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    logo.thumbnail((width, height), Image.Resampling.LANCZOS)
    return logo


def _draw_radar_interior(image: Image.Image, layout: ReportLayout,
                         clear_existing: bool) -> None:
    center_x, center_y = layout.radar_center
    radius = layout.radar_radius
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = (center_x-radius, center_y-radius, center_x+radius, center_y+radius)
    if clear_existing:
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((center_x-radius-5, center_y-radius-5, center_x+radius+5, center_y+radius+5),
                          outline=(95, 225, 248, 190), width=8)
        image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8)))
        draw.ellipse(box, fill=(2, 8, 10, 255), outline=(92, 221, 244, 255), width=3)
    for fraction in (0.2, 0.4, 0.6, 0.8):
        ring = int(radius * fraction)
        draw.ellipse((center_x-ring, center_y-ring, center_x+ring, center_y+ring),
                     outline=(101, 169, 178, 110), width=2)
    for index in range(10):
        angle = math.radians(layout.radar_start_angle_degrees - index * 36)
        point = (center_x + radius * math.cos(angle), center_y - radius * math.sin(angle))
        draw.line((center_x, center_y, *point), fill=(92, 151, 159, 115), width=2)
    scale_font = _font(17, bold=True)
    for value in (20, 40, 60, 80):
        y = center_y - int(radius * value / 100) - 9
        draw.text((center_x - 30, y), str(value), font=scale_font, fill=(220, 245, 246, 230))
    draw.text((center_x - 27, center_y - 10), "0", font=scale_font, fill=(220, 245, 246, 230))
    image.alpha_composite(layer)


def render_report_preview(
    athlete: Mapping[str, object], template_path: Path, club_logo_path: Path,
    output_path: Path, layout: ReportLayout, *, clean_template: bool = False,
    place_club_logo: bool = True,
) -> ReportPreviewResult:
    age_group = athlete.get("age_group")
    if pd.isna(age_group) or not str(age_group).strip():
        raise ValueError("A valid authoritative age group is required for a report preview")
    template = Image.open(template_path).convert("RGBA")
    image = template.copy()
    _draw_radar_interior(image, layout, clear_existing=not clean_template)
    athlete_values = {metric: athlete.get(f"{metric}_percentile") for metric in RADAR_METRICS}
    comparison_values = {metric: athlete.get(f"{metric}_age_group_average_percentile")
                         for metric in RADAR_METRICS}
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    radar_temp = destination.with_name(destination.stem + "__radar.png")
    bounds = layout.radar_overlay_bounds
    radar_size = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    radar_result = generate_radar_chart(
        athlete_values, radar_temp, comparison_values, mode="overlay",
        config=RadarRenderConfig(output_width=radar_size[0], output_height=radar_size[1],
                                 figure_size_inches=(radar_size[0] / 200, radar_size[1] / 200),
                                 dpi=200, start_angle_degrees=layout.radar_start_angle_degrees),
    )
    with Image.open(radar_temp) as overlay:
        image.alpha_composite(overlay.convert("RGBA"), (bounds[0], bounds[1]))
    radar_temp.unlink(missing_ok=True)

    draw = ImageDraw.Draw(image)
    display_name = format_athlete_name(athlete.get("first_name"), athlete.get("last_name"), layout.name_format)
    birthday = format_birthday(athlete.get("birthday"))
    info_font = _font(layout.athlete_info_font_size)
    team_font = _font(layout.team_font_size)
    legend_font = _font(layout.legend_font_size)
    value_color = (238, 244, 244, 255)
    draw.text(layout.athlete_name_position, display_name, font=info_font, fill=value_color)
    draw.text(layout.birthdate_position, birthday, font=info_font, fill=value_color)
    team_box = layout.team_text_box
    team_lines = wrap_text_to_width(athlete.get("team_name"), team_font,
                                    team_box[2] - team_box[0], draw)
    line_height = layout.team_font_size + 4
    for index, line in enumerate(team_lines):
        y = team_box[1] + index * line_height
        if y + line_height <= team_box[3]:
            draw.text((team_box[0], y), line, font=team_font, fill=value_color)
    legend_name_max_width = layout.legend_benchmark_position[0] - layout.legend_athlete_position[0] - 55
    legend_name_font = _font_fitting_width(
        display_name, layout.legend_font_size, legend_name_max_width, draw,
    )
    draw.text(layout.legend_athlete_position, display_name, font=legend_name_font,
              fill=(238, 244, 244, 255))
    benchmark_lines = (f"{str(age_group).upper()} AGE GROUP", "AVERAGE")
    for index, line in enumerate(benchmark_lines):
        draw.text((layout.legend_benchmark_position[0], layout.legend_benchmark_position[1] + index * 20),
                  line, font=legend_font, fill=(238, 244, 244, 255))
    if place_club_logo:
        logo = _transparent_logo(club_logo_path, layout.club_logo_bounds)
        logo_x = layout.club_logo_bounds[0] + ((layout.club_logo_bounds[2] - layout.club_logo_bounds[0] - logo.width) // 2)
        logo_y = layout.club_logo_bounds[1] + ((layout.club_logo_bounds[3] - layout.club_logo_bounds[1] - logo.height) // 2)
        image.alpha_composite(logo, (logo_x, logo_y))
    image.save(destination)
    return ReportPreviewResult(destination, image.size, display_name, birthday, team_lines,
                               radar_result.missing_athlete_metrics, not clean_template,
                               layout.club_logo_bounds)


def load_page1_template(path: Path) -> Image.Image:
    """Load the client-approved clean Page 1 PNG without resizing it."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Clean Page 1 template not found: {source}")
    image = Image.open(source)
    image.load()
    return image.convert("RGBA")


def render_page1_report(athlete: Mapping[str, object], template_path: Path,
                        club_logo_path: Path, output_path: Path,
                        layout: ReportLayout, *, place_club_logo: bool = False) -> ReportPreviewResult:
    """Render Page 1 on the approved template, preserving its baked header logos."""
    load_page1_template(template_path).close()
    return render_report_preview(athlete, template_path, club_logo_path, output_path,
                                 layout, clean_template=True, place_club_logo=place_club_logo)


PAGE2_METRICS: tuple[tuple[str, str], ...] = (
    ("dash_10y", "10-Yard Dash"), ("dash_20y", "20-Yard Dash"),
    ("shuttle_5_10_5", "5-10-5"),
    ("figure8_best", "Dribbling: Figure 8 (Best Time)"),
    ("figure8_worst", "Dribbling: Figure 8 (Worst Time)"),
    ("passing_90", "90° Passing"), ("passing_180", "180° Passing"),
    ("juggling_dominant", "Juggling: Dominant Foot"),
    ("juggling_non_dominant", "Juggling: Non-Dominant Foot"),
    ("juggling_thighs", "Juggling: Thighs Only"),
)
TIME_METRICS = {"dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best", "figure8_worst"}


def _format_metric_value(value: object, metric: str) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "N/A"
    if metric in TIME_METRICS:
        return f"{float(numeric):.3f} s"
    number = float(numeric)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _format_percentile(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "N/A" if pd.isna(numeric) else f"{float(numeric):.1f}"


def _place_logo(image: Image.Image, path: Path,
                bounds: tuple[int, int, int, int]) -> None:
    logo = Image.open(path).convert("RGBA")
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    logo.thumbnail((width, height), Image.Resampling.LANCZOS)
    x = bounds[0] + (width - logo.width) // 2
    y = bounds[1] + (height - logo.height) // 2
    image.alpha_composite(logo, (x, y))


def render_page2_table(athlete: Mapping[str, object], output_path: Path,
                       sogility_logo_path: Path,
                       page2_config: Mapping[str, object]) -> Page2RenderResult:
    """Render the ten-row performance table as a standalone PNG preview."""
    width, height = int(page2_config["canvas_width"]), int(page2_config["canvas_height"])
    background = str(page2_config["background_color"])
    white, green, cyan = (str(page2_config[key]) for key in
                          ("white_color", "green_color", "cyan_color"))
    image = Image.new("RGBA", (width, height), background)
    draw = ImageDraw.Draw(image)
    header = tuple(page2_config["header_position"])  # type: ignore[arg-type]
    identity = tuple(page2_config["identity_position"])  # type: ignore[arg-type]
    table = tuple(page2_config["table_bounds"])  # type: ignore[arg-type]
    columns = tuple(page2_config["column_positions"])  # type: ignore[arg-type]
    row_spacing = int(page2_config["row_spacing"])
    title_font = _font(int(page2_config["title_font_size"]))
    identity_font = _font(int(page2_config["identity_font_size"]), bold=False)
    table_header_font = _font(int(page2_config["table_header_font_size"]))
    table_font = _font(int(page2_config["table_font_size"]), bold=False)
    draw.text(header, "SOGILITY GO: ATHLETE PERFORMANCE DETAILS", font=title_font, fill=white)
    name = format_athlete_name(athlete.get("first_name"), athlete.get("last_name"))
    birthday = format_birthday(athlete.get("birthday"))
    assessment = pd.to_datetime(athlete.get("assessment_date"), errors="coerce")
    assessment_text = "N/A" if pd.isna(assessment) else assessment.strftime("%m/%d/%Y")
    identity_lines = (f"ATHLETE: {name}    BIRTHDATE: {birthday}    AGE GROUP: {athlete.get('age_group')}",
                      f"TEAM: {athlete.get('team_name')}    ASSESSMENT DATE: {assessment_text}")
    for index, line in enumerate(identity_lines):
        draw.text((identity[0], identity[1] + index * 32), line, font=identity_font, fill=white)
    headers = ("METRIC", "ATHLETE RAW SCORE", "PERCENTILE", "RAW AGE-GROUP AVERAGE")
    for x, label in zip(columns, headers):
        draw.text((x, table[1]), label, font=table_header_font, fill=white)
    draw.line((table[0], table[1] + 38, table[2], table[1] + 38), fill=white, width=2)
    rows: list[dict[str, str]] = []
    first_y = table[1] + 55
    for index, (metric, label) in enumerate(PAGE2_METRICS):
        y = first_y + index * row_spacing
        raw = _format_metric_value(athlete.get(metric), metric)
        percentile = _format_percentile(athlete.get(f"{metric}_percentile"))
        average = _format_metric_value(athlete.get(f"{metric}_age_group_average"), metric)
        row = {"metric": label, "athlete_raw_score": raw,
               "percentile": percentile, "raw_age_group_average": average}
        rows.append(row)
        draw.text((columns[0], y), label, font=table_font, fill=white)
        draw.text((columns[1], y), raw, font=table_font, fill=green)
        draw.text((columns[2], y), percentile, font=table_font, fill=white)
        draw.text((columns[3], y), average, font=table_font, fill=cyan)
        draw.line((table[0], y + 38, table[2], y + 38), fill=(220, 230, 230, 100), width=1)
    logo_bounds = tuple(page2_config["sogility_logo_bounds"])  # type: ignore[arg-type]
    _place_logo(image, sogility_logo_path, logo_bounds)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return Page2RenderResult(destination, image.size, tuple(rows))


def render_two_page_preview(athlete: Mapping[str, object], page1_template: Path,
                            club_logo_path: Path, sogility_logo_path: Path,
                            page1_output: Path, page2_output: Path,
                            page1_layout: ReportLayout,
                            page2_config: Mapping[str, object], *,
                            place_page1_club_logo: bool = False) -> TwoPagePreviewResult:
    page1 = render_page1_report(athlete, page1_template, club_logo_path,
                                page1_output, page1_layout,
                                place_club_logo=place_page1_club_logo)
    page2 = render_page2_table(athlete, page2_output, sogility_logo_path, page2_config)
    return TwoPagePreviewResult(page1, page2)
