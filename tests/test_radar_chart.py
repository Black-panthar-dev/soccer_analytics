from __future__ import annotations

import math
from pathlib import Path

from PIL import Image
import pytest

from src.radar_chart import (
    RADAR_METRICS, RadarRenderConfig, generate_radar_chart,
)


EXPECTED = (
    "juggling_thighs", "dash_10y", "dash_20y", "shuttle_5_10_5",
    "figure8_best", "figure8_worst", "passing_90", "passing_180",
    "juggling_non_dominant", "juggling_dominant",
)


def values(value: object = 50) -> dict[str, object]:
    return {metric: value for metric in RADAR_METRICS}


@pytest.fixture
def tmp_path(test_workspace: Path) -> Path:
    """Use the project-owned test workspace instead of the restricted system temp."""
    return test_workspace


def render(tmp_path: Path, data: dict[str, object] | None = None, **kwargs: object):
    return generate_radar_chart(values() if data is None else data, tmp_path / "radar.png", **kwargs)


def test_exact_approved_ten_axis_order() -> None:
    assert len(RADAR_METRICS) == 10
    assert RADAR_METRICS == EXPECTED


def test_zero_and_hundred_are_preserved(tmp_path: Path) -> None:
    data = values()
    data["juggling_thighs"] = 0
    data["dash_10y"] = 100
    result = render(tmp_path, data)
    assert result.athlete_geometry[0][1] == 0
    assert result.athlete_geometry[1][1] == 100


def test_missing_stays_nan_and_is_reported(tmp_path: Path) -> None:
    data = values()
    data["dash_20y"] = None
    result = render(tmp_path, data)
    assert math.isnan(result.athlete_geometry[2][1])
    assert result.missing_athlete_metrics == ("dash_20y",)
    assert not result.athlete_polygon_closed


def test_optional_comparison_is_not_drawn(tmp_path: Path) -> None:
    result = render(tmp_path)
    assert not result.comparison_polygon_closed
    assert set(result.missing_comparison_metrics) == set(RADAR_METRICS)


def test_comparison_uses_canonical_order_despite_mapping_order(tmp_path: Path) -> None:
    comparison = {metric: index for index, metric in enumerate(reversed(RADAR_METRICS))}
    result = generate_radar_chart(values(), tmp_path / "radar.png", comparison)
    assert result.metric_order == EXPECTED
    assert [point[1] for point in result.comparison_geometry] == [comparison[m] for m in EXPECTED]


@pytest.mark.parametrize("invalid", [-0.01, 100.01, float("inf"), "bad"])
def test_invalid_percentile_rejected(tmp_path: Path, invalid: object) -> None:
    data = values()
    data["dash_10y"] = invalid
    with pytest.raises(ValueError):
        render(tmp_path, data)


def test_unknown_or_missing_metric_key_rejected(tmp_path: Path) -> None:
    data = values()
    del data["dash_10y"]
    data["unknown"] = 20
    with pytest.raises(ValueError, match="exactly the 10"):
        render(tmp_path, data)


def test_transparent_overlay_png_and_dimensions(tmp_path: Path) -> None:
    result = render(tmp_path)
    with Image.open(result.path) as image:
        assert image.mode == "RGBA"
        assert image.size == (1000, 1000)
        low, high = image.getchannel("A").getextrema()
        assert low == 0 and high > 0


def test_debug_chart_generated(tmp_path: Path) -> None:
    result = render(tmp_path, mode="debug")
    assert result.path.is_file()
    assert result.mode == "debug"
    with Image.open(result.path) as image:
        assert image.size == (1000, 1000)


def test_identical_input_has_deterministic_geometry(tmp_path: Path) -> None:
    first = generate_radar_chart(values(37), tmp_path / "one.png")
    second = generate_radar_chart(dict(reversed(list(values(37).items()))), tmp_path / "two.png")
    assert first.athlete_geometry == second.athlete_geometry


@pytest.mark.parametrize("missing", [1, 4, 10])
def test_missing_metrics_do_not_crash_or_become_zero(tmp_path: Path, missing: int) -> None:
    data = values(60)
    for metric in RADAR_METRICS[:missing]:
        data[metric] = None
    result = render(tmp_path, data)
    assert len(result.missing_athlete_metrics) == missing
    assert all(math.isnan(result.athlete_geometry[i][1]) for i in range(missing))


def test_all_available_creates_closed_filled_polygon(tmp_path: Path) -> None:
    assert render(tmp_path).athlete_polygon_closed


def test_comparison_can_render_independently(tmp_path: Path) -> None:
    result = generate_radar_chart(None, tmp_path / "comparison.png", values(50))
    assert not result.athlete_polygon_closed
    assert result.comparison_polygon_closed


def test_geometry_configuration_exposed(tmp_path: Path) -> None:
    config = RadarRenderConfig(start_angle_degrees=90, clockwise=False, line_width=5,
                               fill_alpha=.4, output_width=800, output_height=800,
                               figure_size_inches=(4, 4))
    result = render(tmp_path, config=config)
    assert result.canvas_dimensions == (800, 800)


def test_final_series_styling_is_thin_muted_and_translucent() -> None:
    config = RadarRenderConfig()
    assert config.athlete_line_width == pytest.approx(0.9)
    assert config.comparison_line_width == pytest.approx(0.72)
    assert config.athlete_line_width > config.comparison_line_width
    assert config.athlete_color == "#42c96b"
    assert config.comparison_color == "#43c4df"
    assert config.athlete_fill_alpha == pytest.approx(0.25)
    assert config.comparison_fill_alpha == pytest.approx(0.25)


def test_renderer_accepts_precomputed_values_without_percentile_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.percentiles
    monkeypatch.setattr(src.percentiles, "calculate_metric_percentiles",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not calculate")))
    assert render(tmp_path, values(73)).path.is_file()
