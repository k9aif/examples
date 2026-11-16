# SPDX-License-Identifier: Apache-2.0
"""
Local web page for the zip-code weather example. Started by ./run.sh; not meant for hosting.

    GET  /                  the page (Weather and Architecture tabs)
    POST /api/weather       {"zip": "30301", "role": "customer", "poison": false}
    GET  /api/health        model server reachable? which catalog models?
    GET  /api/agent         the agent YAML and the Shield checks in force
"""

from __future__ import annotations

import os
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from weather_zip.app import AGENTS_DIR, ROLE_POLICY, build_adapter
from weather_zip.service import ask

STATIC = Path(__file__).resolve().parent / "static"
STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["adapter"] = build_adapter()
    yield


app = FastAPI(title="Weather by zip code (K9-AIF + OpenAI Agents SDK)", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class WeatherRequest(BaseModel):
    zip: str = Field(..., max_length=500)
    role: str = "customer"
    poison: bool = False


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/weather")
async def weather(req: WeatherRequest):
    return await ask(STATE["adapter"], req.zip.strip(), req.role, req.poison)


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
