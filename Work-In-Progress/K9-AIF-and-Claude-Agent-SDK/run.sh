#!/usr/bin/env bash
# Pet Store Agentic -- run tests, then the deterministic-core demo.
#
# There's no persistent server yet (that's the Router/Storefront API
# phase, still ahead) -- this runs what actually exists: the test suite,
# then demo/walk_deterministic_order.py against the live Postgres database
# configured in .env.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY="$SCRIPT_DIR/.venv/bin/python3.11"

if [ ! -x "$VENV_PY" ]; then
  echo "[run.sh] ERROR: venv not found at $VENV_PY"
  echo "  Run first:"
  echo "    python3.11 -m venv .venv"
  echo "    source .venv/bin/activate"
  echo "    pip install -e /Users/ravinatarajan/ai/k9-aif-framework"
  echo "    pip install -r requirements.txt"
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "[run.sh] ERROR: .env not found. Copy an existing K9-AIF .env (POSTGRES_*, K9_ENV, etc.) here first."
  exit 1
fi

set -a
source "$SCRIPT_DIR/.env"
set +a

echo "=================================================================="
echo " Pet Store Agentic -- test suite"
echo "=================================================================="
"$VENV_PY" -m pytest tests/ -v

echo
echo "=================================================================="
echo " Pet Store Agentic -- deterministic order walkthrough"
echo "=================================================================="
"$VENV_PY" demo/walk_deterministic_order.py
