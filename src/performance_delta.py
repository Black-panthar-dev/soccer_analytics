"""Direction-aware raw performance changes between canonical assessments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

from .assessment_history import AthleteAssessment
from .metric_extractor import METRIC_COLUMNS


LOWER_IS_BETTER: Final[frozenset[str]] = frozenset({
    "dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best", "figure8_worst",
})
HIGHER_IS_BETTER: Final[frozenset[str]] = frozenset(set(METRIC_COLUMNS) - LOWER_IS_BETTER)


class DeltaStatus:
    IMPROVED: Final[str] = "IMPROVED"
    DECLINED: Final[str] = "DECLINED"
    UNCHANGED: Final[str] = "UNCHANGED"
    NOT_AVAILABLE: Final[str] = "N/A"


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    current_raw: float | None
    previous_raw: float | None
    raw_delta: float | None
    performance_delta: float | None
    direction: str
    status: str
    percent_change: float | None = None


def calculate_metric_delta(
    metric: str, current: float | None, previous: float | None, *, tolerance: float = 1e-9,
) -> MetricDelta:
    """Calculate mathematical and direction-aware change without imputing missing values."""
    if metric not in METRIC_COLUMNS:
        raise KeyError(f"Unknown metric: {metric}")
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    direction = "lower" if metric in LOWER_IS_BETTER else "higher"
    if current is None or previous is None:
        return MetricDelta(metric, current, previous, None, None, direction, DeltaStatus.NOT_AVAILABLE)
    raw_delta = current - previous
    performance_delta = -raw_delta if direction == "lower" else raw_delta
    if abs(performance_delta) <= tolerance:
        performance_delta = 0.0
        status = DeltaStatus.UNCHANGED
    else:
        status = DeltaStatus.IMPROVED if performance_delta > 0 else DeltaStatus.DECLINED
    percent_change = None if previous == 0 else (raw_delta / abs(previous)) * 100.0
    return MetricDelta(metric, current, previous, raw_delta, performance_delta,
                       direction, status, percent_change)


def compare_assessments(
    current: AthleteAssessment, previous: AthleteAssessment | None, *, tolerance: float = 1e-9,
) -> list[MetricDelta]:
    """Compare all ten metrics; a missing previous assessment yields ten N/A deltas."""
    if previous is not None and current.athlete_id != previous.athlete_id:
        raise ValueError("Cannot compare assessments belonging to different athletes")
    return [calculate_metric_delta(
        metric, current.raw_metrics.get(metric),
        None if previous is None else previous.raw_metrics.get(metric), tolerance=tolerance,
    ) for metric in METRIC_COLUMNS]


def delta_records(
    current: AthleteAssessment, previous: AthleteAssessment | None, *, tolerance: float = 1e-9,
) -> list[dict[str, object]]:
    """Return audit-friendly flat records for a latest/previous comparison."""
    records = []
    for delta in compare_assessments(current, previous, tolerance=tolerance):
        record: dict[str, object] = {
            "athlete_id": current.athlete_id,
            "athlete": current.athlete_name,
            "current_date": current.assessment_date,
            "previous_date": None if previous is None else previous.assessment_date,
        }
        record.update(asdict(delta))
        records.append(record)
    return records
