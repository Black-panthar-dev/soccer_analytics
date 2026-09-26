"""Generate the three approved-template PNG previews for Chunk 8A."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config_loader import load_config
from .metric_audit import PROJECT_ROOT
from .report_generator import render_report_preview, report_layout_from_config


def run_report_preview_audit(project_root: Path = PROJECT_ROOT) -> pd.DataFrame:
    config = load_config(project_root / "config/config.json")
    layout = report_layout_from_config(config)
    frame = pd.read_csv(project_root / "output/debug/percentile_metrics.csv")
    selections = (
        ("complete", "Amelia Loehr", "Amelia_Loehr_preview.png"),
        ("missing_juggling", "Adelyn O'Boynick", "Adelyn_O_Boynick_missing_juggling_preview.png"),
        ("missing_timing", "Abby Hoffmann", "Abby_Hoffmann_missing_timing_preview.png"),
    )
    template = project_root / "templates/Sogility GO Elite Athlete Assessment (2).png"
    logo = project_root / "logos/STLDA LOGO.png"
    output = project_root / "output/debug/reports"
    records: list[dict[str, object]] = []
    for example, full_name, filename in selections:
        matches = frame.loc[frame["full_name"] == full_name]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one canonical row for preview athlete {full_name}")
        result = render_report_preview(matches.iloc[0].to_dict(), template, logo,
                                       output / filename, layout)
        records.append({"example": example, "athlete": full_name, "path": str(result.path),
                        "dimensions": f"{result.dimensions[0]}x{result.dimensions[1]}",
                        "missing_metrics": "|".join(result.radar_missing_metrics)})
    manifest = pd.DataFrame(records)
    manifest.to_csv(output / "preview_manifest.csv", index=False)
    return manifest


def main() -> int:
    print(run_report_preview_audit().to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
