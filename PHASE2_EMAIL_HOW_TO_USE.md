# Sogility GO Email Delivery — How to Use

Email delivery is a separate operation from report generation. Generating reports never sends
email.

## Dry run

```powershell
python -m src.email_send_cli --dry-run
```

This is the safe review mode. It authenticates with nobody and sends nothing. Review the
recipient groups, athlete names, attachment paths, status, and issues under
`output/phase2/email/` before doing anything else.

Shared parent addresses are grouped into one message with multiple athlete reports.

## Test send

```powershell
python -m src.email_send_cli --test-send
```

First configure a developer-controlled `test_recipient` in `config/email_settings.json` and
complete the OAuth setup in `CLIENT_SETUP_GOOGLE_EMAIL.md`. This sends exactly one report to
the configured test address, adds `[TEST]` to the subject, and never falls back to a parent
address. The authenticated Gmail account is the sender. Credentials and tokens stay local;
the account's normal Google password is never stored.

## Live send

```powershell
python -m src.email_send_cli --live-send
```

Do not run `--live-send` until the complete dry-run recipient list has been reviewed and the
client has explicitly approved production delivery. Live mode must also be enabled in settings
and requires typing the exact confirmation phrase displayed by the program. Successfully sent
reports are protected against accidental duplicate delivery. Failed sends remain retryable;
force resend must be requested explicitly. Workspace administrator approval may be required.

Email wording is editable without Python changes in `config/email_template.json`: `subject`,
`single_report_body`, `multiple_report_body`, `single_report_html`, `multiple_report_html`, and
`closing`.
