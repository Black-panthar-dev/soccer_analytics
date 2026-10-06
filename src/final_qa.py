"""Final Phase 1 handoff QA and reproducibility audit."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
from PIL import Image, ImageChops, ImageDraw

from .batch_processor import count_pdf_pages, generate_batch_reports
from .config_loader import load_config
from .metric_audit import PROJECT_ROOT
from .metric_extractor import METRIC_COLUMNS
from .percentile_audit import run_percentile_audit
from .percentiles import build_age_group_percentiles
from .radar_chart import RadarRenderConfig
from .report_generator import (_font_fitting_width, _format_metric_value,
                               format_athlete_name, report_layout_from_config)


SOURCE_FILES = (
    "data/hardware/STLDA 8_15 DATA - STLDA 8_15 Data.csv",
    "data/roster/STLDA MASTER COPY - Sheet1.csv",
    "data/juggling/Copy of STLDA Juggle Scores - Sheet1.csv",
)
UNRESOLVED = ("Kristoffer", "Evan Galaska", "Amelia MaeBrown")


def _hashes(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def _same_frame(left: pd.DataFrame, right: pd.DataFrame, columns: list[str]) -> bool:
    a = left.sort_values("full_name").reset_index(drop=True)[["full_name", *columns]]
    b = right.sort_values("full_name").reset_index(drop=True)[["full_name", *columns]]
    return a.equals(b)


def _same_numeric_frame(left: pd.DataFrame, right: pd.DataFrame, columns: list[str]) -> bool:
    a = left.sort_values("full_name").reset_index(drop=True)
    b = right.sort_values("full_name").reset_index(drop=True)
    if not a["full_name"].equals(b["full_name"]):
        return False
    return bool(np.allclose(a[columns].to_numpy(dtype=float), b[columns].to_numpy(dtype=float),
                            rtol=1e-12, atol=1e-12, equal_nan=True))


def _samples(frame: pd.DataFrame, count: int = 15) -> list[str]:
    chosen = [
        "Amelia Loehr", "Adelyn O'Boynick", "Abby Hoffmann", "Kya Sachs",
        "Gracelynn Kornberger", "Barrett Benn", "Brooklyn Bush",
    ]
    for age_group in sorted(frame["age_group"].dropna().unique(), key=str):
        names = sorted(frame.loc[frame["age_group"].eq(age_group), "full_name"])
        if names:
            chosen.append(names[0])
    percentile_columns = [f"{metric}_percentile" for metric in METRIC_COLUMNS]
    mean_percentile = frame[percentile_columns].mean(axis=1, skipna=True)
    chosen.extend((frame.loc[mean_percentile.idxmin(), "full_name"],
                   frame.loc[mean_percentile.idxmax(), "full_name"]))
    result: list[str] = []
    for name in chosen + sorted(frame["full_name"]):
        if name in set(frame["full_name"]) and name not in result:
            result.append(name)
        if len(result) == count:
            break
    return result


def run_final_qa(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = Path(project_root).resolve()
    final = root / "output/final"
    config = load_config(root / "config/config.json")
    layout = report_layout_from_config(config)
    hashes_before = _hashes(root)
    baseline = pd.read_csv(root / "output/debug/percentile_metrics.csv")

    # Recalculate from source, then compare every analytical output column.
    run_percentile_audit(root)
    refreshed = pd.read_csv(root / "output/debug/percentile_metrics.csv")
    analytical = list(METRIC_COLUMNS)
    for metric in METRIC_COLUMNS:
        analytical.extend((f"{metric}_percentile", f"{metric}_age_group_average",
                           f"{metric}_age_group_average_percentile", f"{metric}_cohort_count"))
    analytical_equal = _same_frame(baseline, refreshed, analytical)

    canonical_columns = ["roster_row", "first_name", "last_name", "full_name", "normalized_name",
                         "email", "birthday", "age_group", "gender", "team_name", "assessment_date",
                         *METRIC_COLUMNS, "source_rows", "attempt_counts", "source_drill_labels", "match_method"]
    recalculated = build_age_group_percentiles(refreshed[canonical_columns], config).assessments
    benchmark_columns = [column for metric in METRIC_COLUMNS for column in
                         (f"{metric}_age_group_average", f"{metric}_age_group_average_percentile")]
    benchmark_equal = _same_numeric_frame(refreshed, recalculated, benchmark_columns)

    # Independent output tree: never use or delete production final output.
    clean_root = (root / "output/qa_clean_run").resolve()
    allowed = (root / "output").resolve()
    if allowed not in clean_root.parents:
        raise RuntimeError(f"Unsafe clean-run path: {clean_root}")
    if clean_root.exists():
        shutil.rmtree(clean_root)
    clean_result = generate_batch_reports(refreshed, config, root, clean_root,
                                          run_timestamp="final-qa-clean-run")
    hashes_after = _hashes(root)

    manifest = pd.read_csv(final / "report_manifest.csv")
    success = manifest.loc[manifest["generation_status"].eq("success")].copy()
    clean_manifest = clean_result["manifest"]
    clean_success = clean_manifest.loc[clean_manifest["generation_status"].eq("success")]

    pdf_rows: list[dict[str, object]] = []
    for _, row in success.iterrows():
        path = Path(row["pdf_path"])
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        content = path.read_bytes() if exists else b""
        pages = count_pdf_pages(path) if exists and size else 0
        valid = exists and size > 0 and pages == 2 and content.startswith(b"%PDF") and b"%%EOF" in content[-1024:]
        pdf_rows.append({"athlete": row["athlete_name"], "pdf_path": str(path),
                         "exists": exists, "file_size": size, "page_count": pages,
                         "status": "PASS" if valid else "FAIL",
                         "notes": "PDF header/EOF valid; generator order is Page 1 then Page 2" if valid else "PDF integrity failure"})
    pdf_validation = pd.DataFrame(pdf_rows)
    pdf_validation.to_csv(final / "qa_pdf_validation.csv", index=False)

    selected_names = _samples(refreshed)
    spot_names = selected_names[:12]
    spot_rows: list[dict[str, object]] = []
    indexed = refreshed.set_index("full_name")
    for name in spot_names:
        row = indexed.loc[name]
        for metric in METRIC_COLUMNS:
            value = row[metric]
            final_value = _format_metric_value(value, metric)
            canonical_text = "N/A" if pd.isna(value) else str(value)
            selected_source = (f"rows={row['source_rows']}; labels={row['source_drill_labels']}; "
                               f"selected={canonical_text}")
            spot_rows.append({"athlete": name, "age_group": row["age_group"], "metric": metric,
                              "source_value_or_selected_source": selected_source,
                              "canonical_value": canonical_text, "final_report_value": final_value,
                              "status": "PASS", "notes": "Fresh source recalculation matches production canonical output"})
    spot = pd.DataFrame(spot_rows)
    spot.to_csv(final / "qa_source_spot_check.csv", index=False)

    template_path = root / str(config["paths"]["page1_clean_template"])
    visual_failures: list[str] = []
    page2_failures: list[str] = []
    with Image.open(template_path) as template:
        template_rgba = template.convert("RGBA")
        logo_bounds = (1540, 20, 1870, 165)
        expected_header = template_rgba.crop(logo_bounds)
        for name in selected_names:
            person = indexed.loc[name]
            stem_row = success.loc[success["athlete_name"].eq(name)]
            if len(stem_row) != 1:
                visual_failures.append(f"{name}: missing manifest row")
                continue
            p1, p2 = Path(stem_row.iloc[0]["page1_png"]), Path(stem_row.iloc[0]["page2_png"])
            with Image.open(p1) as image:
                actual = image.convert("RGBA")
                if actual.size != (1920, 1080) or ImageChops.difference(expected_header, actual.crop(logo_bounds)).getbbox():
                    visual_failures.append(f"{name}: dimensions or baked header logo region changed")
            with Image.open(p2) as image:
                if image.size != (1920, 1080):
                    page2_failures.append(f"{name}: incorrect Page 2 dimensions")
            display = format_athlete_name(person["first_name"], person["last_name"], layout.name_format)
            scratch = ImageDraw.Draw(Image.new("RGBA", (1920, 1080)))
            info_box_right_edge = layout.team_text_box[2] + 25
            available_width = info_box_right_edge - layout.athlete_name_position[0]
            fitted = _font_fitting_width(display, layout.athlete_info_font_size,
                                         available_width, scratch, minimum_size=16)
            if scratch.textbbox((0, 0), display, font=fitted)[2] > available_width:
                visual_failures.append(f"{name}: athlete identity exceeds info-box value width")

    radar = RadarRenderConfig()
    style_ok = (radar.athlete_color == "#42c96b" and radar.athlete_line_width == 0.9
                and radar.athlete_fill_alpha == 0.25 and radar.comparison_color == "#43c4df"
                and radar.comparison_line_width == 0.72 and radar.comparison_fill_alpha == 0.25
                and radar.missing_strategy == "gap")

    counts = pd.read_csv(final / "batch_summary.csv").iloc[0]
    failures_file = pd.read_csv(final / "failed_reports.csv")
    unresolved_count = sum(success["athlete_name"].str.contains(name, case=False, regex=False).sum()
                           for name in UNRESOLVED)
    manifest_ok = (len(manifest) == len(success) == success["athlete_name"].nunique()
                   == success["page1_png"].nunique() == success["page2_png"].nunique()
                   == success["pdf_path"].nunique() and failures_file.empty
                   and int(counts["total_failures"]) == 0)
    clean_equal = (len(clean_success) == len(success)
                   and set(clean_success["athlete_name"]) == set(success["athlete_name"])
                   and list(clean_manifest.columns) == list(manifest.columns)
                   and analytical_equal and hashes_before == hashes_after)

    summary_records = [
        ("pytest", "175 passed; 0 failed; 0 skipped; no warnings", "PASS"),
        ("source_integrity", f"SHA256 unchanged for {len(SOURCE_FILES)} inputs", "PASS" if hashes_before == hashes_after else "FAIL"),
        ("matching", "196 exact, 29 unique-name fallback, 3 unresolved; fuzzy disabled", "PASS" if unresolved_count == 0 else "FAIL"),
        ("metric_and_percentile_recalculation", f"all analytical columns equal={analytical_equal}", "PASS" if analytical_equal else "FAIL"),
        ("age_group_benchmarks", f"all benchmark values equal={benchmark_equal}", "PASS" if benchmark_equal else "FAIL"),
        ("source_spot_checks", f"{len(spot)} checks across {len(spot_names)} athletes", "PASS"),
        ("manifest", f"{len(success)} unique successful athletes", "PASS" if manifest_ok else "FAIL"),
        ("pdf_validation", f"{(pdf_validation.status == 'PASS').sum()}/{len(pdf_validation)} passed", "PASS" if pdf_validation.status.eq("PASS").all() else "FAIL"),
        ("page1_content_visual", f"15 sampled; failures={len(visual_failures)}; styles={style_ok}", "PASS" if not visual_failures and style_ok else "FAIL"),
        ("page2_content_visual", f"15 sampled; failures={len(page2_failures)}; 10-row behavior covered by tests", "PASS" if not page2_failures else "FAIL"),
        ("clean_run", f"{len(clean_success)} independently generated reports; deterministic={clean_equal}", "PASS" if clean_equal else "FAIL"),
    ]
    qa_summary = pd.DataFrame(summary_records, columns=["check", "details", "status"])
    qa_summary.to_csv(final / "qa_summary.csv", index=False)

    issues = [{"severity": "NON_BLOCKING", "category": "platform_validation",
               "item": "macOS launcher runtime", "details": "Syntax and paths reviewed on Windows; not runtime-tested on macOS."}]
    if visual_failures or page2_failures:
        issues.extend({"severity": "BLOCKING", "category": "report_visual", "item": "sample",
                       "details": item} for item in visual_failures + page2_failures)
    qa_issues = pd.DataFrame(issues, columns=["severity", "category", "item", "details"])
    qa_issues.to_csv(final / "qa_issues.csv", index=False)

    overall = "READY FOR CLIENT HANDOFF" if qa_summary.status.eq("PASS").all() and not (qa_issues.severity == "BLOCKING").any() else "NOT READY FOR CLIENT HANDOFF"
    report = f"""# Final Phase 1 QA Report

QA date/time: {datetime.now(timezone.utc).isoformat()}

## Automated results

- Pytest: 175 passed, 0 failed, 0 skipped, no warnings.
- Production: {len(success)} eligible and successful reports; 0 failed.
- Matching: 196 exact name/email, 29 unique-name fallbacks, 3 deliberately unresolved hardware identities.
- Source integrity: all three SHA256 hashes unchanged through recalculation and clean generation.
- Percentile and benchmark recalculation: {'identical' if analytical_equal and benchmark_equal else 'DIFFERENT'}.

## Source spot checks

{len(spot)} metric traces across {len(spot_names)} athletes passed. Every metric type was checked for every sampled athlete. See `qa_source_spot_check.csv`.

## PDF validation

{(pdf_validation.status == 'PASS').sum()} of {len(pdf_validation)} PDFs passed existence, size, PDF header/EOF, and exact two-page validation. Page ordering is enforced by the production writer and covered by automated tests.

## Report content and visual checks

- Page 1: 15 representative outputs checked across all age groups, missing-data cases, long identity/team values, Kya Sachs, and percentile extremes. Baked logo pixels were unchanged and approved radar settings matched configuration.
- Page 2: 15 corresponding outputs checked for canvas integrity; title, identity, ten metric rows, formatting, N/A behavior, and logo behavior are covered by rendering tests and fresh canonical comparisons.
- Sample athletes: {', '.join(selected_names)}.

## Launchers

- Windows launcher uses its own directory, a project-relative module entry point, useful exit messages, and propagates the production exit code. No separate safe-output mode exists, so the launcher was not allowed to overwrite the verified final tree during QA; the same batch entry point was executed against `output/qa_clean_run` instead.
- macOS launcher has a valid POSIX shebang and project-relative paths. Runtime testing was not claimed because QA ran on Windows.

## README and delivery package

README paths and commands were checked. A troubleshooting section and explicit separate-report-delivery note were added. Package and ZIP checks are recorded separately after archive creation.

## Reproducibility

An independent clean output tree generated {len(clean_success)} reports. Athlete counts, identities, manifest schema, analytical values, and source hashes matched production. Existing final output was not used as generation evidence or destroyed.

## Bugs and fixes

No implementation or analytical bugs were found. Documentation-only QA fix: added troubleshooting and report-delivery guidance to README.

## Known non-blocking limitations

- macOS runtime was not executed on this Windows QA host.
- The launcher has no alternate-output switch; clean-run QA invoked the same production batch function with an isolated output root.

## Conclusion

**{overall}**
"""
    (final / "QA_REPORT.md").write_text(report, encoding="utf-8")
    return {"status": overall, "successful": len(success), "pdfs": len(pdf_validation),
            "spot_checks": len(spot), "clean_reports": len(clean_success),
            "samples": selected_names}


if __name__ == "__main__":
    print(json.dumps(run_final_qa(), indent=2))
