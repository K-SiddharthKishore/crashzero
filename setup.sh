#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_model.py
.venv/bin/python scripts/fetch_data.py
.venv/bin/python scripts/fetch_demo.py
echo 'Ready. Start with ./run.sh'
