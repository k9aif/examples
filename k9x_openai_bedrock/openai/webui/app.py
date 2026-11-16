# SPDX-License-Identifier: Apache-2.0
"""
Web page for the zip-code weather example. Started locally by ./run.sh, or in a container by
ubuntu/build-run.sh (published at openai.k9x.ai through a Cloudflare tunnel).

Public use is bounded: each visitor gets WEATHER_RATE_PER_MIN requests a minute (default 6), and
requests run one at a time against the model server (others wait up to 90 s, then get "busy").
Nothing a visitor sends or receives is stored or shown to anyone else (see weather_zip/service.py);
answers are sent with Cache-Control: no-store.

    GET  /                  public landing page
    GET  /login, POST /login, POST /logout
    GET  /app               the demo (Weather and Architecture tabs); needs a session
    POST /api/weather       {"zip": "30301", "role": "customer", "poison": false}; needs a session
    GET  /api/health        model server reachable? which catalog models?
    GET  /api/agent         the agent YAML and the Shield checks in force
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import time
import urllib.request
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from weather_zip.app import AGENTS_DIR, ROLE_POLICY, build_adapter
from weather_zip.service import ask

STATIC = Path(__file__).resolve().parent / "static"
STATE: dict = {}
RATE_PER_MIN = int(os.environ.get("WEATHER_RATE_PER_MIN", "6"))
_HITS: dict = defaultdict(deque)
_ONE_AT_A_TIME = asyncio.Semaphore(int(os.environ.get("WEATHER_CONCURRENCY", "1")))


def _client(request: Request) -> str:
    """The visitor's address: Cloudflare's header when tunnelled, else the socket peer."""
    return (request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


# ── Sign-in: demo login only, one private session per sign-in ─────────────────
# The demo password is shown on the page (K9X convention: demo login only, never an admin one).
# Each sign-in gets its own random session id in an HttpOnly cookie, signed with SESSION_SECRET
# (random per process when unset, so a restart signs everyone out). Sessions live in memory.
DEMO_USER = os.environ.get("DEMO_USER", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo")
_SECRET = (os.environ.get("SESSION_SECRET") or secrets.token_hex(32)).encode()
_SESSIONS: dict = {}
_SESSION_TTL_S = 8 * 3600
_COOKIE = "k9x_openai_session"


def _sign(sid: str) -> str:
    return sid + "." + hmac.new(_SECRET, sid.encode(), hashlib.sha256).hexdigest()[:32]


def _session(request: Request) -> str | None:
    raw = request.cookies.get(_COOKIE) or ""
    sid, _, sig = raw.partition(".")
    if not sid or not hmac.compare_digest(_sign(sid), raw):
        return None
    created = _SESSIONS.get(sid)
    if created is None or time.time() - created > _SESSION_TTL_S:
        _SESSIONS.pop(sid, None)
        return None
    return sid


def _require_session(request: Request) -> str:
    sid = _session(request)
    if sid is None:
        raise HTTPException(401, "Please sign in again.")
    return sid


def _page(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8").replace("__DEMO_PASSWORD__", DEMO_PASSWORD)


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


@app.get("/", response_class=HTMLResponse)
def landing():
    return _page("landing.html")


@app.get("/login", response_class=HTMLResponse)
def login_page(error: int = 0):
    page = _page("login.html")
    if error:
        page = page.replace("<!--ERROR-->", '<div class="err">That user name and password don\'t match.</div>')
    return page


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    _rate_limit("login:" + _client(request))
    ok = hmac.compare_digest(username, DEMO_USER) & hmac.compare_digest(password, DEMO_PASSWORD)
    if not ok:
        return RedirectResponse("/login?error=1", status_code=303)
    now = time.time()
    for old in [k for k, t in _SESSIONS.items() if now - t > _SESSION_TTL_S]:
        _SESSIONS.pop(old, None)
    sid = secrets.token_urlsafe(24)
    _SESSIONS[sid] = now
    resp = RedirectResponse("/app", status_code=303)
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(_COOKIE, _sign(sid), httponly=True, samesite="lax", secure=secure, max_age=_SESSION_TTL_S)
    return resp


@app.post("/logout")
def logout(request: Request):
    sid = _session(request)
    if sid:
        _SESSIONS.pop(sid, None)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(_COOKIE)
    return resp


@app.get("/app")
def demo_app(request: Request):
    if _session(request) is None:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store, private"})


@app.post("/api/weather")
async def weather(req: WeatherRequest, request: Request):
    sid = _require_session(request)
    _rate_limit(_client(request))
    _rate_limit("session:" + sid)
    try:
        await asyncio.wait_for(_ONE_AT_A_TIME.acquire(), timeout=90)
    except asyncio.TimeoutError:
        raise HTTPException(503, "The model server is busy. Please try again in a minute.")
    try:
        result = await ask(STATE["adapter"], req.zip.strip(), req.role, req.poison)
    finally:
        _ONE_AT_A_TIME.release()
    # One visitor's answer must never be served to another from a browser or CDN cache.
    return JSONResponse(result, headers={"Cache-Control": "no-store, private"})


@app.get("/api/health")
def health(request: Request):
    _require_session(request)
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
def agent(request: Request):
    _require_session(request)
    adapter = STATE["adapter"].orchestrator_adapter
    shield = adapter.config.get("security", {}).get("shield", {})
    return {
        "agent_yaml": (Path(AGENTS_DIR) / "weather_agent.yaml").read_text(encoding="utf-8"),
        "shield": {"ingress": shield.get("ingress", {}).get("checks", []),
                   "egress": shield.get("egress", {}).get("checks", [])},
        "role_policy": ROLE_POLICY,
    }
