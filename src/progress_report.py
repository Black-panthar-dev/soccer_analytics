"""Prepared progress comparisons and presentation-only Page 3 rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable, Mapping

from PIL import Image, ImageDraw

from .assessment_history import (
    AthleteAssessment, get_latest_assessment, get_previous_assessment,
)
from .metric_extractor import METRIC_COLUMNS
from .performance_delta import DeltaStatus, MetricDelta, compare_assessments
from .report_generator import PAGE2_METRICS, TIME_METRICS, _font, _place_logo


METRIC_LABELS: Final[dict[str, str]] = dict(PAGE2_METRICS)


@dataclass(frozen=True)
class ProgressComparison:
    current: AthleteAssessment
    previous: AthleteAssessment
    deltas: tuple[MetricDelta, ...]
    metrics_improved: int
    metrics_declined: int
    metrics_unchanged: int
    metrics_na: int


@dataclass(frozen=True)
class ProgressPageResult:
    path: Path
    dimensions: tuple[int, int]
    metric_rows: tuple[dict[str, str], ...]
    summary: Mapping[str, int]


def prepare_progress_comparison(
    assessments: Iterable[AthleteAssessment], *, tolerance: float = 1e-9,
) -> ProgressComparison | None:
    """Prepare latest-versus-immediately-previous data without rendering it."""
    history = list(assessments)
    current = get_latest_assessment(history)
    previous = get_previous_assessment(history)
    if current is None or previous is None:
        return None
    deltas = tuple(compare_assessments(current, previous, tolerance=tolerance))
    counts = {status: sum(item.status == status for item in deltas) for status in
              (DeltaStatus.IMPROVED, DeltaStatus.DECLINED, DeltaStatus.UNCHANGED,
               DeltaStatus.NOT_AVAILABLE)}
    return ProgressComparison(
        current, previous, deltas, counts[DeltaStatus.IMPROVED], counts[DeltaStatus.DECLINED],
        counts[DeltaStatus.UNCHANGED], counts[DeltaStatus.NOT_AVAILABLE],
    )


def format_metric_value(value: float | None, metric: str) -> str:
    if value is None:
        return "N/A"
    if metric in TIME_METRICS:
        return f"{value:.3f} s"
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def format_change(delta: MetricDelta) -> str:
    """Format client-facing change from the already-calculated delta."""
    if delta.raw_delta is None or delta.performance_delta is None:
        return "N/A"
    if delta.status == DeltaStatus.UNCHANGED:
        return "No change"
    if delta.metric in TIME_METRICS:
        qualifier = "faster" if delta.performance_delta > 0 else "slower"
        return f"{abs(delta.raw_delta):.3f} s {qualifier}"
    return f"{delta.raw_delta:+g}"


def progress_table_rows(comparison: ProgressComparison) -> tuple[dict[str, str], ...]:
    return tuple({
        "metric": METRIC_LABELS[item.metric],
        "previous": format_metric_value(item.previous_raw, item.metric),
        "current": format_metric_value(item.current_raw, item.metric),
        "change": format_change(item),
        "status": item.status,
    } for item in comparison.deltas)


def render_progress_page(
    comparison: ProgressComparison, output_path: Path, sogility_logo_path: Path,
) -> ProgressPageResult:
    """Render prepared comparison data; no extraction, matching, or delta math occurs here."""
    image = Image.new("RGBA", (1920, 1080), "#030708")
    draw = ImageDraw.Draw(image)
    white, green, cyan = "#F4F7F7", "#39B95A", "#43D9FF"
    muted, decline = "#929FA1", "#E6A06A"
    draw.text((90, 55), "SOGILITY GO: PROGRESS COMPARISON", font=_font(40), fill=white)
    current, previous = comparison.current, comparison.previous
    identity = (
        f"ATHLETE: {(current.athlete_name or 'N/A').upper()}    "
        f"CURRENT ASSESSMENT: {current.assessment_date:%m/%d/%Y}    "
        f"PREVIOUS ASSESSMENT: {previous.assessment_date:%m/%d/%Y}",
        f"TEAM: {current.team or 'N/A'}    CURRENT AGE GROUP: {current.age_group or 'N/A'}",
    )
    for index, line in enumerate(identity):
        draw.text((90, 142 + index * 31), line, font=_font(20, bold=False), fill=white)
    summary = (f"IMPROVED: {comparison.metrics_improved}    DECLINED: {comparison.metrics_declined}    "
               f"UNCHANGED: {comparison.metrics_unchanged}    UNAVAILABLE: {comparison.metrics_na}")
    draw.text((90, 225), summary, font=_font(21), fill=cyan)

    columns = (105, 765, 1015, 1265, 1610)
    for x, label in zip(columns, ("METRIC", "PREVIOUS", "CURRENT", "CHANGE", "STATUS")):
        draw.text((x, 300), label, font=_font(22), fill=white)
    draw.line((90, 340, 1830, 340), fill=white, width=2)
    rows = progress_table_rows(comparison)
    colors = {DeltaStatus.IMPROVED: green, DeltaStatus.DECLINED: decline,
              DeltaStatus.UNCHANGED: white, DeltaStatus.NOT_AVAILABLE: muted}
    for index, row in enumerate(rows):
        y = 360 + index * 61
        draw.text((columns[0], y), row["metric"], font=_font(20, bold=False), fill=white)
        draw.text((columns[1], y), row["previous"], font=_font(20, bold=False), fill=cyan)
        draw.text((columns[2], y), row["current"], font=_font(20, bold=False), fill=green)
        draw.text((columns[3], y), row["change"], font=_font(20, bold=False), fill=colors[row["status"]])
        draw.text((columns[4], y), row["status"], font=_font(20), fill=colors[row["status"]])
        draw.line((90, y + 39, 1830, y + 39), fill=(220, 230, 230, 85), width=1)
    _place_logo(image, sogility_logo_path, (1640, 35, 1795, 190))
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return ProgressPageResult(destination, image.size, rows, {
        "improved": comparison.metrics_improved, "declined": comparison.metrics_declined,
        "unchanged": comparison.metrics_unchanged, "na": comparison.metrics_na,
    })
