"""Explicit command interface for dry-run, controlled test, or confirmed live email."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .email_delivery import DeliveryLog, delivery_fingerprint
from .email_dry_run_audit import run_email_dry_run
from .email_planner import EmailPlanStatus, build_email_plans, is_valid_email, load_email_template
from .google_email_auth import GoogleEmailAuthError, get_gmail_service
from .google_email_sender import send_live_batch, send_one_test_message, validate_sendable_plan
from .phase2_audit import PROJECT_ROOT


def _load_settings(root: Path) -> dict[str, object]:
    path = root / "config/email_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Email settings are missing or malformed: {path}") from exc
    return data


def _load_plans(root: Path):
    manifest = pd.read_csv(root / "output/final/report_manifest.csv")
    template = load_email_template(root / "config/email_template.json")
    return build_email_plans(manifest, template)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--authorize", action="store_true",
                       help="Authorize Gmail and save a token; never send email")
    modes.add_argument("--dry-run", action="store_true", help="Plan and preview; never authenticate or send")
    modes.add_argument("--test-send", action="store_true", help="Send exactly one redirected test message")
    modes.add_argument("--live-send", action="store_true", help="Send confirmed production recipient groups")
    parser.add_argument("--force-resend", action="store_true",
                        help="Explicitly override duplicates; valid only with --live-send")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    return parser


def main(argv: list[str] | None = None, *, input_func=input) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path(args.project_root)
    if args.force_resend and not args.live_send:
        parser.error("--force-resend requires --live-send")
    if not any((args.authorize, args.dry_run, args.test_send, args.live_send)):
        parser.print_help()
        print("\nNo mode selected. Nothing authenticated or sent.")
        return 0
    if args.dry_run:
        result = run_email_dry_run(root)
        print(pd.Series(result["summary"]).to_string())
        print("DRY RUN ONLY: zero emails sent")
        return 0

    try:
        settings = _load_settings(root)
    except ValueError as exc:
        print(f"SETUP ERROR: {exc}")
        return 2

    credentials_path = root / str(settings.get(
        "google_credentials_path", "config/google_credentials.json"))
    token_path = root / str(settings.get("google_token_path", "config/google_token.json"))

    if args.test_send:
        test_recipient = str(settings.get("test_recipient") or "").strip()
        if not is_valid_email(test_recipient):
            print("BLOCKED: configure a valid test_recipient in config/email_settings.json")
            return 2

    if args.authorize:
        try:
            get_gmail_service(credentials_path, token_path)
        except GoogleEmailAuthError as exc:
            print(f"AUTHORIZATION NOT COMPLETED\n\n{exc}")
            return 2
        if not token_path.is_file() or token_path.stat().st_size == 0:
            print("AUTHORIZATION NOT COMPLETED\n\nGoogle did not create a usable authorization file.")
            return 2
        print("Google email authorization completed successfully.")
        print("No email was sent.")
        return 0

    plans = _load_plans(root)
    maximum = int(settings.get("max_total_attachment_bytes", 20_000_000))
    attempts = int(settings.get("max_transient_attempts", 3))
    log = DeliveryLog(root / "output/phase2/email/delivery_log.csv")

    if args.test_send:
        try:
            service = get_gmail_service(credentials_path, token_path)
        except GoogleEmailAuthError as exc:
            print(f"GOOGLE EMAIL SETUP ERROR: {exc}")
            return 2
        result = send_one_test_message(service, plans, test_recipient, log,
                                       max_total_attachment_bytes=maximum, max_attempts=attempts)
        print(f"Test-send result: {result['status']} message_id={result['gmail_message_id']}")
        return 0 if result["status"] == "TEST_SENT" else 1

    if not bool(settings.get("live_send_enabled", False)):
        print("BLOCKED: live_send_enabled is false in config/email_settings.json")
        return 2
    successful = log.successful_fingerprints()
    failed = log.failed_fingerprints()
    ready, blocked, duplicate = [], 0, 0
    for plan in plans:
        valid, _ = validate_sendable_plan(plan, maximum)
        if not valid:
            blocked += 1
        elif delivery_fingerprint(plan) in successful and not args.force_resend:
            duplicate += 1
        else:
            ready.append(plan)
    print(f"Email groups ready: {len(ready)}")
    print(f"Attachments: {sum(len(plan.attachment_paths) for plan in ready)}")
    print(f"Already delivered/skipped: {duplicate}")
    print(f"Blocked: {blocked}")
    print(f"Failed from prior attempt eligible for retry: "
          f"{sum(delivery_fingerprint(plan) in failed for plan in ready)}")
    expected = f"SEND {len(ready)} EMAILS"
    if not ready:
        print("Nothing eligible to send.")
        return 0
    confirmation = input_func(f"Type exactly '{expected}' to continue: ")
    if confirmation != expected:
        print("CANCELLED: confirmation did not match. Zero emails sent.")
        return 2
    try:
        service = get_gmail_service(credentials_path, token_path)
    except GoogleEmailAuthError as exc:
        print(f"GOOGLE EMAIL SETUP ERROR: {exc}")
        return 2
    results = send_live_batch(service, plans, log, max_total_attachment_bytes=maximum,
                              max_attempts=attempts, force_resend=args.force_resend)
    counts = pd.Series([result["status"] for result in results]).value_counts()
    print(counts.to_string())
    return 1 if any(result["status"] == "FAILED" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
