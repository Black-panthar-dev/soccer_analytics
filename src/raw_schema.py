"""Raw source schemas with positional details isolated from business logic."""

from __future__ import annotations

from dataclasses import dataclass


SOURCE_ROW_COLUMN = "_source_row"


@dataclass(frozen=True)
class HardwareRawSchema:
    """Structural schema for the headerless A-CHAMPS export.

    No business meaning is assigned to any position here.
    """

    column_count: int = 34
    # Client-verified identity positions. Business mappings remain centralized here.
    athlete_name_index: int = 1
    athlete_email_index: int = 2
    drill_name_index: int = 3
    assessment_timestamp_index: int = 10
    total_time_index: int = 12
    hit_count_index: int = 14
    sprint_first_split_index: int = 21
    sprint_second_split_index: int = 22
    # Inspection-confirmed timing-like positions, used only for format validation.
    timing_value_indexes: tuple[int, ...] = (12, *range(20, 34))

    @property
    def column_indexes(self) -> tuple[int, ...]:
        """Return the expected zero-based raw column indexes."""
        return tuple(range(self.column_count))


HARDWARE_RAW_SCHEMA = HardwareRawSchema()

ROSTER_REQUIRED_COLUMNS: tuple[str, ...] = (
    "TEST TIME",
    "Team Name",
    "First Name",
    "Last Name",
    "Gender",
    "Birthday",
    "Age Group",
    "Parent Contact",
)

JUGGLING_REQUIRED_COLUMNS: tuple[str, ...] = (
    "First Name",
    "Last Name",
    "Dominant",
    "Non-Dominant",
    "Thighs",
)
