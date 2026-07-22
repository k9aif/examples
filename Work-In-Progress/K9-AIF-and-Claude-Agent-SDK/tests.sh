#!/usr/bin/env bash
# Pet Store Agentic -- run the test suite. 30 tests, all mocking the
# external call (llm_invoke or claude-agent-sdk's query()) -- no live
# API cost, no credentials needed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY="$SCRIPT_DIR/.venv/bin/python3.11"

if [ ! -x "$VENV_PY" ]; then
  echo "[tests.sh] ERROR: venv not found at $VENV_PY"
  echo "  Run first:"
  echo "    python3.11 -m venv .venv"
  echo "    source .venv/bin/activate"
  echo "    pip install -e /Users/ravinatarajan/ai/k9-aif-framework"
  echo "    pip install -r requirements.txt"
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "[tests.sh] ERROR: .env not found. Copy an existing K9-AIF .env (POSTGRES_*, K9_ENV, etc.) here first."
  exit 1
fi

set -a
source "$SCRIPT_DIR/.env"
set +a

"$VENV_PY" -m pytest tests/ -v
