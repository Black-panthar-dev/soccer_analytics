"""Real-data eligibility audit and test-only Page 3 visual fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .assessment_history import AthleteAssessment, get_assessments_for_athlete
from .batch_processor import render_final_pdf
from .client_overrides import apply_roster_overrides
from .config_loader import load_config
from .loader import load_roster_csv
from .matcher import build_canonical_roster
from .metric_extractor import METRIC_COLUMNS
from .phase2_audit import PROJECT_ROOT, run_phase2_audit
from .progress_report import prepare_progress_comparison, render_progress_page
from .report_generator import render_two_page_preview, report_layout_from_config


def _fixture_assessment(name: str, day: int, values: list[float | None]) -> AthleteAssessment:
    metrics = dict(zip(METRIC_COLUMNS, values))
    return AthleteAssessment(
        name, name, date(2026, 8, day), "U10", "TEST FIXTURE TEAM", metrics,
        {metric: value is not None for metric, value in metrics.items()},
        {"fixture": True, "juggling_values_are_dated": True},
        {"first_name": name.split()[0], "last_name": name.split()[-1]},
    )


def progress_fixtures() -> dict[str, list[AthleteAssessment]]:
    """Synthetic histories used only for rendering and automated tests."""
    return {
        "TEST_DEBUG_improvement_heavy": [
            _fixture_assessment("Improvement Fixture", 15, [2.2, 4.2, 6.1, 18, 23, 6, 7, 8, 5, 3]),
            _fixture_assessment("Improvement Fixture", 20, [2.0, 3.9, 5.8, 17, 22, 9, 10, 11, 7, 5]),
        ],
        "TEST_DEBUG_decline_heavy": [
            _fixture_assessment("Decline Fixture", 15, [2.0, 3.8, 5.7, 17, 22, 10, 11, 12, 8, 6]),
            _fixture_assessment("Decline Fixture", 20, [2.2, 4.1, 6.0, 18, 24, 7, 8, 9, 6, 4]),
        ],
        "TEST_DEBUG_mixed": [
            _fixture_assessment("Mixed Fixture", 15, [2.1, 4.0, 6.0, 18, 23, 8, 9, 10, 7, 5]),
            _fixture_assessment("Mixed Fixture", 20, [2.0, 4.1, 5.8, 18, 24, 10, 8, 11, 6, 5]),
        ],
        "TEST_DEBUG_missing_historical_metric": [
            _fixture_assessment("Missing Metric", 15, [None, 4.0, 6.0, 18, 23, 8, 9, 10, 7, 5]),
            _fixture_assessment("Missing Metric", 20, [2.0, 3.9, 5.9, 17, 22, 9, 10, 11, 8, 6]),
        ],
        "TEST_DEBUG_unchanged": [
            _fixture_assessment("Unchanged Fixture", 15, [2.0, 4.0, 6.0, 18, 23, 8, 9, 10, 7, 5]),
            _fixture_assessment("Unchanged Fixture", 20, [2.0, 4.0, 6.0, 18, 23, 8, 9, 10, 7, 5]),
        ],
        "TEST_DEBUG_missing_dated_juggling": [
            _fixture_assessment("Missing Juggling", 15, [2.1, 4.1, 6.1, 18, 23, 8, 9, None, None, None]),
            _fixture_assessment("Missing Juggling", 20, [2.0, 4.0, 6.0, 17, 22, 9, 10, 11, 8, 6]),
        ],
    }


def _report_row(current: AthleteAssessment) -> dict[str, object]:
    first, _, last = (current.athlete_name or "Test Fixture").partition(" ")
    row: dict[str, object] = {
        "first_name": first, "last_name": last, "full_name": current.athlete_name,
        "birthday": "01/01/2010", "team_name": current.team, "age_group": current.age_group,
        "assessment_date": current.assessment_date,
    }
    for metric in METRIC_COLUMNS:
        row[metric] = current.raw_metrics[metric]
        row[f"{metric}_percentile"] = 50.0
        row[f"{metric}_age_group_average"] = current.raw_metrics[metric]
        row[f"{metric}_age_group_average_percentile"] = 50.0
    return row


def run_progress_audit(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = Path(project_root)
    history_result = run_phase2_audit(root)
    assessments = history_result["assessments"]
    config = load_config(root / "config/config.json")
    paths, inputs = config["paths"], config["input_files"]
    roster = apply_roster_overrides(
        load_roster_csv(root / paths["roster_input"] / inputs["roster"]), config)
    audit_rows: list[dict[str, object]] = []
    for _, athlete in build_canonical_roster(roster).iterrows():
        history = get_assessments_for_athlete(assessments, athlete["roster_row"])
        comparison = prepare_progress_comparison(history)
        latest = max(history, key=lambda item: item.assessment_date, default=None)
        previous = sorted(history, key=lambda item: item.assessment_date)[-2] if len(history) >= 2 else None
        audit_rows.append({
            "athlete": athlete["full_name"],
            "current_date": None if latest is None else latest.assessment_date,
            "previous_date": None if previous is None else previous.assessment_date,
            "page3_eligible": comparison is not None,
            "metrics_improved": 0 if comparison is None else comparison.metrics_improved,
            "metrics_declined": 0 if comparison is None else comparison.metrics_declined,
            "metrics_unchanged": 0 if comparison is None else comparison.metrics_unchanged,
            "metrics_na": 10 if comparison is None else comparison.metrics_na,
            "reason": "ELIGIBLE" if comparison else
                      ("NO_ASSESSMENT" if latest is None else "NO_PREVIOUS_ASSESSMENT"),
        })
    output = root / "output/phase2/debug"
    preview_dir = output / "progress_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output / "progress_comparison_audit.csv"
    pd.DataFrame(audit_rows).to_csv(audit_path, index=False)

    logo = root / str(paths["page2_sogility_logo"])
    previews: list[Path] = []
    pdfs: list[Path] = []
    for index, (stem, history) in enumerate(progress_fixtures().items()):
        comparison = prepare_progress_comparison(history)
        assert comparison is not None
        page3 = preview_dir / f"{stem}_page3.png"
        render_progress_page(comparison, page3, logo)
        previews.append(page3)
        if index < 2:
            page1, page2 = preview_dir / f"{stem}_page1.png", preview_dir / f"{stem}_page2.png"
            render_two_page_preview(
                _report_row(comparison.current), root / str(paths["page1_clean_template"]),
                root / "logos/STLDA LOGO.png", logo, page1, page2,
                report_layout_from_config(config), config["page2_layout"],
                place_page1_club_logo=False,
            )
            pdf = preview_dir / f"{stem}_3PAGE_REPORT.pdf"
            render_final_pdf(page1, page2, pdf, page3)
            pdfs.append(pdf)
    return {"audit_path": audit_path, "page3_eligible": sum(row["page3_eligible"] for row in audit_rows),
            "previews": previews, "pdfs": pdfs}


def main() -> int:
    result = run_progress_audit()
    print(f"Production Page 3 eligible: {result['page3_eligible']}")
    print(f"Fixture previews: {len(result['previews'])}")
    print(f"Fixture three-page PDFs: {len(result['pdfs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
