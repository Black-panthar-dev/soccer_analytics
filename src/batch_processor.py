"""Fault-isolated production generation of two-page athlete reports."""

from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pandas as pd
from PIL import Image

from .config_loader import load_config
from .metric_audit import PROJECT_ROOT
from .percentile_audit import run_percentile_audit
from .report_generator import render_two_page_preview, report_layout_from_config


MANIFEST_COLUMNS = ["athlete_name", "age_group", "team_name", "assessment_date",
                    "page1_png", "page2_png", "pdf_path", "generation_status", "notes"]
FAILED_COLUMNS = ["athlete_name", "age_group", "generation_status", "reason"]
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def safe_athlete_stem(first_name: object, last_name: object) -> str:
    """Return a stable Last_First ASCII filename stem."""
    parts = []
    for value in (last_name, first_name):
        if not pd.isna(value) and str(value).strip():
            text = unicodedata.normalize("NFKD", str(value).strip())
            ascii_text = text.encode("ascii", "ignore").decode("ascii")
            # Preserve authoritative internal casing while preventing lowercase-only filenames.
            parts.append(ascii_text[:1].upper() + ascii_text[1:])
    stem = "_".join(parts) or "Unknown_Athlete"
    return _UNSAFE.sub("_", stem).strip("_-") or "Unknown_Athlete"


def render_final_pdf(page1_path: Path, page2_path: Path,
                     output_pdf_path: Path) -> Path:
    """Combine full-resolution PNG pages into an ordered two-page PDF."""
    destination = Path(output_pdf_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(page1_path) as first_source, Image.open(page2_path) as second_source:
        first = first_source.convert("RGB")
        second = second_source.convert("RGB")
        if first.size != second.size:
            raise ValueError("PDF source pages must have identical dimensions")
        first.save(destination, "PDF", save_all=True, append_images=[second],
                   resolution=144.0, quality=95, optimize=False)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"PDF was not created successfully: {destination}")
    return destination


def count_pdf_pages(path: Path) -> int:
    """Count PDF page objects without adding another runtime dependency."""
    content = Path(path).read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?!s)\b", content))


def generate_batch_reports(
    assessments: pd.DataFrame, config: Mapping[str, object], project_root: Path,
    output_root: Path, *, run_timestamp: str | None = None,
) -> dict[str, object]:
    root = Path(project_root)
    output = Path(output_root)
    page1_dir, page2_dir, pdf_dir = (output / "png/page1", output / "png/page2", output / "pdf")
    for directory in (page1_dir, page2_dir, pdf_dir):
        directory.mkdir(parents=True, exist_ok=True)
    paths = config.get("paths")
    page2_config = config.get("page2_layout")
    if not isinstance(paths, dict) or not isinstance(page2_config, dict):
        raise ValueError("Config requires paths and page2_layout objects")
    layout = report_layout_from_config(config)
    template = root / str(paths["page1_clean_template"])
    sogility_logo = root / str(paths["page2_sogility_logo"])
    club_logo = root / "logos/STLDA LOGO.png"
    logo_defaults = config.get("logo_defaults", {})
    place_page1_club_logo = bool(
        logo_defaults.get("page1_club_logo_overlay", True)
        if isinstance(logo_defaults, dict) else True
    )
    timestamp = run_timestamp or datetime.now(timezone.utc).isoformat()
    manifest_records: list[dict[str, object]] = []
    failed_records: list[dict[str, object]] = []
    log_lines = [f"Report generation started: {timestamp}"]
    seen_stems: set[str] = set()
    eligible_count = success_count = skipped_count = failure_count = missing_count = 0

    for _, row in assessments.iterrows():
        athlete_name = str(row.get("full_name") or "Unknown Athlete")
        age_group = row.get("age_group")
        base = {"athlete_name": athlete_name, "age_group": age_group,
                "team_name": row.get("team_name"), "assessment_date": row.get("assessment_date"),
                "page1_png": "", "page2_png": "", "pdf_path": ""}
        if pd.isna(age_group) or not str(age_group).strip():
            skipped_count += 1
            reason = "Missing authoritative age group"
            manifest_records.append({**base, "generation_status": "skipped", "notes": reason})
            failed_records.append({"athlete_name": athlete_name, "age_group": age_group,
                                   "generation_status": "skipped", "reason": reason})
            log_lines.append(f"SKIPPED | {athlete_name} | {reason}")
            continue
        eligible_count += 1
        stem = safe_athlete_stem(row.get("first_name"), row.get("last_name"))
        if stem.casefold() in seen_stems:
            failure_count += 1
            reason = f"Duplicate output filename stem: {stem}"
            manifest_records.append({**base, "generation_status": "failed", "notes": reason})
            failed_records.append({"athlete_name": athlete_name, "age_group": age_group,
                                   "generation_status": "failed", "reason": reason})
            log_lines.append(f"FAILED | {athlete_name} | {reason}")
            continue
        seen_stems.add(stem.casefold())
        page1 = page1_dir / f"{stem}_page1.png"
        page2 = page2_dir / f"{stem}_page2.png"
        pdf = pdf_dir / f"{stem}_Assessment_Report.pdf"
        try:
            render_two_page_preview(row.to_dict(), template, club_logo, sogility_logo,
                                    page1, page2, layout, page2_config,
                                    place_page1_club_logo=place_page1_club_logo)
            render_final_pdf(page1, page2, pdf)
            if count_pdf_pages(pdf) != 2:
                raise RuntimeError("Generated PDF does not contain exactly two pages")
            if not all(path.is_file() and path.stat().st_size > 0 for path in (page1, page2, pdf)):
                raise RuntimeError("One or more generated output files are missing or empty")
            success_count += 1
            if any(pd.isna(row.get(metric)) for metric in
                   ("dash_10y", "dash_20y", "shuttle_5_10_5", "figure8_best", "figure8_worst",
                    "passing_90", "passing_180", "juggling_dominant",
                    "juggling_non_dominant", "juggling_thighs")):
                missing_count += 1
            manifest_records.append({**base, "page1_png": str(page1), "page2_png": str(page2),
                                     "pdf_path": str(pdf), "generation_status": "success", "notes": ""})
            log_lines.append(f"SUCCESS | {athlete_name} | {pdf}")
        except Exception as exc:  # one athlete must never terminate the batch
            failure_count += 1
            reason = f"{type(exc).__name__}: {exc}"
            manifest_records.append({**base, "page1_png": str(page1), "page2_png": str(page2),
                                     "pdf_path": str(pdf), "generation_status": "failed", "notes": reason})
            failed_records.append({"athlete_name": athlete_name, "age_group": age_group,
                                   "generation_status": "failed", "reason": reason})
            log_lines.append(f"FAILED | {athlete_name} | {reason}")

    manifest = pd.DataFrame.from_records(manifest_records, columns=MANIFEST_COLUMNS)
    failed = pd.DataFrame.from_records(failed_records, columns=FAILED_COLUMNS)
    summary = pd.DataFrame([{"run_timestamp": timestamp, "total_input_assessments": len(assessments),
        "total_eligible_athletes": eligible_count, "total_pdfs_generated": success_count,
        "total_failures": failure_count, "total_skipped": skipped_count,
        "total_with_missing_metrics": missing_count}])
    manifest.to_csv(output / "report_manifest.csv", index=False)
    summary.to_csv(output / "batch_summary.csv", index=False)
    failed.to_csv(output / "failed_reports.csv", index=False)
    log_lines.append(f"SUMMARY | eligible={eligible_count} generated={success_count} "
                     f"failed={failure_count} skipped={skipped_count}")
    (output / "generation_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return {"manifest": manifest, "summary": summary.iloc[0].to_dict(), "failed": failed,
            "output_root": output}


def run_production_batch(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = Path(project_root)
    run_percentile_audit(root)
    assessments = pd.read_csv(root / "output/debug/percentile_metrics.csv")
    config = load_config(root / "config/config.json")
    return generate_batch_reports(assessments, config, root, root / "output/final")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = run_production_batch(args.project_root)
    summary = result["summary"]
    print("Report generation complete")
    print(f"Eligible: {summary['total_eligible_athletes']}")
    print(f"Generated: {summary['total_pdfs_generated']}")
    print(f"Failed: {summary['total_failures']}")
    print(f"Skipped: {summary['total_skipped']}")
    return 0 if summary["total_failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
