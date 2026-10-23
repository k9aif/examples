# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework -- k9chat public API, v1

"""
"Ask the framework" API: one question in, one grounded answer out, for
other applications (K9X Studio's Help) and, later, a question bar on
k9x.ai. Separate from /chat on purpose: /chat is tied to the browser
login cookie and accepts every UI switch (projects, persona dials,
internet, settings); this API accepts a question and five options.

  POST /api/v1/ask           question -> answer (SSE stream by default)
  GET  /api/v1/ask/options   the defaults, and which ones this caller may change
  GET  /api/v1/health        200 up / 503 down, for the k9x dashboard

Off unless K9CHAT_API_ENABLED=true. With K9CHAT_API_SIMULATED=true (the
default) every answer is canned and marked "simulated": true, so callers
can be built against the contract before the GPU is involved.

Two kinds of caller:
  - keyed (Studio): Authorization: Bearer <key>, checked by the framework's
    ApiKeyAuthenticator (k9_security/zero_trust/identity.py). Keys live
    only in .env. A caller may also be pinned to source addresses
    (K9_KEY_<NAME>_FROM): then the key works only from those addresses and
    only on the internal path, never through the Cloudflare tunnel.
  - anonymous (a browser on k9x.ai): an allowed Origin plus a Cloudflare
    Turnstile token (X-Turnstile-Token), verified server-side including
    the hostname it was solved on. Locked to the safe defaults.

Every request is turned away as cheaply as possible, in this order:
size cap -> who is calling -> body shape -> options allowed -> budgets
(per caller, per IP, and one daily budget for all anonymous callers) ->
FAQ shortcut (CPU) -> GPU queue (full = 503 busy at once) -> model.

The Authorization header and Turnstile token are never logged; logs name
the caller ("studio", "anonymous").
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from k9_aif_abb.k9_security.vulnerability.checks.request_frequency_check import RequestFrequencyCheck
from k9_aif_abb.k9_security.zero_trust.identity import ApiKeyAuthenticator

from k9chat.rate_limit import client_ip

log = logging.getLogger("k9chat.api")

OPTION_NAMES = ("framework", "faq", "internet", "stream", "eval")
DEFAULT_OPTIONS = {"framework": True, "faq": True, "internet": False, "stream": True, "eval": False}
# Options a caller may change only with the ask_options role. faq and
# stream change nothing about safety or cost, so anyone may set them.
GUARDED_OPTIONS = ("framework", "internet", "eval")
BLOCKED_ANSWER = "k9x Shield stopped this question before it reached the model."
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes")


# ── request / response shapes ────────────────────────────────────────────────
class AskOptions(BaseModel):
    framework: Optional[bool] = None
    faq: Optional[bool] = None
    internet: Optional[bool] = None
    stream: Optional[bool] = None
    eval: Optional[bool] = None


class AskRequest(BaseModel):
    model_config = {"extra": "forbid"}          # an unknown field is a mistake, not something to ignore

    question: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    context: Dict[str, str] = Field(default_factory=dict)
    options: AskOptions = Field(default_factory=AskOptions)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


class Caller:
    def __init__(self, name: str, keyed: bool, roles: List[str], ip: str):
        self.name, self.keyed, self.roles, self.ip = name, keyed, roles, ip

    @property
    def may_change_guarded(self) -> bool:
        return self.keyed and "ask_options" in self.roles


# ── the API ──────────────────────────────────────────────────────────────────
class AskApi:
    """Holds the API's config, budgets and authenticator; build_router()
    turns it into FastAPI routes. Config: config.yaml's ``api`` section."""

    def __init__(self, config: Dict[str, Any], environ: Optional[Dict[str, str]] = None,
                 framework_locked=lambda: False):
        self.env = os.environ if environ is None else environ
        self.framework_locked = framework_locked     # K9CHAT_FRAMEWORK_MODE_LOCKED wins over any caller
        self._ns = uuid.uuid4().hex[:8]              # budget counters never shared with the UI's limits
        cfg = (config or {}).get("api", {}) or {}
        self.enabled = _flag(cfg.get("enabled"))
        self.simulated = _flag(cfg.get("simulated"), True)
        self.max_body_bytes = int(cfg.get("max_body_bytes", 8192))
        self.context_max_chars = int(cfg.get("context_max_chars", 500))

        callers = cfg.get("callers", {}) or {}
        self.callers = callers
        self.authenticator = ApiKeyAuthenticator(callers, environ=self.env)
        self.allowed_from: Dict[str, List[str]] = {}
        for name, spec in callers.items():
            raw = self.env.get(spec.get("from_env", ""), "") if spec.get("from_env") else ""
            self.allowed_from[name] = [a.strip() for a in raw.split(",") if a.strip()]
        self.caller_budgets = {name: self._windows(f"key:{name}", spec.get("budget", []))
                               for name, spec in callers.items()}

        anon = cfg.get("anonymous", {}) or {}
        self.anon_enabled = _flag(anon.get("enabled"))
        self.allowed_origins = [o.rstrip("/") for o in anon.get("allowed_origins", []) or []]
        self.turnstile_secret = str(anon.get("turnstile_secret") or "")
        self.turnstile_hostnames = list(anon.get("turnstile_hostnames", []) or [])
        self.anon_ip_budget = self._windows("anon-ip", anon.get("per_ip", []))
        self.anon_global_budget = self._windows("anon-all", anon.get("global", []))
        if self.anon_enabled and not self.turnstile_secret and not self.simulated:
            log.warning("[api] anonymous access is on but no Turnstile secret is set: anonymous calls are refused")
        self._health_cache: Dict[str, Any] = {"at": 0.0, "body": None}

    # budgets reuse the framework's Shield check (OWASP LLM10), one per window
    def _windows(self, scope: str, windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for w in windows or []:
            limit, seconds = int(w["max"]), int(w["window_seconds"])
            out.append({"scope": f"{self._ns}:{scope}", "max": limit, "seconds": seconds,
                        "check": RequestFrequencyCheck({"max_requests_per_window": limit,
                                                        "rate_limit_window_seconds": seconds})})
        return out

    @staticmethod
    def _spend(windows: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
        """Counts one request against every window; returns the longest window over budget, else None."""
        over = [w for w in windows
                if w["check"].check({"session_id": f"k9chat-api:{w['scope']}:{key}:{w['seconds']}"}).blocked]
        return max(over, key=lambda w: w["seconds"]) if over else None

    # ── who is calling ───────────────────────────────────────────────────
    def identify(self, request: Request) -> Caller:
        ip, _ = client_ip(request)
        auth = request.headers.get("authorization")
        if auth is not None:
            scheme, _, token = auth.partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                raise self._unauthorized("Use Authorization: Bearer <key>.")
            identity = self.authenticator.authenticate({"api_key": token.strip()})
            if identity is None:
                log.warning("[api] refused: unknown key from %s", ip)
                raise self._unauthorized("Unknown key.")
            name = identity.principal_id
            pinned = self.allowed_from.get(name) or []
            if pinned:
                peer = request.client.host if request.client else ""
                via_tunnel = bool(request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for"))
                if via_tunnel or peer not in pinned:
                    # Same answer as a wrong key: a stolen key gives no hint that it is right.
                    log.warning("[api] refused: key for '%s' used from %s (tunnel=%s)", name, peer, via_tunnel)
                    raise self._unauthorized("Unknown key.")
            if "ask" not in identity.roles:
                raise ApiError(403, "forbidden", "This key may not use /api/v1/ask.")
            return Caller(name, True, list(identity.roles), ip)

        if not self.anon_enabled:
            raise self._unauthorized("This API needs Authorization: Bearer <key>.")
        origin = (request.headers.get("origin") or "").rstrip("/")
        if origin not in self.allowed_origins:
            raise ApiError(403, "origin_not_allowed", "Anonymous calls are only accepted from the K9X site.")
        return Caller("anonymous", False, [], ip)

    @staticmethod
    def _unauthorized(message: str) -> ApiError:
        return ApiError(401, "unauthorized", message, {"WWW-Authenticate": 'Bearer realm="k9chat"'})

    async def check_turnstile(self, request: Request, caller: Caller) -> None:
        if caller.keyed:
            return
        token = request.headers.get("x-turnstile-token", "")
        if not token:
            raise ApiError(403, "challenge_required", "Missing X-Turnstile-Token.")
        if not self.turnstile_secret:
            if self.simulated:
                return                                   # simulated mode: any token passes
            raise ApiError(403, "challenge_failed", "Anonymous access is not configured.")
        ok = await asyncio.to_thread(self._verify_turnstile, token, caller.ip)
        if not ok:
            raise ApiError(403, "challenge_failed", "The bot check did not pass.")

    def _verify_turnstile(self, token: str, ip: str) -> bool:
        import requests
        try:
            r = requests.post(TURNSTILE_VERIFY_URL, timeout=5,
                              data={"secret": self.turnstile_secret, "response": token, "remoteip": ip}).json()
        except Exception as exc:
            log.warning("[api] Turnstile verify failed: %s", exc)
            return False
        # A token solved on someone else's site is not ours to honour.
        return bool(r.get("success")) and (not self.turnstile_hostnames
                                           or r.get("hostname") in self.turnstile_hostnames)

    # ── options ──────────────────────────────────────────────────────────
    def resolve_options(self, asked: AskOptions, caller: Caller) -> Dict[str, bool]:
        """Defaults, plus what the caller asked for and may change. Framework
        and internet are one switch in K9Chat (internet = not framework)."""
        given = {k: v for k, v in asked.model_dump().items() if v is not None}
        if "framework" in given and "internet" in given and given["framework"] == given["internet"]:
            raise ApiError(400, "invalid", "framework and internet are one switch: internet = not framework.")
        if "internet" in given and "framework" not in given:
            given["framework"] = not given["internet"]
        given.pop("internet", None)
        if not caller.may_change_guarded:
            locked = [k for k in GUARDED_OPTIONS if k in given and given[k] != DEFAULT_OPTIONS[k]]
            if locked:
                raise ApiError(403, "option_not_allowed",
                               f"This caller may not change: {', '.join(locked)}.")
        opts = {**DEFAULT_OPTIONS, **given}
        if self.framework_locked():
            opts["framework"] = True
        opts["internet"] = not opts["framework"]
        if not opts["framework"]:
            opts["faq"] = False                          # FAQ answers are framework content
        return opts

    def options_view(self, caller: Optional[Caller]) -> Dict[str, Any]:
        may = caller.may_change_guarded if caller else False
        return {"defaults": DEFAULT_OPTIONS,
                "changeable": [k for k in OPTION_NAMES if may or k not in GUARDED_OPTIONS],
                "caller": caller.name if caller else "anonymous",
                "simulated": self.simulated}

    # ── budgets ──────────────────────────────────────────────────────────
    def spend_budget(self, caller: Caller) -> None:
        if caller.keyed:
            over = self._spend(self.caller_budgets.get(caller.name, []), caller.name)
        else:
            over = self._spend(self.anon_ip_budget, caller.ip) or self._spend(self.anon_global_budget, "all")
        if over:
            log.warning("[api] budget: caller=%s ip=%s over %d per %ss", caller.name, caller.ip,
                        over["max"], over["seconds"])
            raise ApiError(429, "rate_limited", "Too many questions; please try again later.",
                           {"Retry-After": str(min(over["seconds"], 3600))})

    # ── health ───────────────────────────────────────────────────────────
    def health(self) -> tuple[int, Dict[str, Any]]:
        """Cached 15 s: the dashboard polls it, and a flood of health
        calls must not turn into a flood of model-host checks."""
        now = time.monotonic()
        if self._health_cache["body"] is None or now - self._health_cache["at"] > 15:
            from k9chat.chat import get_health_status, get_k9chat_version
            from k9chat import queue_control
            if self.simulated:
                model_ok, error = True, None
            else:
                h = get_health_status()
                model_ok, error = bool(h.get("ok")), ("model host unreachable" if not h.get("ok") else None)
            q = queue_control.status()
            body = {"status": "ok" if model_ok else "down", "api": "v1", "simulated": self.simulated,
                    "version": get_k9chat_version(), "model_host": "ok" if model_ok else "down",
                    "queue": {k: q[k] for k in ("active", "waiting", "max_concurrent", "max_queue")}}
            if error:
                body["error"] = error
            self._health_cache = {"at": now, "body": body}
        body = self._health_cache["body"]
        return (200 if body["status"] == "ok" else 503), body


# ── answering ────────────────────────────────────────────────────────────────
def _source_entries(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for hit in hits:
        label = (hit.get("source") or "").split(":")[0]
        if not label or label in seen:
            continue
        seen.add(label)
        entry: Dict[str, Any] = {"source": label}
        if label.startswith("k9x-videos/") and not label.endswith("/channel"):
            entry["url"] = f"https://www.youtube.com/watch?v={label.split('/', 1)[1]}"
        out.append(entry)
    return out


def _question_with_context(question: str, context: Dict[str, str], max_chars: int) -> str:
    """Page context ("on Studio's canvas, HIL Orchestrator selected") goes to
    the model as part of the question, so Shield screens it like the question."""
    if not context:
        return question
    lines = "; ".join(f"{k}: {v}" for k, v in context.items())[:max_chars]
    return f"{question}\n\n(Asked from: {lines})"


def _simulated_answer(question: str) -> Dict[str, Any]:
    return {"answer": f"[simulated] This is where K9Chat's answer to \"{question[:120]}\" will appear. "
                      "Set K9CHAT_API_SIMULATED=false for real answers.",
            "sources": [{"source": "k9x-videos/uXv8gF3xiXc", "url": "https://www.youtube.com/watch?v=uXv8gF3xiXc"}],
            "answered_by": "simulated", "model": None}


def _error_body(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def build_router(api: AskApi) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def cors(request: Request, response: Response) -> Response:
        origin = (request.headers.get("origin") or "").rstrip("/")
        if api.anon_enabled and origin in api.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response

    def fail(request: Request, exc: ApiError) -> Response:
        return cors(request, JSONResponse(_error_body(exc.code, exc.message), status_code=exc.status,
                                          headers=exc.headers))

    @router.options("/ask")
    async def ask_preflight(request: Request):
        resp = Response(status_code=204)
        if api.anon_enabled and (request.headers.get("origin") or "").rstrip("/") in api.allowed_origins:
            # Browsers never send a bearer key: Authorization is deliberately not allowed here.
            resp.headers["Access-Control-Allow-Methods"] = "POST"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Turnstile-Token"
            resp.headers["Access-Control-Max-Age"] = "600"
        return cors(request, resp)

    @router.get("/ask/options")
    async def ask_options(request: Request):
        try:
            caller = api.identify(request) if request.headers.get("authorization") else None
        except ApiError as exc:
            return fail(request, exc)
        return cors(request, JSONResponse(api.options_view(caller)))

    @router.get("/health")
    async def health():
        status, body = await asyncio.to_thread(api.health)
        return JSONResponse(body, status_code=status)

    @router.post("/ask")
    async def ask(request: Request):
        started = time.monotonic()
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > api.max_body_bytes:
                raise ApiError(413, "too_large", f"Request body is limited to {api.max_body_bytes} bytes.")
            caller = api.identify(request)
            await api.check_turnstile(request, caller)
            raw = await request.body()
            if len(raw) > api.max_body_bytes:
                raise ApiError(413, "too_large", f"Request body is limited to {api.max_body_bytes} bytes.")
            try:
                body = AskRequest.model_validate_json(raw or b"{}")
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first.get("loc", ())) or "body"
                raise ApiError(400, "invalid", f"{where}: {first.get('msg')}")
            question = body.question.strip()
            if not question:
                raise ApiError(400, "invalid", "question: must not be blank")
            opts = api.resolve_options(body.options, caller)
            api.spend_budget(caller)
        except ApiError as exc:
            return fail(request, exc)

        session_id = body.session_id or uuid.uuid4().hex
        # Namespaced so an API caller can never read or extend a browser visitor's conversation.
        history_id = f"api-{caller.name}-{session_id}"
        owner = f"api:{caller.name}:{session_id}" if caller.keyed else f"api:anonymous:{caller.ip}"
        prompt = _question_with_context(question, body.context, api.context_max_chars)
        log.info("[api] ask caller=%s stream=%s framework=%s", caller.name, opts["stream"], opts["framework"])

        def finish(answer: Dict[str, Any], eval_used: bool) -> Dict[str, Any]:
            applied = {**opts, "eval": eval_used}
            return {**answer, "session_id": session_id, "options_applied": applied,
                    "elapsed_ms": round((time.monotonic() - started) * 1000), "simulated": api.simulated}

        if opts["stream"]:
            return cors(request, StreamingResponse(
                _stream(api, prompt, question, history_id, owner, opts, finish),
                media_type="text/event-stream", headers={"Cache-Control": "no-cache"}))
        try:
            answer, eval_used = await _answer(api, prompt, question, history_id, owner, opts)
        except ApiError as exc:
            return fail(request, exc)
        return cors(request, JSONResponse(finish(answer, eval_used)))

    return router


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _answer(api: AskApi, prompt: str, question: str, history_id: str, owner: str,
                  opts: Dict[str, bool]) -> tuple[Dict[str, Any], bool]:
    """The whole answer at once (stream: false)."""
    if api.simulated:
        return _simulated_answer(question), False
    from k9chat import chat
    from k9chat.queue_control import QueueBusy, QueueSlot

    token = chat.set_session_internet(opts["internet"])
    try:
        if opts["faq"]:
            match = await asyncio.to_thread(chat.check_faq_shortcut, prompt, history_id)
            if match:
                return {"answer": match["answer"], "sources": [{"source": match.get("source", "faq")}],
                        "answered_by": "faq", "model": None}, False
        hits: List[Dict[str, Any]] = []
        try:
            async with QueueSlot(owner):
                result = await asyncio.to_thread(lambda: chat.send_message(prompt, session_id=history_id, sources_out=hits))
        except QueueBusy as exc:
            raise ApiError(503, "busy", str(exc), {"Retry-After": "30"})
        except PermissionError as exc:
            log.warning("[api] Shield blocked a question: %s", exc)
            raise ApiError(422, "blocked", BLOCKED_ANSWER)
        if result.get("blocked"):
            raise ApiError(422, "blocked", BLOCKED_ANSWER)
        text = result.get("text", "")
        eval_used = False
        if opts["eval"]:
            evaluation = await asyncio.to_thread(chat.evaluate_response, question, text)
            eval_used = evaluation is not None              # None: evaluation is off in this deployment
        model = chat.get_chat_runtime_info().get("model")
        return {"answer": text, "sources": _source_entries(hits), "answered_by": "model", "model": model}, eval_used
    finally:
        _reset_mode(chat, token)


def _reset_mode(chat, token) -> None:
    try:
        chat.reset_session_internet(token)
    except ValueError:              # generator closed from another context (client went away): nothing to undo
        pass


async def _stream(api: AskApi, prompt: str, question: str, history_id: str, owner: str,
                  opts: Dict[str, bool], finish):
    """SSE: `queued` (position, while waiting), `token` (text), then `done`
    (the same JSON as stream: false), or `error` ({code, message})."""
    if api.simulated:
        answer = _simulated_answer(question)
        for word in answer["answer"].split(" "):
            yield _sse("token", {"text": word + " "})
        yield _sse("done", finish(answer, False))
        return
    from k9chat import chat
    from k9chat.queue_control import QueueBusy, QueueSlot

    token = chat.set_session_internet(opts["internet"])     # set here: the generator runs after the handler returns
    slot = None
    try:
        if opts["faq"]:
            match = await asyncio.to_thread(chat.check_faq_shortcut, prompt, history_id)
            if match:
                yield _sse("token", {"text": match["answer"]})
                yield _sse("done", finish({"answer": match["answer"],
                                           "sources": [{"source": match.get("source", "faq")}],
                                           "answered_by": "faq", "model": None}, False))
                return
        slot = QueueSlot(owner)
        try:
            async for position in slot.wait():
                if position > 0:
                    yield _sse("queued", {"position": position})
        except QueueBusy as exc:
            slot = None
            yield _sse("error", {"code": "busy", "message": str(exc)})
            return
        hits: List[Dict[str, Any]] = []
        parts: List[str] = []
        try:
            async for chunk in chat.send_message_stream(prompt, session_id=history_id, sources_out=hits):
                parts.append(chunk)
                yield _sse("token", {"text": chunk})
        except PermissionError as exc:
            log.warning("[api] Shield blocked a question: %s", exc)
            yield _sse("error", {"code": "blocked", "message": BLOCKED_ANSWER})
            return
        except Exception:
            log.exception("[api] generation failed")
            yield _sse("error", {"code": "error", "message": "No answer was produced. Please try again."})
            return
        finally:
            if slot is not None:
                slot.release()
                slot = None
        text = "".join(parts)
        eval_used = False
        if opts["eval"]:
            eval_used = (await asyncio.to_thread(chat.evaluate_response, question, text)) is not None
        model = chat.get_chat_runtime_info().get("model")
        yield _sse("done", finish({"answer": text, "sources": _source_entries(hits),
                                   "answered_by": "model", "model": model}, eval_used))
    finally:
        if slot is not None:
            slot.release()
        _reset_mode(chat, token)
