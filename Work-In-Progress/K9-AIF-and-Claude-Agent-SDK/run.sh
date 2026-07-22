#!/usr/bin/env bash
# Pet Store Agentic -- launches the storefront.
#
# webui/ is a static homage right now -- no Router/Storefront API exists
# yet to wire it to (that's still ahead). This serves it as a real,
# browsable site rather than just a file you open from Finder, since
# relative image paths and a real origin matter even for a static page.
#
# For the backend/data-layer work instead, see tests.sh and demo.sh.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PETSTORE_WEBUI_PORT:-8500}"

if [ ! -d "$SCRIPT_DIR/webui" ]; then
  echo "[run.sh] ERROR: webui/ not found."
  exit 1
fi

echo "=================================================================="
echo " Pet Store Agentic -- storefront (static homage, not yet wired"
echo " to the backend -- see PLAN.md)"
echo "=================================================================="
echo " http://localhost:$PORT"
echo "=================================================================="

if command -v open >/dev/null 2>&1; then
  ( sleep 1 && open "http://localhost:$PORT" ) &
fi

cd "$SCRIPT_DIR/webui"
python3 -m http.server "$PORT"
