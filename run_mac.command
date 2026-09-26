#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1
echo "Starting Sogility GO Elite Athlete Assessment workflow..."
python3 -m src.main
status=$?
if [ "$status" -ne 0 ]; then
    printf "Workflow failed. Press Return to close."
    read -r _unused
fi
exit "$status"
