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
    GET  /app               the weather demo (Weather, Architecture, Multi-agent tabs); needs a session
    GET  /ap                the accounts payable demo with K9X HIL (use case 3); needs a session
    POST /api/weather       {"zip": "30301", "role": "customer", "poison": false}; needs a session
    GET  /health            public: 200 {"status": "ok"} when the demo can answer, 503 when its model server
                            is unreachable (for the K9X Dashboard; no model names)
    GET  /api/health        model server reachable? which catalog models?
    GET  /api/agent         the agent YAML and the Shield checks in force

  Accounts payable (use case 3; on when KAFKA_BOOTSTRAP_SERVERS is set), all scoped to the visitor's session:
    GET  /api/ap/status             is the AP demo running here?
    POST /api/ap/runs               {"invoice": "small|large|bank|blocked"} -> run_id (Router -> Kafka -> squad)
    GET  /api/ap/runs/{run_id}      the run: trace, the invoice read, the rule that fired, the payment
    GET  /api/ap/runs/{run_id}/hil  its K9X HIL task (through the HIL REST API; the key stays on this server)
    POST /api/ap/runs/{run_id}/hil  {"action": "complete|reject", "comment": "..."}: decide in K9X HIL, which
                                    replies on Kafka; the Router resumes the same run
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
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

from k9_aif_abb.k9_utils.config_loader import load_yaml
from weather_zip.app import AGENTS_DIR, CONFIG_PATH, ROLE_POLICY, build_adapter
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
    import html
    css_v = hashlib.sha256((STATIC / "demo.css").read_bytes()).hexdigest()[:10]   # new content, new URL (CDN cache)
    return ((STATIC / name).read_text(encoding="utf-8").replace("__DEMO_PASSWORD__", DEMO_PASSWORD)
            .replace("__BUILD__", html.escape(os.environ.get("APP_VERSION", "local"))).replace("__DEMO_CSS_V__", css_v))


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
    STATE["ap"] = None
    if os.environ.get("KAFKA_BOOTSTRAP_SERVERS"):
        from accounts_payable.runtime import APRuntime
        STATE["ap"] = APRuntime(load_yaml(CONFIG_PATH))
        await STATE["ap"].start()
    else:
        logging.getLogger("webui").warning(
            "[webui] KAFKA_BOOTSTRAP_SERVERS not set: the accounts payable demo (use case 3) is off; weather runs")
    yield
    if STATE["ap"] is not None:
        await STATE["ap"].stop()


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


_TABS = {"weather", "arch", "multi", "ap"}      # "ap" opens /ap      # tabs a landing-page row may open after sign-in


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), tab: str = Form("")):
    _rate_limit("login:" + _client(request))
    ok = hmac.compare_digest(username, DEMO_USER) & hmac.compare_digest(password, DEMO_PASSWORD)
    if not ok:
        return RedirectResponse("/login?error=1", status_code=303)
    now = time.time()
    for old in [k for k, t in _SESSIONS.items() if now - t > _SESSION_TTL_S]:
        _SESSIONS.pop(old, None)
    sid = secrets.token_urlsafe(24)
    _SESSIONS[sid] = now
    target = "/ap" if tab == "ap" else "/app" + (f"#{tab}" if tab in _TABS else "")   # use case 3 is its own page
    resp = RedirectResponse(target, status_code=303)
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
    return HTMLResponse(_page("index.html"), headers={"Cache-Control": "no-store, private"})


@app.get("/ap")
def ap_demo(request: Request):
    """Use case 3, accounts payable with K9X HIL: its own page (the weather demo is /app)."""
    if _session(request) is None:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_page("ap.html"), headers={"Cache-Control": "no-store, private"})


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


def _model_server_reachable(timeout: float = 4) -> bool:
    inference = STATE["adapter"].orchestrator_adapter.config.get("inference", {})
    base = (inference.get("llm_factory", {}).get("base_url") or "").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/v1/models", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


@app.get("/health")
def public_health():
    """Public liveness for the K9X Dashboard: the demo answers only when its model server does, so an unreachable
    model server is reported as 503, not as "up". Says nothing about which models run."""
    if _model_server_reachable(timeout=2):
        return {"status": "ok", "service": "openai-weather"}
    return JSONResponse({"status": "unavailable", "service": "openai-weather",
                         "reason": "model server unreachable"}, status_code=503)


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


# ── Accounts payable (use case 3) ─────────────────────────────────────────────
AP_OPEN_PER_SESSION = int(os.environ.get("AP_OPEN_PER_SESSION", "3"))   # runs not yet finished, per visitor
_AP_DONE = {"completed", "rejected", "error"}
_HIL_FIELDS = ("id", "title", "status", "priority", "queue_name", "application_name", "assigned_to",
               "correlation_id", "reply_to", "ttl_hours", "ttl_action", "created_at", "completed_at", "payload",
               "task_type", "required_role", "decision_authority", "artifact_list", "contract")
_NO_STORE = {"Cache-Control": "no-store, private"}


def _ap():
    rt = STATE.get("ap")
    if rt is None:
        raise HTTPException(503, "The accounts payable demo isn't running here (KAFKA_BOOTSTRAP_SERVERS not set).")
    return rt


class APSubmit(BaseModel):
    invoice: str = Field(..., pattern="^(small|large|bank|blocked)$")


class APDecision(BaseModel):
    action: str = Field(..., pattern="^(complete|reject)$")
    comment: str = Field("", max_length=300)


@app.get("/api/ap/status")
def ap_status(request: Request):
    _require_session(request)
    rt = STATE.get("ap")
    if rt is None:
        return {"running": False}
    from accounts_payable.runtime import INVOICES
    return {"running": True, "invoices": INVOICES, "hil_url": rt.hil_url, "hil_api": bool(rt.hil_url and rt.hil_key)}


@app.post("/api/ap/runs")
async def ap_submit(req: APSubmit, request: Request):
    sid = _require_session(request)
    rt = _ap()
    _rate_limit(_client(request))
    _rate_limit("session:" + sid)
    open_runs = [r for r in rt.runs.values() if r["owner"] == sid and r["status"] not in _AP_DONE]
    if len(open_runs) >= AP_OPEN_PER_SESSION:
        raise HTTPException(429, f"You have {len(open_runs)} invoices still in flight. Decide or wait for them first.")
    run_id = await asyncio.to_thread(rt.submit, req.invoice, sid)
    return JSONResponse({"run_id": run_id}, headers=_NO_STORE)


@app.get("/api/ap/runs/{run_id}")
def ap_run(run_id: str, request: Request):
    sid = _require_session(request)
    run = _ap().view(run_id, sid)
    if run is None:
        raise HTTPException(404, "No such run in this session.")
    return JSONResponse(run, headers=_NO_STORE)


@app.get("/api/ap/runs/{run_id}/hil")
async def ap_hil_task(run_id: str, request: Request):
    sid = _require_session(request)
    rt = _ap()
    if rt.view(run_id, sid) is None:
        raise HTTPException(404, "No such run in this session.")
    try:
        task = await asyncio.to_thread(rt.hil_task, run_id, sid)
    except RuntimeError as exc:                       # HIL API not configured here
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"K9X HIL didn't answer: {type(exc).__name__}")
    return JSONResponse({"task": {k: task.get(k) for k in _HIL_FIELDS} if task else None}, headers=_NO_STORE)


@app.post("/api/ap/runs/{run_id}/hil")
async def ap_hil_decide(run_id: str, req: APDecision, request: Request):
    sid = _require_session(request)
    rt = _ap()
    _rate_limit("session:" + sid)
    if rt.view(run_id, sid) is None:
        raise HTTPException(404, "No such run in this session.")
    try:
        out = await asyncio.to_thread(rt.hil_decide, run_id, sid, req.action, req.comment.strip())
    except LookupError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 409:
            raise HTTPException(409, "This task was already decided in K9X HIL.")
        raise HTTPException(502, f"K9X HIL refused the decision: {type(exc).__name__} {status or ''}".strip())
    return JSONResponse(out, headers=_NO_STORE)
