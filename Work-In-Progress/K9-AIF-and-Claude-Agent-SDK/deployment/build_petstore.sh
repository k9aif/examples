#!/usr/bin/env bash
# Pet Store Agentic -- build and deploy on RHEL (Podman).
# Adjust PROJECT_DIR below to wherever this project actually lands on the
# RHEL host -- this mirrors k9x_satan/deployment/build_satan.sh's shape,
# not a path already confirmed on that box.
set -euo pipefail

PROJECT_DIR=/home/ravinata/ai/k9-aif-examples/petstore-agentic
cd "$PROJECT_DIR"

# .env (POSTGRES_HOST/USER/PASSWORD/DB/SCHEMA) is gitignored -- must already
# exist on this host before running this script. Not shipped in the deploy
# tarball; copy it here once, separately, the same way EOC and Satan expect
# their own .env to already be present.
[[ -f .env ]] || { echo "ERROR: .env not found in $PROJECT_DIR"; exit 1; }

sudo podman build \
  -f deployment/Dockerfile -t k9-petstore:latest .

sudo podman stop k9-petstore 2>/dev/null || true
sudo podman rm   k9-petstore 2>/dev/null || true

# Host-backed file for gates.db (livestock-order approval state) -- without
# this, gate history lives only in the container's writable layer and the
# stop+rm+rebuild this script does on every run would wipe it. World-writable
# because the container runs as UID 1001, which has no reliable identity on
# the RHEL host side of a bind mount (same reasoning as Satan's data dir).
GATES_DB_HOST_DIR=/home/container_storage/volumes/k9-aif-examples/petstore-agentic
sudo mkdir -p "$GATES_DB_HOST_DIR"
sudo touch "$GATES_DB_HOST_DIR/gates.db"
sudo chmod 777 "$GATES_DB_HOST_DIR/gates.db"

sudo podman run -d --name k9-petstore \
  --restart=always \
  --memory=2g --cpus=2 \
  -p 127.0.0.1:8500:8500 \
  -v "$GATES_DB_HOST_DIR/gates.db":/app/webui/gates.db:Z \
  --env-file .env \
  k9-petstore:latest

echo "Deployed. Tail logs with: sudo podman logs -f k9-petstore"
