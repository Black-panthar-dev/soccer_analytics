#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
cd "$SCRIPT_DIR" || exit 1

printf '%s\n' \
  '--------------------------------------------------' \
  'SOGILITY GO - GOOGLE EMAIL AUTHORIZATION' \
  '--------------------------------------------------' '' \
  'Google will open in your browser.' '' \
  'Please sign in using:' '' \
  '  your approved Google Workspace account' '' \
  "Your Google password is entered only on Google's website." \
  'The application does not see or store your password.' ''

PYTHON_BIN=''
if [[ -x "$SCRIPT_DIR/output/.venv/bin/python3" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/output/.venv/bin/python3"
elif [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ ! -f "$SCRIPT_DIR/config/google_credentials.json" ]]; then
  printf '%s\n' 'Google email setup could not start because the required' \
    'application files are missing. Please contact the developer.' '' \
    'Press Return to close.'
  read -r _unused
  exit 1
fi

if [[ -z "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -c \
  'import pandas, matplotlib, PIL, google.auth, google_auth_oauthlib, googleapiclient' \
  >/dev/null 2>&1; then
  printf '%s\n' 'Google email setup could not start because Python or required' \
    'application components are missing. Please contact the developer.' '' \
    'Dependencies must be installed by the developer; this launcher will' \
    'not install software or change your computer settings.' '' \
    'Press Return to close.'
  read -r _unused
  exit 1
fi

printf 'Press Return to continue and open Google... '
read -r _unused
if "$PYTHON_BIN" -m src.email_send_cli --authorize --project-root "$SCRIPT_DIR"; then
  printf '\n%s\n' \
    'Google email authorization completed successfully.' '' \
    'You may close this window.' '' 'Press Return to close.'
  read -r _unused
  exit 0
fi

printf '\n%s\n' 'AUTHORIZATION NOT COMPLETED' '' \
  'Please contact the developer if the problem continues.' '' \
  'Press Return to close.'
read -r _unused
exit 1
