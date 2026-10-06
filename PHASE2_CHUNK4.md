# Phase II, Chunk 4: controlled Gmail delivery engine

## Sender and modes

`src/google_email_sender.py` builds RFC/MIME messages and invokes Gmail API
`users.messages.send` through the authenticated client from `src/google_email_auth.py`. It does
not set a `From` header: the authenticated Google Workspace account is the actual sender. It
supports plain text, optional simple HTML, and one or more unique, validated PDF attachments.

`src/email_send_cli.py` is separate from report generation and has three explicit modes:

- `--dry-run`: no OAuth and no sending.
- `--test-send`: requires a configured valid test recipient, redirects exactly one READY plan,
  prefixes its subject with `[TEST]`, adds a test notice, and logs the original intended
  recipient separately.
- `--live-send`: additionally requires `live_send_enabled: true` and the exact dynamic typed
  confirmation `SEND X EMAILS`. `--force-resend` is valid only with this mode and is logged.

Running report generation or the email CLI without a mode never sends email.

## Duplicate protection and recovery

The SHA-256 delivery fingerprint contains the normalized recipient plus sorted athlete names,
assessment dates, and SHA-256 content hashes of their PDFs. It excludes absolute paths,
generation timestamps, and template wording. A successful `SENT` fingerprint is skipped on a
later production run unless force-resend is explicit. `TEST_SENT` and `FAILED` do not mark a
production delivery complete.

Every attempt is appended and flushed immediately to
`output/phase2/email/delivery_log.csv`, with batch ID, UTC timestamp, recipients, report
identity, fingerprint, mode, status, Gmail message ID, sanitized error information, and
force-resend state. Thus, if a batch stops after 50 successful messages, the next run skips
those 50 and continues with the remainder.

## Validation and retries

Plans must be READY; recipients must remain valid; attachments must be unique, existing,
non-empty PDFs; and total attachment bytes must stay under the configurable conservative
limit. Oversized messages are blocked without compression. HTTP 429/500/502/503/504 errors use
bounded exponential backoff (three attempts by default); permanent failures are not retried.
Only a successful Gmail response produces `SENT`, and its message ID is recorded.

No Google authorization occurred and zero real emails—including production recipient
emails—were sent while developing or validating this chunk.
