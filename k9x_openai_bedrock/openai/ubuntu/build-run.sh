#!/usr/bin/env bash
# Zip-code weather (K9-AIF + OpenAI Agents SDK): build and run helper, single container.
# Same structure as k9chat/ubuntu/build-run.sh (build/start/stop/logs/all).
#
# Build context is ai/ (parent of k9-aif-framework/ and k9-aif-examples/). The framework checkout
# must have the OpenAI Agents SDK adapter (framework main, or 1.27.0 and later).
#
# Requires openai/.env on this host (copy env-example; set OLLAMA_BASE_URL). Not baked into the image.
#
# The container listens on 127.0.0.1:${HOST_PORT} only: a reverse proxy or tunnel on this host
# (for example Cloudflare Tunnel -> localhost:8121) publishes it.
#
# Commands:
#   build   build the image
#   start   start the container (port 8121, override with HOST_PORT)
#   stop    stop the container
#   logs    tail logs
#   all     build + start

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"                 # .../<project>/openai
EXAMPLES_ROOT="$(git -C "$APP_DIR" rev-parse --show-toplevel 2>/dev/null || (cd "$APP_DIR/../.." && pwd))"
AI_DIR="$(cd "$EXAMPLES_ROOT/.." && pwd)"               # parent of both repos

[[ -d "$AI_DIR/k9-aif-framework/k9_aif_abb/k9_adapters/openai_agents" ]] || {
  echo "Error: $AI_DIR/k9-aif-framework has no k9_aif_abb/k9_adapters/openai_agents."
  echo "  Clone k9-aif-framework next to this repo, or update it: git -C $AI_DIR/k9-aif-framework pull"
  exit 1
}
EXAMPLE_REL="$(basename "$EXAMPLES_ROOT")/${APP_DIR#"$EXAMPLES_ROOT"/}"

IMAGE="k9x-openai-weather:latest"
CONTAINER="k9x-openai-weather"
HOST_PORT="${HOST_PORT:-8121}"

cmd="${1:-help}"
case "$cmd" in

  build)
    EX_VER="$(git -C "$EXAMPLES_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    FW_VER="$(git -C "$AI_DIR/k9-aif-framework" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    VERSION="examples ${EX_VER} / k9-aif ${FW_VER}"
    echo "Building $IMAGE (context: $AI_DIR, example: $EXAMPLE_REL, $VERSION) ..."
    cd "$AI_DIR"
    sudo podman build -t "$IMAGE" \
      --build-arg "K9AIF_DIR=k9-aif-framework" \
      --build-arg "EXAMPLE_DIR=$EXAMPLE_REL" \
      --build-arg "APP_VERSION=$VERSION" \
      -f "$EXAMPLE_REL/ubuntu/Containerfile" .
    echo "Build complete: $IMAGE ($VERSION)"
    ;;

  start)
    if [[ ! -f "$APP_DIR/.env" ]]; then
      echo "Missing $APP_DIR/.env -- copy env-example there and set OLLAMA_BASE_URL first."
      exit 1
    fi
    echo "Starting $CONTAINER on 127.0.0.1:$HOST_PORT ..."
    sudo podman rm -f "$CONTAINER" 2>/dev/null || true
    sudo podman run -d \
      --name "$CONTAINER" \
      --restart=always \
      -p "127.0.0.1:${HOST_PORT}:8121" \
      --env-file "$APP_DIR/.env" \
      -e K9_ENV=production \
      "$IMAGE"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  K9-AIF + OpenAI Agents SDK: weather by zip code"
    echo "  Local:  http://127.0.0.1:${HOST_PORT}"
    echo "  Public: through your tunnel (e.g. https://openai.k9x.ai)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ;;

  stop)
    echo "Stopping $CONTAINER ..."
    sudo podman stop "$CONTAINER" 2>/dev/null || true
    echo "Stopped."
    ;;

  logs)
    sudo podman logs -f "$CONTAINER"
    ;;

  all)
    "$0" build
    "$0" start
    ;;

  help|*)
    echo "Usage: $0 <command>"
    echo ""
    echo "  build   build the Podman image ($IMAGE)"
    echo "  start   start the container on 127.0.0.1:${HOST_PORT} (override with HOST_PORT=...)"
    echo "  stop    stop the container"
    echo "  logs    tail logs"
    echo "  all     build + start"
    ;;
esac
