#!/usr/bin/env bash
# k9chat — build and run helper (single container, no pod needed)
# Run from anywhere on the Podman host (no sudo needed to invoke -- the
# script escalates internally). Mirrors k9x_mcp_server's ubuntu/build-
# run.sh structure (build/start/stop/logs/all).
#
# Build context is ai/ (parent of both k9-aif-framework/ and this repo,
# k9-aif-examples/) -- the image needs both k9_aif_abb/ and k9chat/
# together, see the Containerfile. Clone k9-aif-framework as a sibling of
# this repo first.
#
# Runs rootful (sudo podman), matching the k9x_mcp_server/studiox_ibm
# precedent. USER 1001 in the Containerfile still applies inside the
# container regardless of how it was launched.
#
# Requires k9chat/.env to already exist on the host (copy
# k9chat/.env.example there and fill in your own Ollama host, GPU
# telemetry URL, etc. -- start refuses to run without it).
#
# Commands:
#   build   — build the k9chat container image
#   start   — start the container (port 7777 by default, override with HOST_PORT)
#   stop    — stop the container
#   logs    — tail logs
#   seed    — run seed_knowledge_base.py once against the mounted data volume
#   all     — build + start + seed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
K9CHAT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXAMPLES_ROOT="$(cd "$K9CHAT_DIR/.." && pwd)"
AI_DIR="$(cd "$EXAMPLES_ROOT/.." && pwd)"

[[ -d "$AI_DIR/k9-aif-framework/k9_aif_abb" ]] || {
  echo "Error: $AI_DIR/k9-aif-framework/k9_aif_abb not found."
  echo "  Clone k9-aif-framework as a sibling of this repo first."
  exit 1
}
K9AIF_REL_PATH="k9-aif-framework"
K9EXAMPLES_REL_PATH="$(basename "$EXAMPLES_ROOT")"

IMAGE="k9chat:latest"
CONTAINER="k9chat"
HOST_PORT="${HOST_PORT:-7777}"

cmd="${1:-help}"

case "$cmd" in

  build)
    echo "Building $IMAGE (context: $AI_DIR, framework dir: $K9AIF_REL_PATH, examples dir: $K9EXAMPLES_REL_PATH) ..."
    cd "$AI_DIR"
    sudo podman build -t "$IMAGE" \
      --build-arg "K9AIF_DIR=$K9AIF_REL_PATH" \
      --build-arg "K9EXAMPLES_DIR=$K9EXAMPLES_REL_PATH" \
      -f "$K9EXAMPLES_REL_PATH/k9chat/ubuntu/Containerfile" .
    echo "Build complete: $IMAGE"
    ;;

  start)
    if [[ ! -f "$K9CHAT_DIR/.env" ]]; then
      echo "Missing $K9CHAT_DIR/.env -- copy k9chat/.env.example" \
           "there and fill it in first (Ollama host, GPU telemetry URL, etc.)."
      exit 1
    fi
    echo "Starting $CONTAINER on port $HOST_PORT ..."
    sudo podman rm -f "$CONTAINER" 2>/dev/null || true
    mkdir -p "$K9CHAT_DIR/data"
    # Container runs as USER 1001 internally (Containerfile) regardless of
    # who invoked podman -- world-writable rather than chown'ing to 1001
    # since this host user's own UID varies by machine. Home-network
    # deployment, not multi-tenant, so this tradeoff is fine here.
    chmod -R a+rwX "$K9CHAT_DIR/data"
    sudo podman run -d \
      --name "$CONTAINER" \
      --restart=always \
      -p "${HOST_PORT}:7777" \
      --env-file "$K9CHAT_DIR/.env" \
      -e K9CHAT_CHROMA_PATH=/app/data/.chroma \
      -e K9CHAT_PROJECTS_DB=/app/data/k9chat_projects.db \
      -v "$K9CHAT_DIR/data:/app/data:Z" \
      "$IMAGE"
    echo ""
    HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    HOST_IP="${HOST_IP:-localhost}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  k9chat"
    echo "  UI: http://${HOST_IP}:${HOST_PORT}"
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

  seed)
    if [[ ! -f "$K9CHAT_DIR/.env" ]]; then
      echo "Missing $K9CHAT_DIR/.env -- see 'start' for setup."
      exit 1
    fi
    echo "Seeding the knowledge base into the mounted data volume ..."
    mkdir -p "$K9CHAT_DIR/data"
    chmod -R a+rwX "$K9CHAT_DIR/data"

    # seed_knowledge_base.py also reads from sibling repos and the
    # framework's own root docs (k9x-ecosystem/, dow-k9-aif/, k9-aif-blogs/,
    # doit/assets/, k9-aif-framework/{CLAUDE,SKILLS,README}.md) -- none of
    # that is baked into the image (the Containerfile only copies
    # k9_aif_abb/ + k9chat/), so without these mounts seeding only picks up
    # k9chat's own 2 local docs. Mounted here, at seed time, rather than in
    # the Containerfile so the corpus stays current without a rebuild every
    # time a source doc changes -- each mount is best-effort (only added if
    # it actually exists on this host), matching the seed script's own
    # "missing source is a skip, not a failure" convention.
    #
    # Targets match FRAMEWORK_ROOT/ECOSYSTEM_ROOT/DOW_ROOT/BLOGS_ROOT/
    # DOIT_ASSETS in seed_knowledge_base.py -- FRAMEWORK_ROOT resolves to
    # /k9-aif-framework inside the container (REPO_ROOT's sibling-path
    # default, ../../k9-aif-framework from /app/k9chat/).
    SEED_MOUNTS=()
    add_mount() { [[ -e "$1" ]] && SEED_MOUNTS+=(-v "$1:$2:ro"); }
    add_mount "$AI_DIR/k9-aif-framework/CLAUDE.md"  "/k9-aif-framework/CLAUDE.md"
    add_mount "$AI_DIR/k9-aif-framework/SKILLS.md"  "/k9-aif-framework/SKILLS.md"
    add_mount "$AI_DIR/k9-aif-framework/README.md"  "/k9-aif-framework/README.md"
    add_mount "$AI_DIR/k9-aif-framework/k9_aif_abb/k9_security/CLAUDE.md" \
              "/k9-aif-framework/k9_aif_abb/k9_security/CLAUDE.md"
    add_mount "$AI_DIR/k9x-ecosystem"               "/k9x-ecosystem"
    add_mount "$AI_DIR/dow-k9-aif"                  "/dow-k9-aif"
    add_mount "$AI_DIR/k9-aif-blogs"                "/k9-aif-blogs"
    add_mount "$AI_DIR/doit"                        "/doit"

    sudo podman run --rm \
      --env-file "$K9CHAT_DIR/.env" \
      -e K9CHAT_CHROMA_PATH=/app/data/.chroma \
      -v "$K9CHAT_DIR/data:/app/data:Z" \
      "${SEED_MOUNTS[@]}" \
      "$IMAGE" python -m k9chat.seed_knowledge_base
    ;;

  all)
    "$0" build
    "$0" start
    "$0" seed
    ;;

  help|*)
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  build   — build the Podman image ($IMAGE)"
    echo "  start   — start the container (port ${HOST_PORT}, override with HOST_PORT=...)"
    echo "  stop    — stop the container"
    echo "  logs    — tail logs"
    echo "  seed    — run seed_knowledge_base.py once against the mounted data volume"
    echo "  all     — build + start + seed"
    ;;

esac
