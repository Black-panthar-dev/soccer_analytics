from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image

from src.batch_processor import count_pdf_pages, render_final_pdf
from src.performance_delta import DeltaStatus
from src.progress_audit import progress_fixtures, run_progress_audit
from src.progress_report import format_change, prepare_progress_comparison, render_progress_page


ROOT = Path(__file__).resolve().parents[1]


def histories():
    return progress_fixtures()


def test_one_assessment_has_no_page3() -> None:
    history = histories()["TEST_DEBUG_improvement_heavy"]
    assert prepare_progress_comparison(history[:1]) is None


def test_two_assessments_have_page3() -> None:
    comparison = prepare_progress_comparison(histories()["TEST_DEBUG_improvement_heavy"])
    assert comparison is not None
    assert comparison.current.assessment_date.day == 20
    assert comparison.previous.assessment_date.day == 15


def test_three_assessments_compare_latest_to_immediately_previous() -> None:
    base = histories()["TEST_DEBUG_improvement_heavy"]
    earliest = base[0].__class__(
        base[0].athlete_id, base[0].athlete_name, base[0].assessment_date.replace(day=1),
        base[0].age_group, base[0].team, base[0].raw_metrics, base[0].availability,
        base[0].source_metadata, base[0].roster_identity)
    comparison = prepare_progress_comparison([base[1], earliest, base[0]])
    assert comparison is not None
    assert comparison.current.assessment_date.day == 20
    assert comparison.previous.assessment_date.day == 15


def _delta(fixture: str, metric: str):
    comparison = prepare_progress_comparison(histories()[fixture])
    assert comparison is not None
    return next(item for item in comparison.deltas if item.metric == metric)


def test_direction_aware_client_change_formatting() -> None:
    assert format_change(_delta("TEST_DEBUG_improvement_heavy", "dash_10y")) == "0.200 s faster"
    assert format_change(_delta("TEST_DEBUG_decline_heavy", "dash_10y")) == "0.200 s slower"
    assert format_change(_delta("TEST_DEBUG_improvement_heavy", "passing_90")) == "+3"
    assert format_change(_delta("TEST_DEBUG_decline_heavy", "passing_90")) == "-3"
    assert format_change(_delta("TEST_DEBUG_unchanged", "passing_90")) == "No change"


def test_missing_previous_or_current_is_na_and_not_zero() -> None:
    previous_missing = _delta("TEST_DEBUG_missing_historical_metric", "dash_10y")
    assert previous_missing.previous_raw is None
    assert format_change(previous_missing) == "N/A"
    assert previous_missing.status == DeltaStatus.NOT_AVAILABLE
    history = histories()["TEST_DEBUG_improvement_heavy"]
    current_metrics = dict(history[1].raw_metrics)
    current_metrics["dash_10y"] = None
    current = replace(history[1], raw_metrics=current_metrics,
                      availability={key: value is not None for key, value in current_metrics.items()})
    current_missing = prepare_progress_comparison([current, history[0]])
    assert current_missing is not None
    assert current_missing.deltas[0].current_raw is None
    assert current_missing.deltas[0].performance_delta is None
    assert format_change(current_missing.deltas[0]) == "N/A"


def test_undated_juggling_is_not_copied_and_dated_juggling_compares() -> None:
    missing = prepare_progress_comparison(histories()["TEST_DEBUG_missing_dated_juggling"])
    assert missing is not None
    juggling = [item for item in missing.deltas if item.metric.startswith("juggling_")]
    assert all(item.previous_raw is None and item.status == "N/A" for item in juggling)
    dated = prepare_progress_comparison(histories()["TEST_DEBUG_improvement_heavy"])
    assert dated is not None
    assert all(item.status == "IMPROVED" for item in dated.deltas if item.metric.startswith("juggling_"))


def test_progress_page_has_ten_rows_and_expected_dimensions(test_workspace: Path) -> None:
    comparison = prepare_progress_comparison(histories()["TEST_DEBUG_mixed"])
    assert comparison is not None
    result = render_progress_page(comparison, test_workspace / "page3.png",
                                  ROOT / "logos/Sogility_Logo.png")
    assert result.dimensions == (1920, 1080)
    assert len(result.metric_rows) == 10
    with Image.open(result.path) as image:
        assert image.size == (1920, 1080)


def test_existing_production_pdfs_remain_two_pages() -> None:
    pdfs = sorted((ROOT / "output/final/pdf").glob("*.pdf"))
    assert len(pdfs) == 225
    assert all(count_pdf_pages(path) == 2 for path in pdfs)


def test_fixture_pdf_is_exactly_three_pages(test_workspace: Path) -> None:
    pages = []
    for number in range(1, 4):
        path = test_workspace / f"page{number}.png"
        Image.new("RGB", (1920, 1080), (number, number, number)).save(path)
        pages.append(path)
    pdf = render_final_pdf(pages[0], pages[1], test_workspace / "fixture.pdf", pages[2])
    assert count_pdf_pages(pdf) == 3


def test_real_data_has_zero_page3_eligible_and_audit_fields() -> None:
    result = run_progress_audit(ROOT)
    assert result["page3_eligible"] == 0
    assert result["audit_path"].is_file()
    assert len(result["previews"]) == 6
    assert len(result["pdfs"]) == 2
    assert all(count_pdf_pages(path) == 3 for path in result["pdfs"])
