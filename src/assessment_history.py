"""Canonical, presentation-independent historical assessment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Iterable, Mapping

import pandas as pd

from .metric_extractor import METRIC_COLUMNS


ASSESSMENT_DATE_SOURCE: Final[str] = "hardware column 10 (assessment/session timestamp)"
AGE_GROUP_SOURCE: Final[str] = "current roster (historical age group unavailable)"
JUGGLING_DATE_LIMITATION: Final[str] = (
    "The current juggling source has no assessment-date column. Scores can be attached "
    "only when an athlete has one hardware assessment date; they are not copied across history."
)


def _optional_text(value: object) -> str | None:
    return None if pd.isna(value) else str(value)


def _optional_number(value: object) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def normalize_assessment_date(value: object) -> date | None:
    """Normalize a source assessment value to a calendar date."""
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError, OverflowError):
        return None
    return None if pd.isna(parsed) else parsed.date()


@dataclass(frozen=True)
class AthleteAssessment:
    """One athlete's selected raw metrics for exactly one assessment date."""

    athlete_id: object
    athlete_name: str | None
    assessment_date: date
    age_group: str | None
    team: str | None
    raw_metrics: Mapping[str, float | None]
    availability: Mapping[str, bool]
    source_metadata: Mapping[str, object]
    roster_identity: Mapping[str, object]

    def metric(self, name: str) -> float | None:
        if name not in METRIC_COLUMNS:
            raise KeyError(f"Unknown metric: {name}")
        return self.raw_metrics.get(name)


def assessments_from_canonical(canonical: pd.DataFrame) -> list[AthleteAssessment]:
    """Adapt Phase I canonical rows without changing their extraction behavior."""
    assessments: list[AthleteAssessment] = []
    for _, row in canonical.iterrows():
        assessment_date = normalize_assessment_date(row.get("assessment_date"))
        if assessment_date is None:
            continue
        metrics = {metric: _optional_number(row.get(metric)) for metric in METRIC_COLUMNS}
        assessments.append(AthleteAssessment(
            athlete_id=row.get("roster_row"),
            athlete_name=_optional_text(row.get("full_name")),
            assessment_date=assessment_date,
            age_group=_optional_text(row.get("age_group")),
            team=_optional_text(row.get("team_name")),
            raw_metrics=metrics,
            availability={metric: value is not None for metric, value in metrics.items()},
            source_metadata={
                "assessment_date_source": ASSESSMENT_DATE_SOURCE,
                "source_rows": _optional_text(row.get("source_rows")),
                "attempt_counts": _optional_text(row.get("attempt_counts")),
                "source_drill_labels": _optional_text(row.get("source_drill_labels")),
                "match_method": _optional_text(row.get("match_method")),
                "juggling_date_status": "undated_source",
            },
            roster_identity={
                "roster_row": row.get("roster_row"),
                "first_name": _optional_text(row.get("first_name")),
                "last_name": _optional_text(row.get("last_name")),
                "email": _optional_text(row.get("email")),
                "birthday": row.get("birthday"),
                "gender": _optional_text(row.get("gender")),
                "age_group_source": AGE_GROUP_SOURCE,
            },
        ))
    return sorted(assessments, key=lambda item: (str(item.athlete_id), item.assessment_date))


def get_assessments_for_athlete(
    assessments: Iterable[AthleteAssessment], athlete_id: object,
) -> list[AthleteAssessment]:
    """Return an athlete's assessments in chronological order."""
    return sorted(
        (item for item in assessments if item.athlete_id == athlete_id),
        key=lambda item: item.assessment_date,
    )


def get_latest_assessment(
    assessments: Iterable[AthleteAssessment], athlete_id: object | None = None,
) -> AthleteAssessment | None:
    selected = list(assessments) if athlete_id is None else get_assessments_for_athlete(assessments, athlete_id)
    return max(selected, key=lambda item: item.assessment_date, default=None)


def get_previous_assessment(
    assessments: Iterable[AthleteAssessment], athlete_id: object | None = None,
) -> AthleteAssessment | None:
    selected = list(assessments) if athlete_id is None else get_assessments_for_athlete(assessments, athlete_id)
    ordered = sorted(selected, key=lambda item: item.assessment_date)
    return ordered[-2] if len(ordered) >= 2 else None


def get_assessment_by_date(
    assessments: Iterable[AthleteAssessment], athlete_id: object, assessment_date: object,
) -> AthleteAssessment | None:
    target = normalize_assessment_date(assessment_date)
    if target is None:
        return None
    return next((item for item in assessments
                 if item.athlete_id == athlete_id and item.assessment_date == target), None)
