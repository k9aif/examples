# Pet Store Agentic — deterministic storefront, RHEL UBI 9 Python 3.11 image
#
# The running storefront (webui/webui_server.py) imports only
# petstore/gates, petstore/services, and petstore/services/original_catalog_data
# -- none of which import k9_aif_abb. The framework is proven substitutable
# via petstore/abb + petstore/sbb (DiagnosisAgent, tested), but that path
# isn't wired into the live storefront yet -- so, unlike k9x_satan's
# Dockerfile, this image does NOT need a k9-aif-framework git clone.
#
# Build (from inside K9-AIF-and-Claude-Agent-SDK/):
#   podman build -f deployment/Dockerfile -t k9-petstore:latest .

FROM registry.access.redhat.com/ubi9/python-311:latest

USER root

WORKDIR /app

# Copy dependency file first so this layer stays cached unless it changes.
COPY requirements-deploy.txt /tmp/requirements-deploy.txt

RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r /tmp/requirements-deploy.txt

# Application source.
COPY petstore /app/petstore
COPY webui /app/webui

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    K9_ENV=production \
    PETSTORE_WEBUI_PORT=8500

# gates.db (SQLite, livestock-gate approval state) is written here at
# runtime -- webui_server.py chdir()s into webui/ before serve_forever().
# Owned by UID 1001 (the runtime USER below) with group-root write, so it
# works both as an anonymous container dir and as a host bind-mount target
# (build_petstore.sh maps this to a host-backed volume so gate history
# survives podman stop/rm/rebuild, not just process restarts).
RUN chown -R 1001:0 /app/webui && chmod -R g+rwX /app/webui

EXPOSE 8500

# No /health route exists on this app (unlike the FastAPI-based ecosystem
# products) -- webui_server.py is a plain http.server; hit / instead.
HEALTHCHECK --interval=30s --timeout=8s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8500/')" \
      || exit 1

USER 1001

CMD ["python3", "webui/webui_server.py"]
