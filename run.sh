#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Environment missing. Run ./setup.sh first.' >&2
  exit 1
fi
mkdir -p .cache/ultralytics .cache/matplotlib
export YOLO_CONFIG_DIR="$PWD/.cache/ultralytics"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
export PYTORCH_ENABLE_MPS_FALLBACK=1
exec .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port "${PORT:-8501}" --server.headless true "$@"
