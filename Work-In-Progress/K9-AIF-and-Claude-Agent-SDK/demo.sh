#!/usr/bin/env bash
# Pet Store Agentic -- the deterministic order walkthrough. Cart through
# delivery, zero LLM calls, run against the live Postgres database
# configured in .env.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY="$SCRIPT_DIR/.venv/bin/python3.11"

if [ ! -x "$VENV_PY" ]; then
  echo "[demo.sh] ERROR: venv not found at $VENV_PY -- see tests.sh for setup steps."
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "[demo.sh] ERROR: .env not found. Copy an existing K9-AIF .env (POSTGRES_*, K9_ENV, etc.) here first."
  exit 1
fi

set -a
source "$SCRIPT_DIR/.env"
set +a

"$VENV_PY" demo/walk_deterministic_order.py
