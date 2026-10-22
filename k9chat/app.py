# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework

import asyncio
import json
import logging
import random
import re
import os
import sys
import time
import uuid

# app.py is uvicorn's actual import target (k9chat.app:app) -- the one
# file in k9chat that most needs to be self-sufficient regardless of
# which Python/uvicorn launches it. Relying on cwd already being on
# sys.path (true for a plain `python`/`uvicorn` invocation from the repo
# root) breaks the moment a *different* environment's uvicorn is on PATH
# (e.g. a global/Homebrew install with its own old pip-installed k9-aif)
# or --reload's spawned subprocess doesn't inherit it -- confirmed live,
# 2026-09-20: `ModuleNotFoundError: No module named 'k9chat'`
# from exactly that combination. Same pattern chat.py/chat_agent.py/
# seed_knowledge_base.py already use; this was the one file missing it.
#
# Two separate roots now (k9chat moved into its own k9-aif-examples repo
# 2026-09-21, previously both of these were the same k9-aif-framework
# root): FRAMEWORK_ROOT for k9_aif_abb/ imports (sibling checkout,
# override via K9AIF_FRAMEWORK_PATH), EXAMPLES_ROOT so `k9chat.*` resolves
# as a package regardless of invocation directory.
FRAMEWORK_ROOT = os.environ.get(
    "K9AIF_FRAMEWORK_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../k9-aif-framework")),
)
if FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, FRAMEWORK_ROOT)

EXAMPLES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if EXAMPLES_ROOT not in sys.path:
    sys.path.insert(0, EXAMPLES_ROOT)

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from k9chat.chat import (
    send_message,
    send_message_stream,
    is_streaming_enabled,
    toggle_streaming,
    is_evaluation_enabled,
    toggle_evaluation,
    evaluate_response,
    get_chat_runtime_info,
    get_health_status,
    run_chat_startup_check,
    clear_session,
    truncate_session,
    list_models_for,
    get_selectable_models,
    apply_settings,
    create_project,
    list_projects,
    get_project,
    update_project,
    delete_project,
    add_project_file,
    remove_project_file,
    get_last_assistant_reply,
    is_correction_learning_enabled,
    learn_from_correction,
    get_k9chat_version,
    ScreenRefused,
    is_provider_settings_enabled,
    check_faq_shortcut,
    is_faq_shortcut_enabled,
    toggle_faq_shortcut,
    is_internet_search_enabled,
    toggle_internet_search,
    set_session_internet,
    reset_session_internet,
    is_framework_mode_locked,
    is_guardian_enabled,
)
from k9chat.project_manager import ProjectNotFoundError
from k9chat.auth import (
    LoginRequiredMiddleware,
    current_owner_id,
    get_session_secret,
    sanitize_username,
)
from k9chat.queue_control import QueueBusy, QueueSlot
from k9chat import queue_control
from k9chat.rate_limit import RateLimiter
from k9chat.chat import load_config, _clamp_tone_for_framework_mode

BASE_DIR = os.path.dirname(__file__)

app = FastAPI(title="K9Chat UI")

# Always active now (see auth.py's module docstring for why the old
# opt-in password gate was dropped) -- every visitor passes through the
# name-entry step once.
#
# Order matters: Starlette's add_middleware() prepends, so the middleware
# added LAST ends up OUTERMOST (runs first on each request). Add
# LoginRequiredMiddleware first and SessionMiddleware second so
# SessionMiddleware actually wraps it and request.session exists by the
# time LoginRequiredMiddleware.dispatch() reads it -- reversing this order
# throws "SessionMiddleware must be installed" on every single request.
class SessionModeMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so the visitor's Framework Mode,
    read from their session, is in context for the whole request --
    including a streamed reply and the threads it hands work to. Added
    first so it runs inside SessionMiddleware (scope["session"] exists)."""

    def __init__(self, app_):
        self.app = app_

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        session = scope.get("session") or {}
        token = set_session_internet(session.get("internet_mode"))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_session_internet(token)


app.add_middleware(SessionModeMiddleware)
app.add_middleware(LoginRequiredMiddleware)
app.add_middleware(SessionMiddleware, secret_key=get_session_secret())


_RATE_LIMITER = RateLimiter(load_config())
log = logging.getLogger("k9chat.app")

# Shield blocks are a reply, not a dead stream: a PermissionError from the
# governed agent used to end /chat/stream silently and the UI waited
# forever. Message wording is Ravi's (2026-10-22).
_BLOCKED_QUIPS = (
    "What is that you're trying to do? Hacking? Sorry, man.",
    "Nice try. Bold, even. But no.",
    "You brought a prompt injection to a governed agent. Respect the hustle, but no.",
    "I see what you did there. So did the Shield.",
    "That's not a question, that's a heist. Heist cancelled.",
    "Somewhere a pen-tester is proud of you. The Shield is not.",
    "Hacker mode detected. Governance mode: always on.",
    "Respectfully: absolutely not.",
    "You tried. The Shield tried harder.",
    "Plot twist: the model never even saw it.",
    "Access denied, with love.",
    "Cute. Did you think there wasn't a bouncer?",
)

# Unhinged dial near the top (and Framework Mode OFF, same rule as the
# dial itself): the hacker gets the unfiltered version. Ravi's call.
_BLOCKED_QUIPS_UNHINGED = (
    "What the fuck are you trying to upload here, you fucking moron?",
    "Are you shitting me? A prompt injection? In this economy?",
    "Holy shit, that's the laziest hack I've seen all week.",
    "Get the fuck out of here with that injection garbage.",
    "Bro really thought 'ignore all previous instructions' would work. Fucking adorable.",
    "Nope. Hell no. Absolutely fucking not.",
    "You call that a hack? My toaster has better tradecraft, dumbass.",
    "Take your sketchy-ass payload and shove it right back where it came from.",
    "Jesus Christ, at least try to be original, you script-kiddie goblin.",
    "Oh fuck off. You really thought that would work?",
    "Damn, you're persistent. Persistently fucking wrong.",
    "That payload is dumber than a bag of hammers. Denied.",
    "Hell no. Go bother a chatbot that doesn't have a goddamn bodyguard.",
    "Wow. Just wow. Who taught you to hack, a fortune cookie?",
    "Cute little exploit. Now piss off.",
)
_UNHINGED_QUIP_LEVEL = 3   # Have Fun dial level (0-4) where the unfiltered pool starts

_CHECK_LABELS = {
    "PromptInjectionCheck": "prompt injection",
    "InputSizeCheck": "oversized input",
    "PIIBoundaryCheck": "personal data",
}


def _blocked_reply(exc: PermissionError, unhinged_level: int = 0, profanity_level: int = 0) -> str:
    text = str(exc)
    m = re.search(r"\[(\w+)\]", text)
    check = _CHECK_LABELS.get(m.group(1), m.group(1)) if m else "a security check"
    found = re.search(r"'([^']{1,80})'", text)
    detail = f'{check}: "{found.group(1)}"' if found else check
    unhinged, _ = _clamp_tone_for_framework_mode(unhinged_level, profanity_level)
    pool = _BLOCKED_QUIPS_UNHINGED if unhinged >= _UNHINGED_QUIP_LEVEL else _BLOCKED_QUIPS
    return (f"{random.choice(pool)} "
            f"\U0001F6E1\uFE0F k9x Shield caught it ({detail}) and nothing reached the model.")


_ERROR_REPLY = "Something went wrong on our side and no reply was produced. Please try again."


def _public(info: dict) -> dict:
    """Runtime/health info as a visitor may see it: without the Provider
    Settings panel, the inference host's address stays server-side
    (it's an internal LAN address on the public deployment)."""
    if is_provider_settings_enabled():
        return info
    host = info.get("base_url") or ""
    out = {**info, "base_url": ""}
    if host and isinstance(out.get("error"), str):
        out["error"] = out["error"].replace(host, "the model host")
    return out


def _runtime() -> dict:
    return _public(get_chat_runtime_info())


@app.on_event("startup")
async def startup_event():
    run_chat_startup_check()

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Cache-busting for /static: every template references assets through
# asset("js/app.js") -> "/static/js/app.js?v=<content hash>". The hash
# changes whenever the file's bytes change, so a deploy is picked up by
# every browser with no manual version bumps (a stale cached app.js once
# left the Job Queue panel stuck on "Loading..." after a deploy).
_ASSET_HASHES: dict = {}


def asset(path: str) -> str:
    digest = _ASSET_HASHES.get(path)
    if digest is None:
        import hashlib
        with open(os.path.join(BASE_DIR, "static", path), "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()[:10]
        _ASSET_HASHES[path] = digest
    return f"/static/{path}?v={digest}"


templates.env.globals["asset"] = asset


@app.middleware("http")
async def _no_cache_html(request: Request, call_next):
    """HTML pages are never cached, so a browser always gets the current
    asset hashes; the hashed assets themselves can be cached freely."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    project_id: str | None = None
    # Two independent 0-4 dials, purely style/register for this local demo
    # tool -- see chat_agent.py's UNHINGED_INSTRUCTIONS/PROFANITY_INSTRUCTIONS.
    # Never sent to the model as anything but a style instruction; doesn't
    # change what's retrieved or what governance/guardrails run.
    unhinged_level: int = 0
    profanity_level: int = 0
    length_level: int = 1


class ProjectRequest(BaseModel):
    name: str
    instructions: str = ""


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    instructions: str | None = None


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "display_name": os.environ.get("OLLAMA_DISPLAY_NAME", ""),
    })


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    # No password, no rejection path -- see auth.py's module docstring for
    # why. sanitize_username() never rejects either; a blank/blocked name
    # just becomes a generated codename.
    username = sanitize_username(form.get("username") or "")
    request.session["logged_in"] = True
    request.session["visitor_id"] = str(uuid.uuid4())
    request.session["username"] = username
    return RedirectResponse(url="/app", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/welcome")


class SettingsRequest(BaseModel):
    provider: str = "ollama"
    base_url: str = ""
    model: str
    api_key: str = ""


def _window_label(seconds: int) -> str:
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "hour" if hours == 1 else f"{hours} hours"
    return f"{max(1, seconds // 60)} minutes"


@app.get("/", response_class=HTMLResponse)
def splash(request: Request):
    """Public: the full-screen splash, one Enter button -> /welcome."""
    return templates.TemplateResponse("splash.html", {"request": request, "version": get_k9chat_version()})


@app.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request):
    """Public landing page. Limits and Guardian state are read from config
    at render time, so the page can't drift from what the app enforces."""
    cfg = load_config()
    visitor = (cfg.get("rate_limit", {}) or {}).get("visitor", []) or []
    short = visitor[0] if visitor else {"max": "?", "window_seconds": 600}
    daily = visitor[1] if len(visitor) > 1 else {"max": "?"}
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "version": get_k9chat_version(),
        "model": get_chat_runtime_info()["model"],
        "limit_short": short["max"],
        "limit_short_window": _window_label(int(short["window_seconds"])),
        "limit_daily": daily["max"],
        "guardian_chat": is_guardian_enabled(),
    })


@app.get("/app", response_class=HTMLResponse)
def home(request: Request):
    runtime = _runtime()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "provider": runtime["provider"],
            "base_url": runtime["base_url"],
            "model": runtime["model"],
            "display_name": runtime["display_name"],
            "selectable_models": get_selectable_models(),
            "provider_settings_enabled": is_provider_settings_enabled(),
            "version": get_k9chat_version(),
        },
    )


@app.get("/chat/queue-status")
def chat_queue_status(request: Request):
    """Polled every 4s by each open tab: the Job Queue panel (see
    queue_control.py) and the presence heartbeat behind the online count."""
    owner = current_owner_id(request)
    status = queue_control.status(owner)
    status["online"] = queue_control.touch_presence(owner)
    return JSONResponse(status)


@app.post("/chat")
def chat(payload: ChatRequest, request: Request):
    message = payload.message.strip()
    if not message:
        return JSONResponse({"reply": ""})

    # Before the FAQ shortcut and the queue -- a refused message costs
    # nothing. 200 + reply, not 429: the chat UI renders `reply` as the
    # assistant's bubble, which is exactly where the visitor should read it.
    refusal = _RATE_LIMITER.check(request, current_owner_id(request))
    if refusal:
        return JSONResponse({"reply": refusal, "rate_limited": True, "model": None})

    # Checked before acquiring a QueueSlot -- a shortcut match never
    # touches Ollama/the GPU at all (CPU-only retrieval + reranker), so it
    # shouldn't have to wait behind other requests using the model.
    shortcut_start = time.monotonic()
    faq_match = check_faq_shortcut(message, session_id=payload.session_id)
    if faq_match:
        runtime = _runtime()
        return JSONResponse({
            "reply": faq_match["answer"],
            "elapsed_ms": round((time.monotonic() - shortcut_start) * 1000),
            "model": None,
            "provider": runtime["provider"],
            "base_url": runtime["base_url"],
            "faq_match": {"score": round(faq_match["score"], 2), "source": faq_match["source"]},
        })

    prior_reply = get_last_assistant_reply(payload.session_id)

    start = time.monotonic()
    try:
        with QueueSlot(current_owner_id(request)):
            result = send_message(
                message, session_id=payload.session_id, project_id=payload.project_id,
                unhinged_level=payload.unhinged_level, profanity_level=payload.profanity_level,
                length_level=payload.length_level,
            )
    except QueueBusy as exc:
        return JSONResponse({"reply": str(exc), "busy": True, "model": None})
    except PermissionError as exc:
        log.warning("[chat] Shield blocked a message: %s", exc)
        return JSONResponse({"reply": _blocked_reply(exc, payload.unhinged_level, payload.profanity_level),
                             "blocked": True, "model": None})
    elapsed_ms = round((time.monotonic() - start) * 1000)
    reply = result.get("text", "")
    blocked = bool(result.get("blocked"))
    runtime = _runtime()
    response = {
        "reply": reply,
        "elapsed_ms": elapsed_ms,
        "model": runtime["model"],
        "provider": runtime["provider"],
        "base_url": runtime["base_url"],
    }
    if blocked:
        response["blocked"] = True
    else:
        # Skip eval/learn on a Guardian refusal -- there's nothing to
        # judge or learn from in a canned "I can't help with that"
        # response, and both would otherwise burn an extra LLM call on it.
        eval_result = evaluate_response(message, reply)
        if eval_result:
            response["evaluation"] = eval_result
        learned = learn_from_correction(prior_reply, message, session_id=payload.session_id)
        if learned:
            response["learned_correction"] = learned
    return JSONResponse(response)


@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request):
    """SSE endpoint — used when chat.stream: true in config.yaml."""
    message = payload.message.strip()
    # Counted here, not inside the generator, so it runs once per request
    # before any streaming starts (same placement reasoning as /chat).
    refusal = _RATE_LIMITER.check(request, current_owner_id(request)) if message else None
    session_id = payload.session_id
    project_id = payload.project_id
    owner = current_owner_id(request)
    unhinged_level = payload.unhinged_level
    profanity_level = payload.profanity_level
    length_level = payload.length_level

    async def event_generator():
        if not message:
            yield f"data: {json.dumps({'done': True})}\n\n"
            return
        if refusal:
            yield f"data: {json.dumps({'chunk': refusal})}\n\n"
            yield f"data: {json.dumps({'done': True, 'rate_limited': True, 'model': None})}\n\n"
            return

        # Same as /chat: checked before touching QueueSlot, since a
        # shortcut match is CPU-only (retrieval + reranker) and never
        # needs the GPU/Ollama queue. run_in_executor because the
        # reranker's inference is a real (if small) blocking CPU call --
        # same offload pattern as evaluate_response()/learn_from_correction()
        # below.
        shortcut_start = time.monotonic()
        faq_match = await asyncio.get_event_loop().run_in_executor(
            None, check_faq_shortcut, message, session_id
        )
        if faq_match:
            yield f"data: {json.dumps({'chunk': faq_match['answer']})}\n\n"
            runtime = _runtime()
            done_payload = {
                "done": True,
                "elapsed_ms": round((time.monotonic() - shortcut_start) * 1000),
                "model": None,
                "provider": runtime["provider"],
                "base_url": runtime["base_url"],
                "faq_match": {"score": round(faq_match["score"], 2), "source": faq_match["source"]},
            }
            yield f"data: {json.dumps(done_payload)}\n\n"
            return

        prior_reply = get_last_assistant_reply(session_id)

        slot = QueueSlot(owner)
        try:
            # Live position while waiting (only when it changes); a full
            # line, a second job from the same visitor, or a timeout ends
            # here as a normal reply.
            async for position in slot.wait():
                if position > 0:
                    yield f"data: {json.dumps({'queued': True, 'position': position})}\n\n"
        except QueueBusy as exc:
            yield f"data: {json.dumps({'chunk': str(exc)})}\n\n"
            yield f"data: {json.dumps({'done': True, 'busy': True, 'model': None})}\n\n"
            return
        try:
            start = time.monotonic()
            full_text = ""
            async for chunk in send_message_stream(
                message, session_id=session_id, project_id=project_id,
                unhinged_level=unhinged_level, profanity_level=profanity_level,
                length_level=length_level,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except PermissionError as exc:
            log.warning("[chat/stream] Shield blocked a message: %s", exc)
            yield f"data: {json.dumps({'chunk': _blocked_reply(exc, unhinged_level, profanity_level)})}\n\n"
            yield f"data: {json.dumps({'done': True, 'blocked': True, 'model': None})}\n\n"
            return
        except Exception:
            # Top of the stack: log it in full, and end the stream with a
            # reply so the visitor isn't left waiting on a dead connection.
            log.exception("[chat/stream] generation failed")
            yield f"data: {json.dumps({'chunk': _ERROR_REPLY})}\n\n"
            yield f"data: {json.dumps({'done': True, 'error': True, 'model': None})}\n\n"
            return
        finally:
            slot.release()   # also on a closed tab (generator cancelled mid-stream)
        elapsed_ms = round((time.monotonic() - start) * 1000)
        runtime = _runtime()
        done_payload = {
            "done": True,
            "elapsed_ms": elapsed_ms,
            "model": runtime["model"],
            "provider": runtime["provider"],
            "base_url": runtime["base_url"],
        }
        eval_result = await asyncio.get_event_loop().run_in_executor(
            None, evaluate_response, message, full_text
        )
        if eval_result:
            done_payload["evaluation"] = eval_result
        learned = await asyncio.get_event_loop().run_in_executor(
            None, learn_from_correction, prior_reply, message, session_id
        )
        if learned:
            done_payload["learned_correction"] = learned
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/chat/config")
def chat_config():
    return JSONResponse({"stream": is_streaming_enabled()})


@app.post("/chat/stream/toggle")
def stream_toggle():
    enabled = toggle_streaming()
    return JSONResponse({"stream": enabled})


@app.get("/chat/evaluation")
def evaluation_status():
    return JSONResponse({"evaluation_enabled": is_evaluation_enabled()})


@app.post("/chat/evaluation/toggle")
def evaluation_toggle():
    enabled = toggle_evaluation()
    return JSONResponse({"evaluation_enabled": enabled})


@app.get("/chat/learning")
def learning_status():
    # Read-only, no /toggle counterpart on purpose -- see the badge's
    # tooltip in index.html for why.
    return JSONResponse({"learning_enabled": is_correction_learning_enabled()})


@app.get("/chat/faq-shortcut")
def faq_shortcut_status():
    return JSONResponse({"faq_shortcut_enabled": is_faq_shortcut_enabled(),
                         "framework_mode": not is_internet_search_enabled()})


@app.post("/chat/faq-shortcut/toggle")
def faq_shortcut_toggle():
    enabled = toggle_faq_shortcut()
    return JSONResponse({"faq_shortcut_enabled": enabled,
                         "framework_mode": not is_internet_search_enabled()})


@app.get("/chat/guardian")
def guardian_status():
    # Read-only, no /toggle counterpart on purpose.
    return JSONResponse({"guardian_enabled": is_guardian_enabled()})


@app.get("/chat/internet-search")
def internet_search_status():
    return JSONResponse({
        "internet_search_enabled": is_internet_search_enabled(),
        "framework_mode_locked": is_framework_mode_locked(),
    })


@app.post("/chat/internet-search/toggle")
def internet_search_toggle(request: Request):
    enabled = toggle_internet_search(request.session)
    return JSONResponse({
        "internet_search_enabled": enabled,
        "framework_mode_locked": is_framework_mode_locked(),
    })


@app.delete("/chat/session/{session_id}")
def delete_session(session_id: str):
    clear_session(session_id)
    return JSONResponse({"cleared": session_id})


class TruncateRequest(BaseModel):
    keep_count: int


@app.post("/chat/session/{session_id}/truncate")
def truncate_session_route(session_id: str, payload: TruncateRequest):
    """Server-side half of edit-and-resubmit -- drops the model's own
    memory of every turn from keep_count onward, not just what's visible
    in the browser. See ChatAgent.truncate_history()."""
    truncate_session(session_id, payload.keep_count)
    return JSONResponse({"session_id": session_id, "keep_count": payload.keep_count})


@app.get("/health")
def health():
    status = _public(get_health_status())
    return JSONResponse(status, status_code=200 if status["ok"] else 503)


@app.get("/chat/runtime")
def runtime():
    return JSONResponse(_runtime())


@app.get("/chat/models")
def models(provider: str = "ollama", base_url: str = "", api_key: str = ""):
    # Lists every model a visitor-named host has pulled (and makes the
    # server call that host): Provider Settings panel only.
    if not is_provider_settings_enabled():
        raise HTTPException(status_code=403, detail="Provider settings are disabled on this deployment.")
    try:
        return JSONResponse({"models": list_models_for(provider, base_url, api_key)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/chat/settings")
def settings(payload: SettingsRequest):
    """Model switching is a heavier, different cost than a normal chat
    message -- it loads a fresh multi-GB model into VRAM (apply_settings()'s
    warm-up call is a real generation). Two people casually flipping
    between models, zero malice, would still mean real repeated GPU
    reload cost -- guarded two ways: a cooldown between switches (global,
    since the cost is per-switch not per-visitor) and the same
    concurrency/thermal QueueSlot every chat message already goes
    through."""
    provider, base_url, api_key = payload.provider, payload.base_url, payload.api_key
    if not is_provider_settings_enabled():
        # Header dropdown only: a model from the .env allowlist, on the
        # provider/host already configured -- whatever the browser sent
        # for those is ignored.
        if payload.model not in get_selectable_models():
            raise HTTPException(status_code=403, detail="That model isn't available on this deployment.")
        current = get_chat_runtime_info()
        provider, base_url, api_key = current["provider"], current["base_url"], ""
    # Global state every visitor's page reads back: only well-formed values.
    payload = payload.model_copy(update={"provider": provider, "base_url": base_url, "api_key": api_key})
    if payload.provider not in ("ollama", "openai-compatible"):
        raise HTTPException(status_code=400, detail="Unknown provider.")
    if not re.fullmatch(r"[\w.:/@+-]{1,128}", payload.model or ""):
        raise HTTPException(status_code=400, detail="Invalid model name.")
    if not re.fullmatch(r"https?://[\w.-]+(:\d{1,5})?(/[\w./-]*)?", payload.base_url or ""):
        raise HTTPException(status_code=400, detail="Invalid base URL.")
    allowed, retry_after = queue_control.check_switch_cooldown()
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Model was switched too recently -- try again in {retry_after}s.",
        )
    try:
        with QueueSlot():
            status = apply_settings(payload.provider, payload.base_url, payload.model, payload.api_key)
    except QueueBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    return JSONResponse(_public(status))


def _require_owned_project(project_id: str, owner_id: str | None) -> dict:
    """404s (not a silent empty result) if the project doesn't exist OR
    belongs to a different visitor -- same response either way so a
    guessed project_id can't be used to probe which IDs are real."""
    project = get_project(project_id, owner_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/projects")
def projects_create(payload: ProjectRequest, request: Request):
    try:
        project = create_project(payload.name, instructions=payload.instructions, owner_id=current_owner_id(request))
    except ScreenRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse(project)


@app.get("/projects")
def projects_list(request: Request):
    return JSONResponse({"projects": list_projects(current_owner_id(request))})


@app.get("/projects/{project_id}")
def projects_get(project_id: str, request: Request):
    return JSONResponse(_require_owned_project(project_id, current_owner_id(request)))


@app.put("/projects/{project_id}")
def projects_update(project_id: str, payload: ProjectUpdateRequest, request: Request):
    _require_owned_project(project_id, current_owner_id(request))
    try:
        return JSONResponse(update_project(project_id, name=payload.name, instructions=payload.instructions))
    except ScreenRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.delete("/projects/{project_id}")
def projects_delete(project_id: str, request: Request):
    _require_owned_project(project_id, current_owner_id(request))
    try:
        return JSONResponse(delete_project(project_id))
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.post("/projects/{project_id}/files")
async def projects_add_file(project_id: str, request: Request, file: UploadFile = File(...)):
    owner = current_owner_id(request)
    _require_owned_project(project_id, owner)
    # Same per-visitor/per-IP budget as chat: screening + embedding a file
    # is GPU work too.
    refusal = _RATE_LIMITER.check(request, owner)
    if refusal:
        raise HTTPException(status_code=429, detail=refusal)
    # Read at most one byte past the cap -- a huge upload is refused without
    # pulling all of it into memory.
    cap = int(load_config().get("persist_screening", {}).get("max_chars", 100_000)) * 4
    raw = await file.read(cap + 1)
    if len(raw) > cap:
        raise HTTPException(status_code=413, detail="File is too large.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Only UTF-8 text files are supported")
    filename = (file.filename or "upload.txt")[:200]

    def _store():
        # Guardian windows are GPU calls: take a queue slot like a chat
        # message does, off the event loop.
        with QueueSlot(owner):
            return add_project_file(project_id, filename, text)

    try:
        result = await asyncio.to_thread(_store)
    except QueueBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ScreenRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    return JSONResponse(result)


@app.delete("/projects/{project_id}/files/{file_id}")
def projects_remove_file(project_id: str, file_id: str, request: Request):
    _require_owned_project(project_id, current_owner_id(request))
    try:
        return JSONResponse(remove_project_file(project_id, file_id))
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")