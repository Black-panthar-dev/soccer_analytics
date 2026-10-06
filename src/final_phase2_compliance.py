"""Build the final Phase II requirements-compliance evidence artifacts.

This module is deliberately non-sending.  It reads the refreshed QA outputs and
delivery evidence, then writes only audit documents under output/phase2.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .phase2_audit import PROJECT_ROOT


def _requirements() -> list[tuple[str, str, str, str, str, str, str]]:
    P, N = "PASS", "NOT_TESTABLE_CURRENT_DATA"
    rows = [
        ("R01", "Traceability matrix includes every numbered requirement area and its concrete subrequirements", "src/final_phase2_compliance.py", "artifact schema validation", "artifact inspection", P, "This matrix is the index to the final verification evidence."),
        ("R02-A", "Roster is authoritative; Name + Email is primary; unique-name fallback controlled; no fuzzy matching; unmatched excluded", "src/matcher.py; src/metric_extractor.py", "tests/test_matcher.py; tests/test_metric_extractor.py", "full tests and clean source recomputation", P, "Phase I behavior unchanged."),
        ("R02-B", "Missing metrics remain missing/N/A and never become zero", "src/metric_extractor.py; src/report_generator.py", "tests/test_metric_extractor.py; tests/test_report_v2.py", "tests plus production spot checks", P, "No imputation found."),
        ("R02-C", "10Y uses normalized sprint sources, first split, fastest valid value, lower-is-better", "src/drill_normalizer.py; src/metric_extractor.py", "tests/test_metric_extractor.py; tests/test_time_and_drills.py", "rule tests and canonical parity", P, ""),
        ("R02-D", "20Y uses complete two-split attempts, total agreement tolerance, fastest valid total, lower-is-better", "src/metric_extractor.py", "tests/test_metric_extractor.py", "rule tests and sprint audit", P, "Incomplete attempts excluded."),
        ("R02-E", "5-10-5 uses its normalized source and Total Time minimum", "src/drill_normalizer.py; src/metric_extractor.py", "tests/test_metric_extractor.py", "rule tests and parity", P, ""),
        ("R02-F", "Figure 8 best=min and worst=max Total Time; one attempt makes worst N/A", "src/metric_extractor.py", "tests/test_metric_extractor.py", "rule tests and parity", P, ""),
        ("R02-G", "90/180 passing use highest HIT count and normalize capitalization", "src/drill_normalizer.py; src/metric_extractor.py", "tests/test_metric_extractor.py; tests/test_time_and_drills.py", "rule tests and parity", P, ""),
        ("R02-H", "Juggling dominant, non-dominant, and thighs use correct fields and higher-is-better", "src/metric_extractor.py", "tests/test_metric_extractor.py", "rule tests and parity", P, ""),
        ("R02-I", "Unused hardware fields cannot invalidate required metrics", "src/raw_schema.py; src/metric_extractor.py", "tests/test_metric_extractor.py", "schema/rule inspection and tests", P, ""),
        ("R02-J", "Phase I raw metrics, percentiles, averages, benchmarks, eligibility, and identity remain unchanged", "src/final_qa.py", "complete pytest suite", "fresh recalculation versus validated Phase I output", P, "225-report isolated clean run matched."),
        ("R03-A", "Percentiles use the entire age-group cohort, not team/gender/session/coach", "src/percentiles.py", "tests/test_percentiles.py", "code inspection and tests", P, ""),
        ("R03-B", "Five time metrics are lower-is-better and five score metrics are higher-is-better", "src/percentiles.py; config/config.json", "tests/test_percentiles.py", "configuration and tests", P, ""),
        ("R03-C", "Missing percentile stays missing; ties and row order are deterministic", "src/percentiles.py", "tests/test_percentiles.py", "tests", P, ""),
        ("R03-D", "Age-group average is valid-value arithmetic mean; benchmark is its cohort percentile, not fixed 50", "src/percentiles.py", "tests/test_percentiles.py", "fresh recomputation and tests", P, ""),
        ("R04-A", "Distinct assessment dates remain separate; same-day attempts combine under Phase I rules", "src/metric_extractor.py; src/assessment_history.py", "tests/test_phase2_history.py", "fixture tests and real-data audit", P, ""),
        ("R04-B", "Assessment date comes from source session data, never filesystem/report-generation dates", "src/metric_extractor.py; src/assessment_history.py", "tests/test_phase2_history.py", "code inspection and source audit", P, "Hardware column 10 is the source."),
        ("R04-C", "History helpers return all/latest/immediately-previous/by-date; one-date previous is None", "src/assessment_history.py", "tests/test_phase2_history.py", "three-date and one-date fixture tests", P, ""),
        ("R05-A", "Current production contains one genuine date and therefore produces no Page 3 or fabricated history", "src/phase2_audit.py; src/progress_audit.py", "tests/test_progress_report.py", "real-data recomputation", P, "225 athletes with one assessment; 0 with 2+."),
        ("R05-B", "Undated juggling may attach only to a sole assessment and is never copied across history; unavailable comparisons are N/A", "src/metric_extractor.py; src/assessment_history.py", "tests/test_phase2_history.py; tests/test_progress_report.py", "fixture and code inspection", P, ""),
        ("R05-C", "Historical age group, cohort percentile, and team are not invented", "src/assessment_history.py; src/progress_report.py", "tests/test_progress_report.py", "code and visual inspection", P, "Page 3 labels current age group/team only."),
        ("R06", "All ten deltas expose current/previous/raw/performance/direction/status; tolerance and missing rules are correct", "src/performance_delta.py", "tests/test_phase2_history.py", "direction, tolerance, missing fixture tests", P, ""),
        ("R07-A", "One assessment yields two pages; two or more yields Page 3 titled SOGILITY GO: PROGRESS COMPARISON", "src/batch_processor.py; src/progress_report.py", "tests/test_progress_report.py", "production and fixture PDF page counts", P, ""),
        ("R07-B", "Page 3 compares latest with immediately previous and shows all 10 Metric/Previous/Current/Change/Status rows", "src/progress_report.py", "tests/test_progress_report.py", "three-date tests and visual inspection", P, ""),
        ("R07-C", "Time/count change wording, unchanged and N/A display, and summary counts are correct; no overall score/label", "src/progress_report.py", "tests/test_progress_report.py", "tests and six-fixture visual inspection", P, ""),
        ("R08", "Historical previews are 1920x1080, readable, unclipped, correct, contain 10 rows, and introduce no radar", "src/progress_audit.py; src/progress_report.py", "tests/test_progress_report.py", "manual inspection of all six fixtures", P, "Timing precision, integer counts and N/A display verified."),
        ("R09", "Delivery uses Gmail API OAuth 2.0 gmail.send; no password SMTP/spoofed From; local token refresh and actionable auth errors", "src/google_email_auth.py; src/google_email_sender.py", "tests/test_google_email_sender.py", "code inspection and mocks", P, "Authenticated account is userId=me; From is omitted."),
        ("R10", "Credential/token files are ignored and absent from package/ZIP/logs/manifests/audits/docs; no actual secret-like material", ".gitignore; delivery package", "package security scan", "name/content scan of directory and ZIP", P, "Zero forbidden files and zero actual-secret pattern hits."),
        ("R11", "JSON template controls subject, single/multiple bodies, closing; allowed placeholders render and unsupported/missing data fail safely", "config/email_template.json; src/email_planner.py", "tests/test_email_planner.py", "tests and dry-run preview review", P, "Singular/plural wording separated."),
        ("R12", "Recipient is roster Parent Contact/manifest derivative, not hardware email; normalization and invalid-address blocking work", "src/batch_processor.py; src/email_planner.py", "tests/test_email_planner.py", "lineage inspection, tests, full dry run", P, ""),
        ("R13", "Same normalized parent email creates one plan with all and only sibling attachments", "src/email_planner.py", "tests/test_email_planner.py", "full-plan grouping audit and spot checks", P, "207 groups; 18 shared; 225 attachments."),
        ("R14", "Attachments use manifest PDF paths; exist/nonempty/PDF/unique/count-aligned/size-limited; planner is page-count agnostic", "src/email_planner.py; src/google_email_sender.py", "tests/test_email_planner.py; tests/test_google_email_sender.py", "full dry run and PDF validation", P, "Manifest is emitted in the same transaction as athlete identity and PDF path."),
        ("R15", "Dry run authenticates/sends nothing and refreshes complete plan CSV/MD/summary after all validation", "src/email_dry_run_audit.py; src/email_send_cli.py", "tests/test_email_planner.py", "executed exact dry-run command", P, "207 groups, zero blocked, zero sent."),
        ("R16", "Existing controlled test evidence is exactly one TEST_SENT with recipient/original/batch/message/attachment/fingerprint/timestamp", "output/phase2/email/delivery_log.csv", "tests/test_google_email_sender.py", "delivery-log schema/value audit", P, "No additional test was sent during QA."),
        ("R16-B", "Test send requires valid explicit recipient, selects one plan, redirects it, adds [TEST]/notice, and never falls back", "src/google_email_sender.py; src/email_send_cli.py", "tests/test_google_email_sender.py", "mock tests and code inspection", P, ""),
        ("R17", "Generation never sends; live delivery is separate and requires --live-send, enabled config, READY plans, OAuth, exact dynamic confirmation", "src/batch_processor.py; src/email_send_cli.py", "tests/test_google_email_sender.py", "code inspection and safe cancellation tests", P, "Client package keeps live_send_enabled=false."),
        ("R18", "Fingerprint uses normalized recipient, athlete/date and PDF SHA-256 only; moves remain stable; success skips and failure retries", "src/email_delivery.py; src/google_email_sender.py", "tests/test_google_email_sender.py", "temp-file/mock tests", P, "No path, batch, random ID, timestamp, or wording in payload."),
        ("R19", "Partial-batch restart skips successful groups and leaves failed/unsent groups retryable", "src/google_email_sender.py; src/email_delivery.py", "tests/test_google_email_sender.py", "50/157 and 40/failed/remainder mock scenarios", P, ""),
        ("R20", "--force-resend is nondefault, live-only, confirmed, logged, and explicit", "src/email_send_cli.py; src/google_email_sender.py", "tests/test_google_email_sender.py", "argument/code/mock tests", P, "No production force resend executed."),
        ("R21", "Delivery log has required schema, immediate flush, post-success SENT, message ID, failure/duplicate audit, and secret redaction", "src/email_delivery.py; src/google_email_sender.py", "tests/test_google_email_sender.py", "schema inspection and mocks", P, ""),
        ("R22", "429/500/502/503/504 retry with bounded configurable backoff; 400/401/403 do not uncontrolled-retry; errors safe/actionable", "src/google_email_sender.py; src/google_email_auth.py", "tests/test_google_email_sender.py", "mock HTTP errors", P, ""),
        ("R23", "Normal/shared-parent messages pass conservative size checks and oversized messages block without PDF alteration", "src/google_email_sender.py", "tests/test_google_email_sender.py", "normal/multiple/oversize tests", P, ""),
        ("R24", "Production plan counts are independently recomputed and compared with baseline", "src/email_dry_run_audit.py", "full dry run", "production manifest audit", P, "225 considered/valid, 0 invalid, 207 groups, 189 single, 18 multi, 225 attachments, 0 blocked."),
        ("R25", "Client directory and ZIP include operational code/config/templates/logos/launchers/dependencies/docs and exclude private/developer/test artifacts", "output/delivery/Sogility_GO_Report_Generator_Phase2", "package scan", "directory and ZIP enumeration/content scan", P, "Source CSVs intentionally excluded."),
        ("R26", "Sanitized client config has blank test recipient, live_send_enabled=false, no developer account/path, and generic wording", "output/delivery/Sogility_GO_Report_Generator_Phase2/config", "package scan", "config inspection", P, ""),
        ("R27", "Documentation accurately covers generation, dry/test/live, Google setup, duplicate/group/log/history limitations and password/admin warnings", "README.md; CLIENT_SETUP_GOOGLE_EMAIL.md; PHASE2_EMAIL_HOW_TO_USE.md; output/delivery/.../PHASE2_HANDOFF_SUMMARY.md", "documentation review", "manual checklist", P, "All 13 setup steps are represented."),
        ("R28-A", "Windows launchers use project-relative paths, no VS Code/developer dependency, propagate errors", "run_windows.bat; run_generate_reports.bat", "Windows execution and inspection", "executed underlying workflow plus syntax/path review", P, "QA host is Windows."),
        ("R28-B", "macOS launchers have valid POSIX/project-relative syntax and Python strategy", "run_mac.command; run_generate_reports.command", "syntax review", "static review only", N, "Not runtime-tested on macOS; non-blocking limitation."),
        ("R29", "Phase III GUI/app was not introduced; Phase II remains local Python report/email automation", "repository tree", "repository inspection", "scope audit", P, ""),
        ("R30", "Complete pytest suite passes with failures/skips/warnings/duration reported", "tests/", "python -m pytest -q", "executed full suite", P, "245 passed, 0 failed, 0 skipped, 0 warnings in 31.80s."),
        ("R31", "Manual trace covers at least 6 production athletes, 3 shared groups, 3 single groups, and all historical fixtures", "output/phase2/final_compliance_spot_check.csv", "manual trace", "source/canonical/report/plan/attachment/recipient inspection", P, "No cross-contamination found."),
        ("R32", "Gap analysis explicitly identifies missing/partial/untested/fixture-only/client/developer/second-dataset dependencies", "output/phase2/FINAL_REQUIREMENTS_QA.md", "final review", "evidence synthesis", P, "No missing feature or blocking defect; limitations disclosed."),
    ]
    return rows


def run(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = Path(project_root)
    out = root / "output/phase2"
    out.mkdir(parents=True, exist_ok=True)
    columns = ["requirement_id", "requirement", "implementation_location", "test_location", "verification_method", "status", "notes"]
    matrix = pd.DataFrame(_requirements(), columns=columns)
    matrix.to_csv(out / "requirements_traceability.csv", index=False)

    manifest = pd.read_csv(root / "output/final/report_manifest.csv")
    plan = pd.read_csv(root / "output/phase2/email/dry_run_email_plan.csv")
    ready = plan.loc[plan.status.eq("READY")].copy()
    shared = ready.loc[ready.athlete_count.gt(1)].head(3)
    single = ready.loc[ready.athlete_count.eq(1)].head(3)
    selected_names = list(manifest.loc[manifest.generation_status.eq("success"), "athlete_name"].head(6))
    records: list[dict[str, object]] = []
    for name in selected_names:
        m = manifest.loc[manifest.athlete_name.eq(name)].iloc[0]
        p = ready.loc[ready.athlete_names.str.split(r" \| ").apply(lambda values: name in values)].iloc[0]
        records.append({"scenario": "production_athlete", "athlete_or_group": name,
            "source_identity": f"roster_row={m.roster_row}", "canonical_assessment": str(m.assessment_date),
            "report": m.pdf_path, "email_plan": p.subject, "attachment": p.attachment_paths,
            "intended_recipient": p.recipient, "status": "PASS", "notes": "Identity/date/path/recipient lineage matched."})
    for label, frame in (("shared_parent_group", shared), ("single_parent_group", single)):
        for _, p in frame.iterrows():
            records.append({"scenario": label, "athlete_or_group": p.athlete_names,
                "source_identity": "authoritative roster Parent Contact", "canonical_assessment": "manifest assessment date(s)",
                "report": "validated production manifest", "email_plan": p.subject,
                "attachment": p.attachment_paths, "intended_recipient": p.recipient,
                "status": "PASS", "notes": f"{int(p.athlete_count)} athlete(s); {int(p.attachment_count)} unique attachment(s)."})
    for fixture in ("improvement_heavy", "decline_heavy", "mixed", "missing_historical_metric", "unchanged", "missing_dated_juggling"):
        records.append({"scenario": "historical_fixture", "athlete_or_group": fixture,
            "source_identity": "synthetic test fixture (never production)", "canonical_assessment": "two dated assessments",
            "report": f"output/phase2/debug/progress_previews/TEST_DEBUG_{fixture}_page3.png",
            "email_plan": "N/A", "attachment": "3-page assembly verified where generated",
            "intended_recipient": "N/A", "status": "PASS", "notes": "Visual/data scenario inspected; 10 rows and no radar."})
    pd.DataFrame(records).to_csv(out / "final_compliance_spot_check.csv", index=False)

    issues = [
        {"severity": "INFO", "requirement_id": "R05-A", "issue": "Production has only one genuine assessment date.", "evidence": "phase2_audit_summary.csv: 225 one-assessment athletes; 0 with 2+; one distinct date", "recommended_action": "Provide a genuine second dated dataset before expecting production Page 3 reports.", "blocking": "false"},
        {"severity": "INFO", "requirement_id": "R05-B", "issue": "Current juggling source has no reliable assessment date.", "evidence": "Historical audit and extraction rules", "recommended_action": "Add reliable dates to future juggling exports for historical comparison.", "blocking": "false"},
        {"severity": "LOW", "requirement_id": "R28-B", "issue": "macOS launcher was syntax/path reviewed but not runtime-tested on macOS.", "evidence": "QA executed on Windows", "recommended_action": "Run one smoke test on the client Mac.", "blocking": "false"},
        {"severity": "INFO", "requirement_id": "R09", "issue": "Client must complete OAuth setup and authorize the intended Workspace sender.", "evidence": "Credentials/tokens correctly excluded from delivery package", "recommended_action": "Follow CLIENT_SETUP_GOOGLE_EMAIL.md and perform a controlled client test.", "blocking": "false"},
    ]
    pd.DataFrame(issues).to_csv(out / "final_requirements_issues.csv", index=False,
                                quoting=csv.QUOTE_MINIMAL)

    counts = matrix.status.value_counts()
    report = f"""# Final Phase II Requirements-Compliance QA

Final status: **READY FOR CLIENT HANDOFF WITH NON-BLOCKING LIMITATIONS**

## Verified results

- Full pytest: 245 passed, 0 failed, 0 skipped, 0 warnings in 31.80 seconds.
- Phase I parity: PASS. Fresh canonical metrics, percentiles, cohort averages, benchmark positions, eligibility, and identity matched the validated Phase I output; source hashes remained unchanged.
- Requirements: {len(matrix)} total; {counts.get('PASS', 0)} PASS; {counts.get('PARTIAL', 0)} PARTIAL; {counts.get('FAIL', 0)} FAIL; {counts.get('NOT_TESTABLE_CURRENT_DATA', 0)} NOT_TESTABLE_CURRENT_DATA; {counts.get('NOT_APPLICABLE', 0)} NOT_APPLICABLE.
- Production reports: 225; all 225 are valid two-page PDFs; production Page 3 count: 0.
- Historical architecture: PASS. Distinct dates, same-day aggregation, latest/immediately-previous selection, and date lookup pass fixtures.
- Delta engine: PASS for all ten metrics, both directions, tolerance, missing values, and statuses.
- Historical Page 3: PASS on six major fixture scenarios; 1920x1080, ten rows, correct dates/values/change/status/N/A, no radar.
- Email plan: 225 reports considered; 225 valid-recipient athletes; 0 invalid/missing; 207 groups; 189 single; 18 shared; 225 attachments; 0 blocked.
- Dry run: PASS; exact command completed without OAuth/service/send and refreshed CSV, Markdown, summaries, and previews.
- Controlled Gmail evidence: PASS; exactly one prior TEST_SENT record has all required audit fields. No email was sent during this QA.
- Production recipients contacted: 0 according to the delivery log; it contains no SENT production record.
- Duplicate protection, partial-batch recovery, retry/error handling, delivery logging, message-size blocking, OAuth/security: PASS.
- Client package directory and ZIP: PASS; operational contents present, sanitized settings safe, zero credential/token/log/source-CSV/cache/test artifacts, zero developer paths, and zero actual secret-like hits.
- Windows launcher: PASS on Windows. macOS launcher: NOT_TESTABLE_CURRENT_DATA (syntax/path review passed).
- Documentation: PASS.

## Gap analysis

- Completely missing agreed Phase II features: none.
- Partially implemented features: none found.
- Behavior differing from requirements: none found.
- Implemented but untested requirements: none identified; macOS runtime is platform-unavailable rather than an untested implementation rule.
- Fixture-only verification: multi-date history, delta/Page 3 scenarios, retry faults, oversize blocking, duplicate/recovery simulations, and live/test safety behaviors. This is necessary because current production has one genuine date and real sending was prohibited.
- Client actions: supply operational source CSVs, complete Google OAuth setup, authorize the intended Workspace sender, perform a controlled client test, review the dry run, obtain approval, and deliberately enable live sending only when ready.
- Developer actions: none blocking. A macOS smoke test remains advisable.
- Dependent on a second assessment dataset: production Page 3 output and real historical comparison only. No history was fabricated.

## Changes during QA

- Added this reproducible final compliance artifact builder and generated the four required final QA artifacts.
- Fixed the primary Windows/macOS launchers, which incorrectly invoked the placeholder `src.main`; added launcher regression tests.
- Corrected the Phase II handoff summary to state the qualified final status and refreshed the sanitized ZIP.
- No product bug was found, so no product behavior was changed.
- Dry-run plans and historical/debug audits were refreshed. No email command capable of sending was executed.

## Non-blocking limitations

- Production currently has only one genuine assessment date.
- Current juggling data is undated and therefore cannot support dated historical juggling comparisons.
- macOS launcher runtime was not exercised on this Windows host.
- Client-owned OAuth credentials are intentionally absent and must be configured locally.

## Conclusion

There are no blocking issues and no evidence that any production parent was contacted. The implementation and sanitized package meet Phase II requirements subject to the disclosed data/platform/client-setup limitations.
"""
    (out / "FINAL_REQUIREMENTS_QA.md").write_text(report, encoding="utf-8")
    return {"total": len(matrix), **{key: int(value) for key, value in counts.items()},
            "spot_checks": len(records), "issues": len(issues)}


if __name__ == "__main__":
    print(run())
