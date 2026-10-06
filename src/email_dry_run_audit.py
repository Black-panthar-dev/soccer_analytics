"""Run production-manifest email planning in guaranteed non-sending mode."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .email_planner import (
    EmailPlanStatus, dry_run_email_planning, is_valid_email, load_email_template,
    normalize_recipient,
)
from .phase2_audit import PROJECT_ROOT


def run_email_dry_run(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = Path(project_root)
    manifest_path = root / "output/final/report_manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError("Production report manifest is missing. Generate reports before email planning.")
    manifest = pd.read_csv(manifest_path)
    required = {"roster_row", "athlete_name", "recipient_email", "assessment_date",
                "pdf_path", "generation_status"}
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"Production report manifest lacks required email-planning fields: {sorted(missing)}")
    template = load_email_template(root / "config/email_template.json")
    output = root / "output/phase2/email"
    plans, paths = dry_run_email_planning(manifest, template, output)
    successful = manifest.loc[manifest["generation_status"].eq("success")]
    valid_flags = [is_valid_email(normalize_recipient(value)[0]) for value in successful["recipient_email"]]
    ready = [plan for plan in plans if plan.status == EmailPlanStatus.READY]
    summary = {
        "total_generated_athlete_reports_considered": len(successful),
        "athletes_with_valid_recipient_email": sum(valid_flags),
        "athletes_with_missing_or_invalid_recipient_email": len(valid_flags) - sum(valid_flags),
        "unique_recipient_groups": len(ready),
        "single_athlete_groups": sum(len(plan.athlete_names) == 1 for plan in ready),
        "multi_athlete_groups": sum(len(plan.athlete_names) >= 2 for plan in ready),
        "total_planned_attachments": sum(len(plan.attachment_paths) for plan in ready),
        "blocked_email_groups": sum(plan.status != EmailPlanStatus.READY for plan in plans),
        "emails_sent": 0,
    }
    summary_path = output / "dry_run_summary.csv"
    pd.DataFrame([summary]).to_csv(summary_path, index=False)
    return {"summary": summary, "plans": plans, **paths, "summary_path": summary_path}


def main() -> int:
    result = run_email_dry_run()
    print(pd.Series(result["summary"]).to_string())
    print("DRY RUN ONLY: zero emails sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
