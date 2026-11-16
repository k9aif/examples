#!/usr/bin/env bash
# Start the zip-code weather page locally: http://127.0.0.1:${PORT:-8003}
#
# First run creates ./.venv and installs the K9-AIF framework with the OpenAI Agents SDK extra:
#   - from a local checkout when K9_FRAMEWORK_DIR is set or ../../../k9-aif-framework exists;
#   - otherwise from PyPI (k9-aif 1.27.0 or later).
# Settings come from ./.env (copy env-example). Nothing is hosted; this runs on your machine.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
export K9_ENV="${K9_ENV:-development}"
PORT="${PORT:-8003}"
PYTHON="${PYTHON:-python3.11}"
FRAMEWORK="${K9_FRAMEWORK_DIR:-../../../k9-aif-framework}"

if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv (first run only)..."
  "$PYTHON" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  if [ -f "$FRAMEWORK/pyproject.toml" ]; then
    echo "Installing K9-AIF from $FRAMEWORK"
    .venv/bin/pip install -q -e "$FRAMEWORK[openai-agents,server]"
  else
    echo "Installing K9-AIF from PyPI"
    .venv/bin/pip install -q "k9-aif[openai-agents,server]>=1.27.0"
  fi
  .venv/bin/pip install -q -r requirements.txt
fi

if [ "${1:-}" = "--demo" ]; then
  exec .venv/bin/python -m weather_zip.run_weather --demo
fi

echo "Open http://127.0.0.1:${PORT}   (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn webui.app:app --host 127.0.0.1 --port "$PORT"
