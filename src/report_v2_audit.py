"""Generate four two-page report preview pairs from stable percentile output."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config_loader import load_config
from .metric_audit import PROJECT_ROOT
from .report_generator import render_two_page_preview, report_layout_from_config


def _stem(name: str) -> str:
    return "_".join("".join(character if character.isalnum() else " " for character in name).split())


def run_report_v2_audit(project_root: Path = PROJECT_ROOT) -> pd.DataFrame:
    config = load_config(project_root / "config/config.json")
    layout = report_layout_from_config(config)
    page2_config = config.get("page2_layout")
    if not isinstance(page2_config, dict):
        raise ValueError("Config must contain page2_layout")
    paths = config.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("Config must contain paths")
    template = project_root / str(paths["page1_clean_template"])
    sogility_logo = project_root / str(paths["page2_sogility_logo"])
    club_logo = project_root / "logos/STLDA LOGO.png"
    frame = pd.read_csv(project_root / "output/debug/percentile_metrics.csv")
    athletes = ("Amelia Loehr", "Adelyn O'Boynick", "Abby Hoffmann", "Kya Sachs")
    output = project_root / "output/debug/final_preview"
    records: list[dict[str, object]] = []
    for full_name in athletes:
        matches = frame.loc[frame["full_name"] == full_name]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one percentile record for {full_name}")
        row = matches.iloc[0].to_dict()
        stem = _stem(full_name)
        page1 = output / f"{stem}_page1.png"
        page2 = output / f"{stem}_page2.png"
        result = render_two_page_preview(row, template, club_logo, sogility_logo,
                                         page1, page2, layout, page2_config,
                                         place_page1_club_logo=False)
        records.extend((
            {"athlete": full_name, "page": 1, "path": str(result.page1.path),
             "dimensions": f"{result.page1.dimensions[0]}x{result.page1.dimensions[1]}"},
            {"athlete": full_name, "page": 2, "path": str(result.page2.path),
             "dimensions": f"{result.page2.dimensions[0]}x{result.page2.dimensions[1]}"},
        ))
    manifest = pd.DataFrame(records)
    output.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output / "preview_manifest.csv", index=False)
    return manifest


def main() -> int:
    print(run_report_v2_audit().to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
