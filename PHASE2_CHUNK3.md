# Phase II, Chunk 3: Google email foundation and safe dry run

## Architecture

Future delivery uses the Gmail API with installed-application OAuth 2.0 and only the
`https://www.googleapis.com/auth/gmail.send` scope. Authentication is isolated in
`src/google_email_auth.py`; report generation, recipient planning, templates, and dry runs do
not authenticate. Live sending is intentionally absent from this chunk.

The client/admin will eventually download a Google Desktop app OAuth file to
`config/google_credentials.json`. The generated token is stored at
`config/google_token.json` and refreshed when possible. Both paths are ignored by Git. Normal
Google passwords, secrets, and tokens are never stored in source, logs, previews, or audits.

## Recipient grouping and templates

The roster `Parent Contact` field is authoritative. Report generation records it in the
manifest as `recipient_email`; hardware athlete email is not used for delivery. Addresses are
trimmed and compared case-insensitively. Every valid shared address produces one plan with all
applicable final PDFs, regardless of surname. Missing, malformed, or ambiguous recipients and
missing reports are blocked rather than silently redirected.

Non-developers can edit `config/email_template.json`. Supported placeholders are deliberately
limited to `{athlete_name}`, `{athlete_names}`, `{assessment_date}`, `{assessment_dates}`, and
`{report_count}`. Singular and plural bodies are configured separately. Sender display and
future OAuth paths are in `config/email_settings.json`; the authenticated Google account will
determine the actual From address, preventing silent spoofing.

## Dry-run workflow

After production reports exist, run `python -m src.email_dry_run_audit`. It reads the production
manifest rather than guessing filenames, verifies every attachment, groups recipients, renders
plain/HTML content, and writes CSV, Markdown, and per-group text previews under
`output/phase2/email/`. This code path cannot accept a Gmail service and performs zero sends.
