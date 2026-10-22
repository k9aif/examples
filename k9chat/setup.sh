#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# K9Chat: install and run locally, without a container.
#
#   k9chat/setup.sh          create k9chat/.venv and install everything
#   k9chat/setup.sh seed     load the knowledge base (needs Ollama reachable)
#   k9chat/setup.sh run      start K9Chat on http://localhost:${PORT:-7777}
#
# The framework comes from PyPI (k9-aif, pinned below). If a k9-aif-framework
# checkout sits next to this repo (or K9AIF_FRAMEWORK_PATH points at one),
# K9Chat imports that source instead, same as the container build.
#
# Python 3.11 (what the container uses). Set PYTHON=/path/to/python3.x to
# choose another 3.11+ interpreter.

set -euo pipefail

K9AIF_VERSION="1.18.7"
TORCH_VERSION="2.14.0"          # CPU build: only the FAQ reranker uses it

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../k9-aif-examples/k9chat
ROOT="$(dirname "$HERE")"                               # .../k9-aif-examples
VENV="$HERE/.venv"
PORT="${PORT:-7777}"

pick_python() {
  if [[ -n "${PYTHON:-}" ]]; then echo "$PYTHON"; return; fi
  for p in python3.11 python3.12 python3; do
    if command -v "$p" >/dev/null 2>&1; then echo "$p"; return; fi
  done
  echo "No python3 found. Install Python 3.11 and re-run." >&2; exit 1
}

install() {
  local py; py="$(pick_python)"
  "$py" - <<'EOF' || { echo "Python 3.11 or newer is required (found $("$py" --version 2>&1))." >&2; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)
EOF
  echo "==> Creating $VENV with $("$py" --version)"
  "$py" -m venv "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  python -m pip install --quiet --upgrade pip

  echo "==> Installing PyTorch $TORCH_VERSION (CPU)"
  if [[ "$(uname -s)" == "Linux" ]]; then
    # PyPI's default Linux wheel bundles CUDA (several GB); K9Chat doesn't need it.
    pip install --quiet "torch==$TORCH_VERSION" --index-url https://download.pytorch.org/whl/cpu
  else
    pip install --quiet "torch==$TORCH_VERSION"
  fi

  echo "==> Installing K9Chat's pinned requirements"
  pip install --quiet -r "$HERE/requirements.txt"

  echo "==> Installing the K9-AIF framework (k9-aif==$K9AIF_VERSION from PyPI)"
  # --no-deps: requirements.txt above already pins every package the
  # framework needs for K9Chat; letting pip re-resolve would move pins.
  pip install --quiet --no-deps "k9-aif==$K9AIF_VERSION"

  if [[ ! -f "$HERE/.env" ]]; then
    cp "$HERE/.env.example" "$HERE/.env"
    echo "==> Created k9chat/.env from .env.example"
  fi

  cat <<EOF

Installed. Next:
  1. Edit k9chat/.env: set OLLAMA_BASE_URL to your Ollama server and the
     model names to models you have pulled (or point it at any
     OpenAI-compatible server).
  2. k9chat/setup.sh seed     # load the knowledge base
  3. k9chat/setup.sh run      # http://localhost:$PORT
EOF
}

need_venv() {
  if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Not installed yet: run k9chat/setup.sh first." >&2; exit 1
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
}

case "${1:-install}" in
  install) install ;;
  seed)
    need_venv
    cd "$ROOT" && python k9chat/seed_knowledge_base.py ;;
  run)
    need_venv
    cd "$ROOT" && exec python -m uvicorn k9chat.app:app --host "${HOST:-127.0.0.1}" --port "$PORT" ;;
  *)
    echo "usage: k9chat/setup.sh [install|seed|run]" >&2; exit 2 ;;
esac
