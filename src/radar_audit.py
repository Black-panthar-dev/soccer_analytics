"""Generate representative real-data radar images for visual inspection."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .metric_audit import PROJECT_ROOT
from .radar_chart import RADAR_METRICS, generate_radar_chart


def _percentiles(row: pd.Series) -> dict[str, object]:
    return {metric: row[f"{metric}_percentile"] for metric in RADAR_METRICS}


def _comparison_percentiles(row: pd.Series) -> dict[str, object]:
    return {metric: row[f"{metric}_age_group_average_percentile"] for metric in RADAR_METRICS}


def _safe_stem(value: object) -> str:
    return "_".join("".join(character if character.isalnum() else " " for character in str(value)).split())


def run_radar_audit(project_root: Path = PROJECT_ROOT) -> pd.DataFrame:
    source = project_root / "output/debug/percentile_metrics.csv"
    frame = pd.read_csv(source)
    percentile_columns = [f"{metric}_percentile" for metric in RADAR_METRICS]
    timing_columns = [f"{metric}_percentile" for metric in
                      ("dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best", "figure8_worst")]
    available = frame[percentile_columns].notna()
    chosen: list[tuple[str, pd.Series]] = []
    used: set[int] = set()

    def choose(label: str, candidates: pd.DataFrame, sort_column: str | None = None,
               ascending: bool = True) -> None:
        candidates = candidates.loc[~candidates.index.isin(used)]
        if sort_column is not None:
            candidates = candidates.sort_values(sort_column, ascending=ascending)
        if candidates.empty:
            raise RuntimeError(f"No real-data candidate found for radar example {label}")
        row = candidates.iloc[0]
        used.add(int(row.name))
        chosen.append((label, row))

    scored = frame.assign(_mean_percentile=frame[percentile_columns].mean(axis=1),
                          _distance_from_50=(frame[percentile_columns].mean(axis=1) - 50).abs())
    choose("all_10_percentiles", scored.loc[available.all(axis=1)], "full_name")
    missing_juggling = frame[[f"{m}_percentile" for m in RADAR_METRICS if m.startswith("juggling")]].isna().all(axis=1)
    choose("missing_juggling", scored.loc[missing_juggling & available[timing_columns].all(axis=1)], "full_name")
    choose("one_missing_timing", scored.loc[available[timing_columns].sum(axis=1).eq(4)], "full_name")
    choose("high_performing", scored.loc[available.sum(axis=1).ge(8)], "_mean_percentile", False)
    choose("mixed_performance", scored.loc[available.sum(axis=1).ge(8)], "_distance_from_50")

    root = project_root / "output/debug/radar"
    overlay_dir, debug_dir = root / "overlay", root / "debug"
    records: list[dict[str, object]] = []
    for label, row in chosen:
        stem = f"{label}__{_safe_stem(row['full_name'])}"
        comparison = _comparison_percentiles(row)
        overlay = generate_radar_chart(_percentiles(row), overlay_dir / f"{stem}.png",
                                       comparison, mode="overlay")
        standalone = generate_radar_chart(_percentiles(row), debug_dir / f"{stem}.png",
                                          comparison, mode="debug")
        records.append({"example": label, "athlete": row["full_name"], "age_group": row["age_group"],
                        "overlay_path": str(overlay.path), "debug_path": str(standalone.path),
                        "missing_metrics": "|".join(overlay.missing_athlete_metrics),
                        "missing_comparison_metrics": "|".join(overlay.missing_comparison_metrics)})
    manifest = pd.DataFrame(records)
    manifest.to_csv(root / "radar_examples_manifest.csv", index=False)
    return manifest


def main() -> int:
    print(run_radar_audit().to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
