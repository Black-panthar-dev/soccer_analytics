"""Roster-authoritative athlete metric extraction and attempt selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Iterable

import pandas as pd

from .drill_normalizer import DEFAULT_DRILL_ALIASES, normalize_drill_name
from .matcher import MatchStatus, build_canonical_roster
from .normalizer import normalize_name
from .raw_schema import HARDWARE_RAW_SCHEMA, SOURCE_ROW_COLUMN
from .time_parser import parse_duration_to_seconds
from .validation import Severity, ValidationIssue


METRIC_COLUMNS: Final[tuple[str, ...]] = (
    "dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best",
    "figure8_worst", "passing_90", "passing_180", "juggling_dominant",
    "juggling_non_dominant", "juggling_thighs",
)
IDENTITY_COLUMNS: Final[tuple[str, ...]] = (
    "roster_row", "first_name", "last_name", "full_name", "normalized_name",
    "email", "birthday", "age_group", "gender", "team_name", "assessment_date",
)
SAFE_HARDWARE_MATCHES: Final[set[str]] = {
    MatchStatus.EXACT_NAME_EMAIL, MatchStatus.UNIQUE_NAME_FALLBACK,
}
SAFE_JUGGLING_MATCHES: Final[set[str]] = {MatchStatus.UNIQUE_NAME_MATCH}


@dataclass
class ExtractionResult:
    canonical: pd.DataFrame
    issues: list[ValidationIssue]
    hardware_attempts: pd.DataFrame


def select_fastest_time(values: Iterable[object]) -> float | None:
    """Return the lowest valid duration, ignoring missing or malformed values."""
    valid = [parsed for value in values if (parsed := parse_duration_to_seconds(value)) is not None]
    return min(valid) if valid else None


def select_highest_score(values: Iterable[object]) -> float | None:
    """Return the highest finite numeric score without converting missing to zero."""
    valid: list[float] = []
    for value in values:
        number = pd.to_numeric(value, errors="coerce")
        if not pd.isna(number):
            valid.append(float(number))
    return max(valid) if valid else None


def extract_sprint_metrics(rows: pd.DataFrame) -> dict[str, float | None]:
    return extract_sprint_metrics_with_tolerance(rows)


def sprint_attempt_components(row: pd.Series,
                              tolerance_seconds: float = 0.01) -> dict[str, object]:
    """Parse a sprint row and identify whether it is a complete 20-yard attempt."""
    first = parse_duration_to_seconds(row[HARDWARE_RAW_SCHEMA.sprint_first_split_index])
    second = parse_duration_to_seconds(row[HARDWARE_RAW_SCHEMA.sprint_second_split_index])
    total = parse_duration_to_seconds(row[HARDWARE_RAW_SCHEMA.total_time_index])
    difference = abs(total - (first + second)) if None not in (first, second, total) else None
    complete = difference is not None and difference <= tolerance_seconds
    return {
        "first_split": first, "second_split": second, "total_time": total,
        "sum_difference": difference, "complete_20y": complete,
    }


def extract_sprint_metrics_with_tolerance(
    rows: pd.DataFrame, tolerance_seconds: float = 0.01,
) -> dict[str, float | None]:
    components = [sprint_attempt_components(row, tolerance_seconds) for _, row in rows.iterrows()]
    complete_totals = [item["total_time"] for item in components if item["complete_20y"]]
    return {
        "dash_10y": select_fastest_time(rows[HARDWARE_RAW_SCHEMA.sprint_first_split_index]),
        "dash_20y": min(complete_totals) if complete_totals else None,
    }


def extract_5_10_5(rows: pd.DataFrame) -> dict[str, float | None]:
    return {"shuttle_5_10_5": select_fastest_time(rows[HARDWARE_RAW_SCHEMA.total_time_index])}


def extract_figure8_metrics(rows: pd.DataFrame) -> dict[str, float | None]:
    values = [parsed for value in rows[HARDWARE_RAW_SCHEMA.total_time_index]
              if (parsed := parse_duration_to_seconds(value)) is not None]
    return {
        "figure8_best": min(values) if values else None,
        "figure8_worst": max(values) if len(values) > 1 else None,
    }


def extract_passing_metrics(rows: pd.DataFrame, metric: str) -> dict[str, float | None]:
    if metric not in {"passing_90", "passing_180"}:
        raise ValueError(f"Unsupported passing metric: {metric}")
    return {metric: select_highest_score(rows[HARDWARE_RAW_SCHEMA.hit_count_index])}


def extract_juggling_metrics(rows: pd.DataFrame) -> dict[str, float | None]:
    if rows.empty:
        return {name: None for name in METRIC_COLUMNS[-3:]}
    def supplied_score(column: str) -> float | None:
        value = pd.to_numeric(rows.iloc[0][column], errors="coerce")
        return None if pd.isna(value) else float(value)
    return {
        "juggling_dominant": supplied_score("Dominant"),
        "juggling_non_dominant": supplied_score("Non-Dominant"),
        "juggling_thighs": supplied_score("Thighs"),
    }


def _safe_match_map(matches: pd.DataFrame, statuses: set[str]) -> dict[tuple[object, ...], pd.Series]:
    safe = matches.loc[matches["status"].isin(statuses)]
    result: dict[tuple[object, ...], pd.Series] = {}
    for _, row in safe.iterrows():
        if row["source"] == "hardware":
            key = (row["normalized_source_name"], row["normalized_source_email"])
        else:
            key = (row["normalized_source_name"],)
        result[key] = row
    return result


def _required_value_issue(row: pd.Series, metric: str, column: int) -> ValidationIssue:
    return ValidationIssue(
        Severity.WARNING, "invalid_required_metric_value", "hardware",
        f"Required source value for {metric} is missing or invalid",
        row[SOURCE_ROW_COLUMN], row[HARDWARE_RAW_SCHEMA.athlete_name_index],
        row.get("_roster_row"), {"metric": metric, "column_index": column, "value": row[column]},
    )


def _prepare_hardware(hardware: pd.DataFrame, matches: pd.DataFrame,
                      aliases: dict[str, str]) -> pd.DataFrame:
    match_map = _safe_match_map(matches, SAFE_HARDWARE_MATCHES)
    records: list[dict[object, object]] = []
    for _, row in hardware.iterrows():
        name = normalize_name(row[HARDWARE_RAW_SCHEMA.athlete_name_index])
        email_value = row[HARDWARE_RAW_SCHEMA.athlete_email_index]
        from .normalizer import normalize_email
        match = match_map.get((name, normalize_email(email_value)))
        if match is None:
            continue
        timestamp = pd.to_datetime(
            row[HARDWARE_RAW_SCHEMA.assessment_timestamp_index],
            format="%B %d, %Y - %I:%M %p", errors="coerce",
        )
        drill = normalize_drill_name(row[HARDWARE_RAW_SCHEMA.drill_name_index], aliases)
        if pd.isna(timestamp) or drill is None:
            continue
        record = row.to_dict()
        record.update(_roster_row=match["matched_roster_row"], _assessment_date=timestamp.date(),
                      _canonical_drill=drill)
        records.append(record)
    return pd.DataFrame.from_records(records)


def _prepare_juggling(juggling: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    match_map = _safe_match_map(matches, SAFE_JUGGLING_MATCHES)
    records: list[dict[object, object]] = []
    for _, row in juggling.iterrows():
        full_name = " ".join(str(row[c]).strip() for c in ("First Name", "Last Name")
                             if not pd.isna(row[c])).strip()
        match = match_map.get((normalize_name(full_name),))
        if match is not None:
            record = row.to_dict()
            record["_roster_row"] = match["matched_roster_row"]
            records.append(record)
    return pd.DataFrame.from_records(records)


def extract_canonical_assessments(
    hardware: pd.DataFrame, roster: pd.DataFrame, juggling: pd.DataFrame,
    hardware_matches: pd.DataFrame, juggling_matches: pd.DataFrame,
    drill_aliases: dict[str, str] | None = None,
    sprint_tolerance_seconds: float = 0.01,
) -> ExtractionResult:
    """Build one canonical record per safely matched athlete and assessment date."""
    aliases = DEFAULT_DRILL_ALIASES if drill_aliases is None else drill_aliases
    prepared = _prepare_hardware(hardware, hardware_matches, aliases)
    prepared_juggling = _prepare_juggling(juggling, juggling_matches)
    canonical_roster = build_canonical_roster(roster).set_index("roster_row", drop=False)
    issues: list[ValidationIssue] = []
    records: list[dict[str, object]] = []
    if prepared.empty:
        columns = list(IDENTITY_COLUMNS + METRIC_COLUMNS) + ["source_rows", "attempt_counts", "source_drill_labels", "match_method"]
        return ExtractionResult(pd.DataFrame(columns=columns), issues, prepared)

    match_method_by_row = (hardware_matches.loc[hardware_matches["status"].isin(SAFE_HARDWARE_MATCHES)]
                           .drop_duplicates("matched_roster_row").set_index("matched_roster_row")["match_method"])
    date_counts = prepared.groupby("_roster_row")["_assessment_date"].nunique()
    warned_undated_juggling: set[object] = set()
    extractors: tuple[tuple[str, Callable[[pd.DataFrame], dict[str, float | None]]], ...] = (
        ("sprints", lambda rows: extract_sprint_metrics_with_tolerance(rows, sprint_tolerance_seconds)),
        ("shuttle_5_10_5", extract_5_10_5),
        ("figure8", extract_figure8_metrics),
        ("passing_90", lambda rows: extract_passing_metrics(rows, "passing_90")),
        ("passing_180", lambda rows: extract_passing_metrics(rows, "passing_180")),
    )
    required = {
        "sprints": (("dash_10y", HARDWARE_RAW_SCHEMA.sprint_first_split_index, parse_duration_to_seconds),
                    ("dash_20y", HARDWARE_RAW_SCHEMA.total_time_index, parse_duration_to_seconds)),
        "shuttle_5_10_5": (("shuttle_5_10_5", HARDWARE_RAW_SCHEMA.total_time_index, parse_duration_to_seconds),),
        "figure8": (("figure8_best", HARDWARE_RAW_SCHEMA.total_time_index, parse_duration_to_seconds),),
        "passing_90": (("passing_90", HARDWARE_RAW_SCHEMA.hit_count_index, lambda v: pd.to_numeric(v, errors="coerce")),),
        "passing_180": (("passing_180", HARDWARE_RAW_SCHEMA.hit_count_index, lambda v: pd.to_numeric(v, errors="coerce")),),
    }
    for (roster_row, assessment_date), group in prepared.groupby(["_roster_row", "_assessment_date"], sort=True):
        athlete = canonical_roster.loc[roster_row]
        record = {column: athlete[column] for column in IDENTITY_COLUMNS if column != "assessment_date"}
        record["assessment_date"] = assessment_date
        record.update({metric: None for metric in METRIC_COLUMNS})
        counts: dict[str, int] = {}
        for drill, extractor in extractors:
            rows = group.loc[group["_canonical_drill"] == drill]
            counts[drill] = len(rows)
            if rows.empty:
                continue
            record.update(extractor(rows))
            for metric, column, parser in required[drill]:
                for _, source_row in rows.iterrows():
                    parsed = parser(source_row[column])
                    if parsed is None or pd.isna(parsed):
                        issues.append(_required_value_issue(source_row, metric, column))
            if drill == "figure8":
                valid_count = sum(parse_duration_to_seconds(value) is not None for value in rows[HARDWARE_RAW_SCHEMA.total_time_index])
                if valid_count == 1:
                    issues.append(ValidationIssue(Severity.WARNING, "single_figure8_attempt", "hardware",
                        "Only one valid Figure 8 attempt; Worst Time remains unavailable",
                        rows.iloc[0][SOURCE_ROW_COLUMN], athlete["full_name"], roster_row,
                        {"assessment_date": assessment_date}))
        jug_rows = prepared_juggling.loc[prepared_juggling["_roster_row"] == roster_row] if not prepared_juggling.empty else prepared_juggling
        if date_counts.get(roster_row, 0) > 1 and not jug_rows.empty:
            jug_rows = jug_rows.iloc[0:0]
            if roster_row not in warned_undated_juggling:
                issues.append(ValidationIssue(
                    Severity.WARNING, "ambiguous_juggling_assessment_date", "juggling",
                    "Undated juggling scores were not assigned across multiple assessment dates",
                    athlete_name=athlete["full_name"], roster_row=roster_row,
                    details={"assessment_dates": sorted(str(v) for v in
                        prepared.loc[prepared["_roster_row"] == roster_row, "_assessment_date"].unique())},
                ))
                warned_undated_juggling.add(roster_row)
        record.update(extract_juggling_metrics(jug_rows))
        record["source_rows"] = "|".join(str(v) for v in group[SOURCE_ROW_COLUMN].tolist())
        record["attempt_counts"] = ";".join(f"{key}:{value}" for key, value in counts.items())
        record["source_drill_labels"] = "|".join(sorted(set(str(v) for v in group[HARDWARE_RAW_SCHEMA.drill_name_index])))
        record["match_method"] = match_method_by_row.get(roster_row, pd.NA)
        records.append(record)
    canonical = pd.DataFrame.from_records(records)
    for metric in METRIC_COLUMNS:
        canonical[metric] = pd.to_numeric(canonical[metric], errors="coerce")
    return ExtractionResult(canonical, issues, prepared)


def write_canonical_debug_output(canonical: pd.DataFrame, output_directory: Path) -> Path:
    debug = Path(output_directory) / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    path = debug / "canonical_metrics.csv"
    canonical.to_csv(path, index=False)
    return path
