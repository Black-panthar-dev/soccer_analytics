#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1
export PYTHONPATH=.
export MPLCONFIGDIR="$SCRIPT_DIR/output/matplotlib"
echo "Generating final athlete reports..."
python3 -m src.batch_processor
status=$?
if [ "$status" -eq 0 ]; then
  echo "Report generation completed successfully."
else
  echo "Report generation completed with failures. See output/final/generation_log.txt"
fi
exit "$status"
