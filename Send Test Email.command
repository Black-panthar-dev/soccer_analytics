#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
cd "$SCRIPT_DIR" || exit 1

printf '%s\n' \
  '--------------------------------------------------' \
  'SOGILITY GO - SEND ONE TEST EMAIL' \
  '--------------------------------------------------' '' \
  'This sends ONE test athlete report only to the configured test address.' \
  'No production parent emails will be contacted.' ''

PYTHON_BIN=''
if [[ -x "$SCRIPT_DIR/output/.venv/bin/python3" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/output/.venv/bin/python3"
elif [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ ! -f "$SCRIPT_DIR/config/google_token.json" ]]; then
  printf '%s\n' 'Google email authorization is missing.' \
    'First double-click Authorize Google Email.command.' '' \
    'Press Return to close.'
  read -r _unused
  exit 1
fi

if [[ -z "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -c \
  'import pandas, matplotlib, PIL, google.auth, google_auth_oauthlib, googleapiclient' \
  >/dev/null 2>&1; then
  printf '%s\n' 'The test email cannot start because Python or required' \
    'application components are missing. Please contact the developer.' '' \
    'Dependencies must be installed by the developer; this launcher will' \
    'not install software or change your computer settings.' '' \
    'Press Return to close.'
  read -r _unused
  exit 1
fi

if ! "$PYTHON_BIN" -c \
  'import json,sys; from pathlib import Path; from src.email_planner import is_valid_email; s=json.loads(Path("config/email_settings.json").read_text(encoding="utf-8")); sys.exit(0 if is_valid_email(str(s.get("test_recipient") or "").strip()) else 1)' \
  >/dev/null 2>&1; then
  printf '%s\n' 'A valid test recipient is not configured.' \
    'The test launcher will not use a production recipient.' \
    'Please contact the developer.' '' 'Press Return to close.'
  read -r _unused
  exit 1
fi

printf 'Press Return to send one test email... '
read -r _unused
if "$PYTHON_BIN" -m src.email_send_cli --test-send --project-root "$SCRIPT_DIR"; then
  printf '\n%s\n' 'SUCCESS: One test email was sent to the configured test recipient.' \
    '' 'You may close this window.' '' 'Press Return to close.'
  read -r _unused
  exit 0
fi

printf '\n%s\n' 'TEST EMAIL NOT SENT' '' \
  'Please contact the developer if the problem continues.' '' \
  'Press Return to close.'
read -r _unused
exit 1
