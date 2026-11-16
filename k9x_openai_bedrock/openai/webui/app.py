# SPDX-License-Identifier: Apache-2.0
"""
Web page for the zip-code weather example. Started locally by ./run.sh, or in a container by
ubuntu/build-run.sh (published at openai.k9x.ai through a Cloudflare tunnel).

Public use is bounded: each visitor gets WEATHER_RATE_PER_MIN requests a minute (default 6), and
requests run one at a time against the model server (others wait up to 90 s, then get "busy").

    GET  /                  the page (Weather and Architecture tabs)
    POST /api/weather       {"zip": "30301", "role": "customer", "poison": false}
    GET  /api/health        model server reachable? which catalog models?
    GET  /api/agent         the agent YAML and the Shield checks in force
"""

from __future__ import annotations

import asyncio
import os
import time
import urllib.request
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from weather_zip.app import AGENTS_DIR, ROLE_POLICY, build_adapter
from weather_zip.service import ask

STATIC = Path(__file__).resolve().parent / "static"
STATE: dict = {}
RATE_PER_MIN = int(os.environ.get("WEATHER_RATE_PER_MIN", "6"))
_HITS: dict = defaultdict(deque)
_ONE_AT_A_TIME = asyncio.Semaphore(1)


def _client(request: Request) -> str:
    """The visitor's address: Cloudflare's header when tunnelled, else the socket peer."""
    return (request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


def _rate_limit(client: str) -> None:
    now, hits = time.monotonic(), _HITS[client]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_PER_MIN:
        raise HTTPException(429, f"Limit is {RATE_PER_MIN} requests a minute. Please wait a moment.")
    hits.append(now)


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["adapter"] = build_adapter()
    yield


app = FastAPI(title="Weather by zip code (K9-AIF + OpenAI Agents SDK)", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class WeatherRequest(BaseModel):
    zip: str = Field(..., max_length=500)
    role: str = Field("customer", pattern="^(customer|staff|guest)$")
    poison: bool = False


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/weather")
async def weather(req: WeatherRequest, request: Request):
    _rate_limit(_client(request))
    try:
        await asyncio.wait_for(_ONE_AT_A_TIME.acquire(), timeout=90)
    except asyncio.TimeoutError:
        raise HTTPException(503, "The model server is busy. Please try again in a minute.")
    try:
        return await ask(STATE["adapter"], req.zip.strip(), req.role, req.poison)
    finally:
        _ONE_AT_A_TIME.release()


@app.get("/api/health")
def health():
    adapter = STATE["adapter"].orchestrator_adapter
    inference = adapter.config.get("inference", {})
    base = (inference.get("llm_factory", {}).get("base_url") or "").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/v1/models", timeout=4) as resp:
            reachable = resp.status == 200
    except Exception:
        reachable = False
    catalog = inference.get("model_catalog", {}).get("models", {})
    models = inference.get("llm_factory", {}).get("models", {})
    return {
        "model_server_reachable": reachable,
        "catalog": [{"alias": a, "model": models.get(e.get("llm_ref")), "capabilities": e.get("capabilities")}
                    for a, e in catalog.items()],
        "routing": adapter.model_routing,
        "version": os.environ.get("APP_VERSION", "local"),
        "zero_trust": adapter.enable_zero_trust,
    }


@app.get("/api/agent")
def agent():
    adapter = STATE["adapter"].orchestrator_adapter
    shield = adapter.config.get("security", {}).get("shield", {})
    return {
        "agent_yaml": (Path(AGENTS_DIR) / "weather_agent.yaml").read_text(encoding="utf-8"),
        "shield": {"ingress": shield.get("ingress", {}).get("checks", []),
                   "egress": shield.get("egress", {}).get("checks", [])},
        "role_policy": ROLE_POLICY,
    }
