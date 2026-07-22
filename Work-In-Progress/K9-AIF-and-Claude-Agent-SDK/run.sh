#!/usr/bin/env bash
# Pet Store Agentic -- launches the storefront.
#
# Real now: category browsing, guest/logged-in checkout, registration,
# login, order history, and an admin portal (all orders + livestock
# gate approval) -- all against the live Postgres petstore schema via
# webui_server.py. Search and a persistent multi-item cart are still
# placeholders. See PLAN.md for exact status.
#
# For the backend/data-layer work instead, see tests.sh and demo.sh.
# To create an admin account: python demo/seed_admin.py <username> <password>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PETSTORE_WEBUI_PORT:-8500}"
VENV_PY="$SCRIPT_DIR/.venv/bin/python3.11"

if [ ! -d "$SCRIPT_DIR/webui" ]; then
  echo "[run.sh] ERROR: webui/ not found."
  exit 1
fi

if [ ! -x "$VENV_PY" ]; then
  echo "[run.sh] ERROR: venv not found at $VENV_PY -- see tests.sh for setup steps."
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
echo " Pet Store Agentic -- storefront"
echo " Real: catalog, checkout, accounts, order history, admin portal."
echo " Still placeholder: search, persistent cart. See PLAN.md."
echo "=================================================================="
echo " http://localhost:$PORT"
echo "=================================================================="

if command -v open >/dev/null 2>&1; then
  ( sleep 1 && open "http://localhost:$PORT" ) &
fi

PETSTORE_WEBUI_PORT="$PORT" "$VENV_PY" "$SCRIPT_DIR/webui/webui_server.py"
