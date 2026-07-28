#!/usr/bin/env bash
set -euo pipefail
# Activate your virtualenv. Override VENV to point at yours:
#   VENV=/path/to/venv ./run.sh
export BROWSER_HEADLESS="${BROWSER_HEADLESS:-0}"
source "${VENV:-.venv}/bin/activate"
exec python3 server.py "$@"
