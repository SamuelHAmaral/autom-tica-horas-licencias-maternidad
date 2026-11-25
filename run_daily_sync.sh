#!/usr/bin/env bash
# Título: sincronización diaria de licencias de maternidad para el cron de Linux.
# Nota: el cron tiene que ejecutar este archivo, no main.py. Entra a esta carpeta
# para encontrar el .env y después usa .venv. El código de salida es el de la tarea
# (0 correcto, 1 configuración, 2 SQL, 3 Nodum).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv interpreter: $VENV_PYTHON" >&2
  echo "Create it with: python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

"$VENV_PYTHON" main.py
