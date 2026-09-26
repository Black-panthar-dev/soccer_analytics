"""Reusable presentation-only rendering for the ten-axis percentile radar."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping

_MATPLOTLIB_CACHE = Path(__file__).resolve().parents[1] / "output" / "matplotlib"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image


RADAR_METRICS: Final[tuple[str, ...]] = (
    "juggling_thighs", "dash_10y", "dash_20y", "shuttle_5_10_5",
    "figure8_best", "figure8_worst", "passing_90", "passing_180",
    "juggling_non_dominant", "juggling_dominant",
)
RADAR_LABELS: Final[dict[str, str]] = {
    "juggling_thighs": "Juggling:\nThighs Only",
    "dash_10y": "10-Yard Dash\n(Acceleration)",
    "dash_20y": "20-Yard Dash\n(Linear Speed)",
    "shuttle_5_10_5": "5-10-5\n(Change of Direction)",
    "figure8_best": "Dribbling: Figure 8\n(Best Time)",
    "figure8_worst": "Dribbling: Figure 8\n(Worst Time)",
    "passing_90": "90° Passing",
    "passing_180": "180° Passing",
    "juggling_non_dominant": "Juggling:\nNon-Dominant\nFoot Only",
    "juggling_dominant": "Juggling:\nDominant\nFoot Only",
}


@dataclass(frozen=True)
class RadarRenderConfig:
    output_width: int = 1000
    output_height: int = 1000
    figure_size_inches: tuple[float, float] = (5.0, 5.0)
    dpi: int = 200
    start_angle_degrees: float = 108.0
    clockwise: bool = True
    radial_max: float = 100.0
    # Matplotlib widths are points: at 200 dpi these render to ~2.5 px and ~2 px.
    athlete_line_width: float = 0.9
    comparison_line_width: float = 0.72
    athlete_fill_alpha: float = 0.25
    comparison_fill_alpha: float = 0.25
    axes_bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    debug_axes_bounds: tuple[float, float, float, float] = (0.21, 0.21, 0.58, 0.58)
    debug_label_padding: float = 20.0
    athlete_color: str = "#42c96b"
    comparison_color: str = "#43c4df"
    missing_strategy: str = "gap"
    # Backward-compatible overrides for callers that style both series alike.
    line_width: float | None = None
    fill_alpha: float | None = None


@dataclass(frozen=True)
class RadarRenderResult:
    path: Path
    metric_order: tuple[str, ...]
    missing_athlete_metrics: tuple[str, ...]
    missing_comparison_metrics: tuple[str, ...]
    canvas_dimensions: tuple[int, int]
    athlete_geometry: tuple[tuple[float, float], ...]
    comparison_geometry: tuple[tuple[float, float], ...]
    athlete_polygon_closed: bool
    comparison_polygon_closed: bool
    mode: str


def _validated_values(values: Mapping[str, object] | None, name: str) -> tuple[float, ...]:
    if values is None:
        return tuple(float("nan") for _ in RADAR_METRICS)
    keys = set(values)
    expected = set(RADAR_METRICS)
    if len(values) != 10 or keys != expected:
        missing = sorted(expected - keys)
        unknown = sorted(keys - expected)
        raise ValueError(f"{name} must contain exactly the 10 radar metrics; missing={missing}, unknown={unknown}")
    result: list[float] = []
    for metric in RADAR_METRICS:
        value = values[metric]
        if value is None or pd.isna(value):
            result.append(float("nan"))
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}.{metric} must be numeric or missing") from exc
        if math.isnan(number):
            result.append(number)
        elif not math.isfinite(number) or not 0.0 <= number <= 100.0:
            raise ValueError(f"{name}.{metric} percentile must be between 0 and 100")
        else:
            result.append(number)
    return tuple(result)


def _geometry(values: tuple[float, ...], angles: np.ndarray) -> tuple[tuple[float, float], ...]:
    return tuple((float(angle), value) for angle, value in zip(angles, values))


def _draw_series(ax: object, angles: np.ndarray, values: tuple[float, ...],
                 color: str, line_width: float, fill_alpha: float) -> bool:
    available = np.isfinite(values)
    if not available.any():
        return False
    closed = bool(available.all())
    plot_angles = np.append(angles, angles[0])
    plot_values = np.append(np.asarray(values, dtype=float), values[0])
    ax.plot(plot_angles, plot_values, color=color, linewidth=line_width,
            solid_joinstyle="round", zorder=4)  # type: ignore[attr-defined]
    if closed:
        ax.fill(plot_angles, plot_values, color=color, alpha=fill_alpha, zorder=3)  # type: ignore[attr-defined]
    return closed


def generate_radar_chart(
    athlete_percentiles: Mapping[str, object] | None,
    output_path: Path,
    comparison_percentiles: Mapping[str, object] | None = None,
    *, mode: str = "overlay", config: RadarRenderConfig | None = None,
) -> RadarRenderResult:
    """Render already-calculated percentiles; no ranking is performed here."""
    settings = config or RadarRenderConfig()
    if mode not in {"overlay", "debug"}:
        raise ValueError("mode must be overlay or debug")
    if settings.missing_strategy != "gap":
        raise ValueError("Only missing_strategy='gap' is currently supported")
    if settings.radial_max <= 0 or settings.output_width <= 0 or settings.output_height <= 0:
        raise ValueError("Radar dimensions and radial maximum must be positive")
    athlete = _validated_values(athlete_percentiles, "athlete_percentiles")
    comparison = _validated_values(comparison_percentiles, "comparison_percentiles")
    angles = np.linspace(0.0, 2.0 * np.pi, len(RADAR_METRICS), endpoint=False)
    figure = plt.figure(figsize=settings.figure_size_inches, dpi=settings.dpi,
                        facecolor="none" if mode == "overlay" else "#05090b")
    bounds = settings.axes_bounds if mode == "overlay" else settings.debug_axes_bounds
    ax = figure.add_axes(bounds, projection="polar")
    ax.set_theta_offset(math.radians(settings.start_angle_degrees))
    ax.set_theta_direction(-1 if settings.clockwise else 1)
    ax.set_ylim(0, settings.radial_max)
    athlete_line_width = settings.line_width or settings.athlete_line_width
    comparison_line_width = settings.line_width or settings.comparison_line_width
    athlete_fill_alpha = (settings.athlete_fill_alpha if settings.fill_alpha is None
                          else settings.fill_alpha)
    comparison_fill_alpha = (settings.comparison_fill_alpha if settings.fill_alpha is None
                             else settings.fill_alpha)
    athlete_closed = _draw_series(
        ax, angles, athlete, settings.athlete_color,
        athlete_line_width, athlete_fill_alpha,
    )
    comparison_closed = _draw_series(
        ax, angles, comparison, settings.comparison_color,
        comparison_line_width, comparison_fill_alpha,
    )
    if mode == "overlay":
        ax.set_axis_off()
        ax.patch.set_alpha(0)
        figure.patch.set_alpha(0)
    else:
        ax.set_facecolor("#05090b")
        ax.spines["polar"].set_color("#63dff5")
        ax.spines["polar"].set_linewidth(1.5)
        ax.set_xticks(angles)
        ax.set_xticklabels([RADAR_LABELS[m] for m in RADAR_METRICS], color="white", fontsize=8)
        ax.tick_params(axis="x", pad=settings.debug_label_padding)
        rings = [value for value in (20, 40, 60, 80, 100) if value <= settings.radial_max]
        ax.set_yticks(rings)
        ax.set_yticklabels([str(value) for value in rings], color="#d8f9ff", fontsize=7)
        ax.grid(color="#80d8e8", alpha=0.35, linewidth=0.8)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, format="png", dpi=settings.dpi, transparent=(mode == "overlay"),
                   facecolor=figure.get_facecolor(), edgecolor="none", pad_inches=0)
    plt.close(figure)
    expected_pixels = (settings.output_width, settings.output_height)
    with Image.open(destination) as rendered:
        if rendered.size != expected_pixels:
            resized = rendered.convert("RGBA").resize(expected_pixels, Image.Resampling.LANCZOS)
            resized.save(destination)
    return RadarRenderResult(
        destination, RADAR_METRICS,
        tuple(metric for metric, value in zip(RADAR_METRICS, athlete) if math.isnan(value)),
        tuple(metric for metric, value in zip(RADAR_METRICS, comparison) if math.isnan(value)),
        expected_pixels, _geometry(athlete, angles), _geometry(comparison, angles),
        athlete_closed, comparison_closed, mode,
    )
