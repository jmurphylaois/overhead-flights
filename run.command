#!/bin/bash
# Mac/Linux launcher: double-click (Mac) or run ./run.command [--lan]
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r overhead_flights/app/requirements.txt; }
export OF_DATA_DIR="$PWD"
exec .venv/bin/python overhead_flights/app/app.py "$@"
