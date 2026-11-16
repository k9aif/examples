#!/usr/bin/env bash
# One-time setup for the zip-code weather example on Ubuntu 22.04 or 24.04, then start it.
# Installs only what the example needs from Ubuntu's archives (asks for sudo). It does not
# install Ollama for you: point OLLAMA_BASE_URL in ../.env at a server you run.
set -euo pipefail
cd "$(dirname "$0")/.."

# No interactive prompts (tzdata asks for a region on a fresh system); sudo drops the variable,
# so it is passed explicitly.
APT="sudo DEBIAN_FRONTEND=noninteractive apt-get"

. /etc/os-release
echo "Ubuntu ${VERSION_ID:-unknown}"

suitable() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }

# 1. Ubuntu's own python3 (missing only on minimal images).
if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing python3 from Ubuntu's archive..."
  $APT update -q && $APT install -y -q python3
fi

# 2. K9-AIF needs 3.11+: 24.04 ships 3.12 (fine); 22.04 ships 3.10, so add 3.11 from deadsnakes.
if command -v python3.11 >/dev/null 2>&1 && suitable python3.11; then
  PY=python3.11
elif suitable python3; then
  PY=python3
else
  echo "Ubuntu's python3 is $(python3 --version 2>&1 | cut -d' ' -f2); K9-AIF needs 3.11+. Installing python3.11 from the deadsnakes PPA..."
  $APT update -q
  $APT install -y -q software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  $APT update -q
  $APT install -y -q python3.11
  PY=python3.11
fi
VER=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python: $($PY --version)"

# 3. venv support for that Python.
if ! $PY -c 'import venv, ensurepip' 2>/dev/null; then
  echo "Installing python${VER}-venv..."
  $APT install -y -q "python${VER}-venv" || { $APT update -q && $APT install -y -q "python${VER}-venv"; }
fi

command -v curl >/dev/null 2>&1 || { $APT update -q && $APT install -y -q curl; }

if [ ! -f .env ]; then
  cp env-example .env
  echo "Created .env from env-example. Edit OLLAMA_BASE_URL if Ollama isn't on this machine."
fi
set -a; . ./.env; set +a

URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
if curl -fsS -m 5 "$URL/v1/models" >/dev/null; then
  echo "Ollama reachable at $URL"
  if ! curl -fsS -m 5 "$URL/api/tags" | grep -q "\"${WEATHER_MODEL:-qwen2.5:7b}\""; then
    echo "Model ${WEATHER_MODEL:-qwen2.5:7b} not found there. On the Ollama host: ollama pull ${WEATHER_MODEL:-qwen2.5:7b}"
  fi
else
  echo "Ollama not reachable at $URL."
  echo "Install it (https://ollama.com/download/linux), run 'ollama pull ${WEATHER_MODEL:-qwen2.5:7b}',"
  echo "or set OLLAMA_BASE_URL in .env to a server you already run. The page will show the model server as unreachable."
fi

PYTHON="$PY" exec ./run.sh "$@"
