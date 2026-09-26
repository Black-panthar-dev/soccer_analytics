from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image

from src.batch_processor import (
    count_pdf_pages,
    generate_batch_reports,
    render_final_pdf,
    safe_athlete_stem,
)
from src.client_overrides import apply_roster_overrides
from src.config_loader import load_config
from src.metric_extractor import METRIC_COLUMNS


ROOT = Path(__file__).resolve().parents[1]


def athlete(first: str, last: str, age_group: object = "U9") -> dict[str, object]:
    row: dict[str, object] = {
        "first_name": first, "last_name": last, "full_name": f"{first} {last}",
        "birthday": "2017-01-02", "team_name": "Test Team", "age_group": age_group,
        "assessment_date": "2026-08-15",
    }
    for index, metric in enumerate(METRIC_COLUMNS, 1):
        row[metric] = float(index)
        row[f"{metric}_percentile"] = float(index * 5)
        row[f"{metric}_age_group_average"] = float(index + 0.5)
        row[f"{metric}_age_group_average_percentile"] = 50.0
    return row


def test_single_athlete_pdf_is_two_ordered_full_size_pages(test_workspace: Path) -> None:
    page1 = test_workspace / "page1.png"
    page2 = test_workspace / "page2.png"
    Image.new("RGBA", (1920, 1080), "green").save(page1)
    Image.new("RGBA", (1920, 1080), "cyan").save(page2)
    pdf = render_final_pdf(page1, page2, test_workspace / "report.pdf")
    assert pdf.is_file() and pdf.stat().st_size > 0
    assert count_pdf_pages(pdf) == 2


def test_filename_sanitization_is_stable() -> None:
    assert safe_athlete_stem("Adelyn", "O'Boynick") == "O_Boynick_Adelyn"
    assert safe_athlete_stem("  Kya ", "Sachs") == "Sachs_Kya"
    assert safe_athlete_stem("aimie", "wanaswa") == "Wanaswa_Aimie"
    assert safe_athlete_stem("Joey", "McDonnell") == "McDonnell_Joey"
    assert safe_athlete_stem("José", "Muñoz") == "Munoz_Jose"


def test_batch_multiple_missing_and_skipped_outputs_and_manifests(test_workspace: Path) -> None:
    config = load_config(ROOT / "config/config.json")
    first = athlete("Kya", "Sachs")
    second = athlete("Test", "Partial")
    second["dash_20y"] = pd.NA
    second["dash_20y_percentile"] = pd.NA
    skipped = athlete("No", "Cohort", pd.NA)
    result = generate_batch_reports(pd.DataFrame([first, second, skipped]), config, ROOT,
                                    test_workspace / "final", run_timestamp="fixed")
    summary = result["summary"]
    manifest = result["manifest"]
    assert summary["total_eligible_athletes"] == 2
    assert summary["total_pdfs_generated"] == 2
    assert summary["total_with_missing_metrics"] == 1
    assert summary["total_skipped"] == 1
    assert set(manifest["generation_status"]) == {"success", "skipped"}
    success = manifest[manifest["generation_status"] == "success"]
    for column, folder in (("page1_png", "png\\page1"),
                           ("page2_png", "png\\page2"), ("pdf_path", "pdf")):
        assert success[column].map(lambda value: Path(value).is_file()).all()
        assert success[column].str.contains(folder, regex=False).all()
    for name in ("report_manifest.csv", "batch_summary.csv", "failed_reports.csv",
                 "generation_log.txt"):
        assert (test_workspace / "final" / name).is_file()
    failed = pd.read_csv(test_workspace / "final/failed_reports.csv")
    assert failed.loc[0, "athlete_name"] == "No Cohort"


def test_duplicate_failure_does_not_stop_batch(test_workspace: Path) -> None:
    config = load_config(ROOT / "config/config.json")
    rows = pd.DataFrame([athlete("Same", "Name"), athlete("Same", "Name"),
                         athlete("Still", "Works")])
    result = generate_batch_reports(rows, config, ROOT, test_workspace / "faults",
                                    run_timestamp="fixed")
    assert result["summary"]["total_pdfs_generated"] == 2
    assert result["summary"]["total_failures"] == 1
    assert len(result["failed"]) == 1


def test_repeated_batch_manifest_structure_is_deterministic(test_workspace: Path) -> None:
    config = load_config(ROOT / "config/config.json")
    rows = pd.DataFrame([athlete("Repeat", "Athlete")])
    first = generate_batch_reports(rows, config, ROOT, test_workspace / "run1",
                                   run_timestamp="fixed")["manifest"]
    second = generate_batch_reports(rows, config, ROOT, test_workspace / "run2",
                                    run_timestamp="fixed")["manifest"]
    assert list(first.columns) == list(second.columns)
    assert first[["athlete_name", "age_group", "generation_status", "notes"]].equals(
        second[["athlete_name", "age_group", "generation_status", "notes"]])


def test_kya_override_included_and_unmatched_excluded() -> None:
    config = load_config(ROOT / "config/config.json")
    roster = pd.DataFrame([{"First Name": "Kya", "Last Name": "Sachs",
                            "Age Group": pd.NA}])
    updated = apply_roster_overrides(roster, config)
    assert updated.loc[0, "Age Group"] == "U9"
    production = pd.read_csv(ROOT / "output/debug/percentile_metrics.csv")
    names = set(production["full_name"].str.casefold())
    assert "kya sachs" in names
    assert {"evan galaska", "amelia maebrown"}.isdisjoint(names)
    assert not any(name.startswith("kristoffer") for name in names)


def test_launch_scripts_exist_and_invoke_batch_entrypoint() -> None:
    for name in ("run_generate_reports.bat", "run_generate_reports.command"):
        path = ROOT / name
        assert path.is_file()
        assert "src.batch_processor" in path.read_text(encoding="utf-8")
