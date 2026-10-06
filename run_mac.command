#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1
echo "Generating Sogility GO athlete reports..."
python3 -m src.batch_processor
status=$?
if [ "$status" -ne 0 ]; then
    printf "Workflow failed. Press Return to close."
    read -r _unused
fi
exit "$status"
