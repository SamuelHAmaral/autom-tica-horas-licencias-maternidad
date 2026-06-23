#!/usr/bin/env bash
set -euo pipefail

# Daily maternity leave sync for Linux cron.
# Keeps execution rooted at project folder so .env is discovered correctly.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv interpreter: $VENV_PYTHON" >&2
  echo "Create it with: python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

"$VENV_PYTHON" main.py
