#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${1:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python3" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python3"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[error] python3 not found" >&2
    exit 2
  fi
fi

echo "[info] using python: $PYTHON_BIN"
"$PYTHON_BIN" launcher/scripts/build_runtime.py --python "$PYTHON_BIN"
"$PYTHON_BIN" launcher/scripts/sync_firmware.py

echo "[ok] release resources prepared under launcher/resources/."
