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
    POST /api/ap/batch              ten invoices at once; the few that need a person wait in K9X HIL
    (decisions are taken in K9X HIL itself, hil.k9x.ai; its reply on Kafka resumes the same run)
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


def _session_ref(sid: str | None) -> str:
    """A short fingerprint of the session for the page (never the session id itself: that is the secret that keeps
    each visitor's runs private)."""
    return hashlib.sha256(sid.encode()).hexdigest()[:8] if sid else ""


_SIGN_IN_FORM = ('<form method="post" action="/login" style="margin:0"><input type="hidden" name="username" '
                 'value="__DEMO_USER__"><input type="hidden" name="password" value="__DEMO_PASSWORD__">'
                 '<input type="hidden" name="tab" value="home"><button class="{cls}" type="submit">{label}</button></form>')


def _auth_bits(sid: str | None) -> dict:
    """The landing page's sign-in controls: signed out, Sign in signs in as the demo user at once; signed in, the
    session's fingerprint (subtle) and Sign out."""
    if sid:
        who = (f'<span class="who" title="Your private session (a fingerprint, not the session id)">'
               f'{DEMO_USER} · session {_session_ref(sid)}</span>'
               '<form method="post" action="/logout" style="margin:0"><button class="signout" type="submit">'
               'Sign out</button></form>')
        return {"<!--AUTH-->": who, "<!--AUTH_TOC-->": ""}
    return {"<!--AUTH-->": _SIGN_IN_FORM.format(cls="signin", label="Sign in"),
            "<!--AUTH_TOC-->": "<li>" + _SIGN_IN_FORM.format(cls="toclink", label="Sign in →") + "</li>"}


def _page(name: str, sid: str | None = None) -> str:
    import html
    import re
    text = (STATIC / name).read_text(encoding="utf-8")
    for marker, value in _auth_bits(sid).items():
        text = text.replace(marker, value)
    text = (text.replace("__SESSION_REF__", f"session {_session_ref(sid)}" if sid else "")
            .replace("__DEMO_USER__", html.escape(DEMO_USER)).replace("__DEMO_PASSWORD__", DEMO_PASSWORD)
            .replace("__BUILD__", html.escape(os.environ.get("APP_VERSION", "local")))
            .replace("__DEMO_CSS_V__", "__V:demo.css__"))
    # __V:<static file>__ -> its content hash: a changed file gets a new URL, so a CDN never serves a stale copy
    return re.sub(r"__V:([\w.-]+)__", lambda m: _content_hash(m.group(1)), text)


def _content_hash(name: str) -> str:
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


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
def landing(request: Request):
    return HTMLResponse(_page("landing.html", _session(request)), headers={"Cache-Control": "no-store, private"})


@app.get("/patterns", response_class=HTMLResponse)
def patterns(request: Request):
    """OpenAI Agents SDK orchestration patterns: a public reference page, no sign-in."""
    return HTMLResponse(_page("openai_patterns.html", _session(request)), headers={"Cache-Control": "no-store, private"})


@app.get("/guardrails", response_class=HTMLResponse)
def guardrails(request: Request):
    """OpenAI's guardrails guidance next to what K9-AIF adds (Zero Trust, Shield, Guardian, HIL): public, no sign-in."""
    return HTMLResponse(_page("guardrails.html", _session(request)), headers={"Cache-Control": "no-store, private"})


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
    sid = _session(request)                    # already signed in: keep the same session (and its runs)
    if sid is None:
        sid = secrets.token_urlsafe(24)
        _SESSIONS[sid] = now
    if tab == "home":
        target = "/"                           # Sign in on the landing page: stay there, pick a use case
    else:
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
    return HTMLResponse(_page("index.html", _session(request)), headers={"Cache-Control": "no-store, private"})


@app.get("/ap")
def ap_demo(request: Request):
    """Use case 3, accounts payable with K9X HIL: its own page (the weather demo is /app)."""
    if _session(request) is None:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_page("ap.html", _session(request)), headers={"Cache-Control": "no-store, private"})


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
        # for the signed-in pages' top bar, like das.k9x.ai: the model agents with tools are routed to, and where it runs
        "agent_model": _agent_model(inference),
        "shield": bool(((adapter.config.get("security") or {}).get("shield") or {}).get("enabled")),
        "guardian": str(((adapter.config.get("governance") or {}).get("guardian") or {}).get("enabled", "")).lower()
                    in ("1", "true", "yes"),
        "model_host": os.environ.get("MODEL_HOST_LABEL", ""),
    }


def _agent_model(inference: dict) -> str:
    """The catalog's tool-calling model: the K9 Model Router sends every agent on this site to it (the weather agent,
    InvoiceAgent and PaymentAgent; checked with K9ModelProvider). A catalog with more models would need the per-run
    choice shown instead."""
    models = inference.get("llm_factory", {}).get("models", {})
    for entry in inference.get("model_catalog", {}).get("models", {}).values():
        if "tool_calling" in (entry.get("capabilities") or []):
            return models.get(entry.get("llm_ref"), "") or ""
    return ""


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
AP_OPEN_PER_SESSION = int(os.environ.get("AP_OPEN_PER_SESSION", "3"))   # runs still working (model calls), per visitor
AP_WAITING_PER_SESSION = int(os.environ.get("AP_WAITING_PER_SESSION", "10"))   # runs parked for a person, per visitor
AP_QUEUE_MAX = int(os.environ.get("AP_QUEUE_MAX", "30"))   # invoices running or waiting to run, all visitors together
_AP_QUEUED = {"submitted", "running", "resuming"}


def _ap_queue_full(rt, adding: int) -> None:
    """One GPU runs the invoices one at a time: the queue holds at most AP_QUEUE_MAX, for everyone together."""
    queued = sum(1 for r in rt.runs.values() if r["status"] in _AP_QUEUED)
    if queued + adding > AP_QUEUE_MAX:
        raise HTTPException(429, f"The queue is full ({queued} of {AP_QUEUE_MAX} invoices, from all visitors). "
                                 "They run one at a time; try again in a few minutes.")
_AP_DONE = {"completed", "rejected", "error", "blocked"}
_HIL_FIELDS = ("id", "title", "status", "priority", "queue_name", "application_name", "assigned_to",
               "correlation_id", "reply_to", "ttl_hours", "ttl_action", "created_at", "completed_at", "payload",
               "task_type", "required_role", "decision_authority", "artifact_list", "contract", "require_comment")
_NO_STORE = {"Cache-Control": "no-store, private"}


def _ap():
    rt = STATE.get("ap")
    if rt is None:
        raise HTTPException(503, "The accounts payable demo isn't running here (KAFKA_BOOTSTRAP_SERVERS not set).")
    return rt


class APSubmit(BaseModel):
    invoice: str = Field(..., pattern="^(small|large|bank|blocked|inject|disclose|divert|flood|guest|reworded)$")
    guardian: bool = True          # False: Granite Guardian off for this run only (the visitor's own experiment)


@app.get("/api/ap/status")
def ap_status(request: Request):
    _require_session(request)
    rt = STATE.get("ap")
    if rt is None:
        return {"running": False}
    from accounts_payable.runtime import ATTACKS, BATCH, INVOICES
    attacks = {k: (t if len(t) <= 400 else t[:300] + f" … ({len(t):,} characters in all)") for k, (t, _) in ATTACKS.items()}
    return {"running": True, "invoices": {**INVOICES, **BATCH, **attacks}, "hil_url": rt.hil_url,
            "hil_api": bool(rt.hil_url and rt.hil_key)}


@app.post("/api/ap/runs")
async def ap_submit(req: APSubmit, request: Request):
    sid = _require_session(request)
    rt = _ap()
    _rate_limit(_client(request))
    _rate_limit("session:" + sid)
    mine = [r for r in rt.runs.values() if r["owner"] == sid and r["status"] not in _AP_DONE]
    working = [r for r in mine if r["status"] != "pending_hil"]       # a run waiting for a person holds nothing
    waiting = [r for r in mine if r["status"] == "pending_hil"]
    if len(working) >= AP_OPEN_PER_SESSION:
        raise HTTPException(429, f"You have {len(working)} invoices still running. Wait for one to finish.")
    if len(waiting) >= AP_WAITING_PER_SESSION:
        raise HTTPException(429, f"You have {len(waiting)} invoices waiting for a person. Decide some first.")
    _ap_queue_full(rt, 1)
    run_id = await asyncio.to_thread(rt.submit, req.invoice, sid, req.guardian)
    return JSONResponse({"run_id": run_id}, headers=_NO_STORE)


@app.get("/api/ap/runs")
def ap_runs(request: Request):
    """This visitor's runs, newest first (for the page's 'Your runs' strip)."""
    sid = _require_session(request)
    rt = _ap()
    mine = sorted((r for r in rt.runs.values() if r["owner"] == sid), key=lambda r: r["created"], reverse=True)
    return JSONResponse([{"run_id": r["run_id"], "invoice": r["invoice"], "label": r.get("label"), "status": r["status"]}
                         for r in mine[:30]],
                        headers=_NO_STORE)


@app.get("/api/ap/queue")
def ap_queue(request: Request):
    """Every visitor's invoices in the order the orchestrator takes them, one at a time: the one working now, then
    the ones waiting. Only this visitor's own entries carry a name; the others say only that they are someone
    else's. Runs parked for a person are not in the queue (they hold nothing)."""
    sid = _require_session(request)
    rt = _ap()
    order = {"running": 0, "resuming": 0, "submitted": 1}
    live = sorted((r for r in rt.runs.values() if r["status"] in order),
                  key=lambda r: (order[r["status"]], r["created"]))
    items = [{"mine": r["owner"] == sid, "status": r["status"],
              "label": (r.get("label") or r["invoice"]) if r["owner"] == sid else None} for r in live]
    return JSONResponse({"total": len(items), "max": AP_QUEUE_MAX, "items": items[:12]}, headers=_NO_STORE)


@app.get("/api/ap/runs/{run_id}")
def ap_run(run_id: str, request: Request):
    sid = _require_session(request)
    run = _ap().view(run_id, sid)
    if run is None:
        raise HTTPException(404, "No such run in this session.")
    return JSONResponse(run, headers=_NO_STORE)


@app.get("/api/ap/hil-queue")
async def ap_hil_queue(request: Request):
    """This visitor's invoices sent to K9X HIL, with each task's status from K9X HIL (read only)."""
    sid = _require_session(request)
    rt = _ap()
    return JSONResponse(await asyncio.to_thread(rt.hil_queue, sid), headers=_NO_STORE)


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


@app.post("/api/ap/batch")
async def ap_batch(request: Request):
    """Ten invoices at once, the way a day's invoices arrive: they run one after another; the few that need a person
    wait in K9X HIL while the rest finish."""
    sid = _require_session(request)
    rt = _ap()
    _rate_limit(_client(request))
    _rate_limit("session:" + sid)
    from accounts_payable.runtime import BATCH
    busy = [r for r in rt.runs.values() if r["owner"] == sid and r["status"] not in _AP_DONE | {"pending_hil"}]
    if busy:
        raise HTTPException(429, f"{len(busy)} of your invoices are still running. Start the batch when they finish.")
    waiting = [r for r in rt.runs.values() if r["owner"] == sid and r["status"] == "pending_hil"]
    if len(waiting) + 3 > AP_WAITING_PER_SESSION:
        raise HTTPException(429, f"You have {len(waiting)} invoices waiting for a person. Decide some in K9X HIL first.")
    _ap_queue_full(rt, len(BATCH))
    ids = [await asyncio.to_thread(rt.submit, key, sid) for key in BATCH]
    return JSONResponse({"run_ids": ids}, headers=_NO_STORE)
