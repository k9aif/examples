# SPDX-License-Identifier: Apache-2.0
"""
One weather request, with the governance trace that came with it. Used by the CLI
(run_weather.py) and the web page (webui/app.py).

Isolation between visitors: nothing about a request is kept after it returns. Its trace events
are collected under its own random trace id and handed back only to that request; the demo
"poison" switch is a per-request context variable. The adapter, Shield and the router keep no
request content between calls (the router is asked with an empty prompt).
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any, AsyncIterator, Dict, List

from k9_aif_abb.k9_utils.trace_events import register_trace_callback

from . import tools

_LOCK = threading.Lock()
_EVENTS: Dict[str, List[Dict[str, Any]]] = {}
_LISTENERS: Dict[str, tuple] = {}            # trace id -> (event loop, asyncio.Queue): live streaming


def _collect(event: Dict[str, Any]) -> None:
    """Keep the event under its request's trace id; wake that request's stream, if any. Events can come
    from other threads (Guardian's call pool, tool threads), so the wake-up goes through the loop."""
    tid = event.get("trace_id")
    with _LOCK:
        if tid not in _EVENTS:
            return
        _EVENTS[tid].append(event)
        listener = _LISTENERS.get(tid)
    if listener:
        loop, queue = listener
        loop.call_soon_threadsafe(queue.put_nowait, None)


register_trace_callback(_collect)


def _secs(ms: Any) -> str:
    try:
        return f"{int(ms) / 1000:.1f} s"
    except (TypeError, ValueError):
        return "? s"


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _is_guardian(e: Dict[str, Any]) -> bool:
    return e.get("type") == "LLMCall" and str(e.get("task_type", "")).startswith("guardian")


def checks_from_events(events: List[Dict[str, Any]], question: str = "", running: bool = False) -> List[Dict[str, Any]]:
    """The run as its stages, in order, each with every call made inside it.

    A stage is {"box", "status", "step", "detail", "calls": [str]}: ``box`` is its short name in the
    flow, ``calls`` accounts for each check and model call under it, ``step``/``detail`` are the one-line
    form (CLI). Raw events arrive in the order the code emits them: Granite Guardian's calls (chained
    after Shield) before the event that names the check, a Zero Trust decision before the agent turn it
    allows, the Model Router's choice before the model call. So Guardian calls are held and attached to
    the next check, and so on. Nothing is dropped: a Guardian call that ends the run is its own stage."""
    stages: List[Dict[str, Any]] = []
    guardian: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    route: Dict[str, Any] = {}
    zero_trust: List[Dict[str, Any]] = []
    totals = {"g_calls": 0, "g_ms": 0, "m_calls": 0, "m_ms": 0, "points": 0}
    g_models: List[str] = []
    m_models: List[str] = []

    def add(box: str, status: str, what: str, calls: List[str]) -> None:
        stages.append({"box": box, "status": status, "calls": calls,
                       "step": box, "detail": f"{what}: " + " · ".join(calls) if calls else what})

    def checked(shield_ok: bool = True) -> tuple:
        calls = ["Shield ✓" if shield_ok else "Shield ✗ blocked"]
        status = "allowed" if shield_ok else "blocked"
        if guardian:
            ms = sum(int(g.get("latency_ms") or 0) for g in guardian)
            verdicts = {g.get("verdict") for g in guardian}
            n = f", {len(guardian)} calls" if len(guardian) > 1 else ""
            if "UNSAFE" in verdicts:
                calls.append(f"Guardian ✗ blocked ({_secs(ms)}{n})"); status = "blocked"
            elif "UNAVAILABLE" in verdicts:
                calls.append(f"Guardian unavailable ({_secs(ms)}{n})"); status = "blocked"
            else:
                calls.append(f"Guardian ✓ ({_secs(ms)}{n})")
        elif skipped:
            calls.append("Guardian not used here (by policy)")
        else:
            calls.append("Guardian ✓ (already checked, same text)")
        guardian.clear(); skipped.clear()
        totals["points"] += 1
        return calls, status

    if question:
        stages.append({"box": "Input", "status": "info", "calls": [question], "step": "Input", "detail": question})
    for e in events:
        t = e.get("type")
        if _is_guardian(e):
            guardian.append(e)
            if e.get("model") and e.get("model") not in g_models:
                g_models.append(e.get("model"))
            totals["g_calls"] += 1
            totals["g_ms"] += int(e.get("latency_ms") or 0)
        elif t == "GuardianSkipped":
            skipped.append(e)
        elif t == "ZeroTrust":
            if not any(st["box"] == "Zero Trust" for st in stages) and not zero_trust:
                ok = e.get("allowed")
                add("Zero Trust", "allowed" if ok else "blocked", "may this caller ask",
                    [f"Zero Trust {'ALLOW' if ok else 'DENY'}" + ("" if ok else f": {e.get('reason') or ''}")])
            else:
                zero_trust.append(e)
        elif t == "OpenAIRunCheck" and e.get("gate") == "ingress":
            calls, status = checked()
            add("Request check", status, "the request text", calls)
        elif t == "OpenAIAgentStart":
            zero_trust.clear()
            add(str(e.get("agent")), "allowed", f"may this caller reach {e.get('agent')}",
                [f"Zero Trust {e.get('zero_trust')}"])
        elif t == "LLMRoute":
            route = e
        elif t == "LLMCall":
            totals["m_calls"] += 1
            totals["m_ms"] += int(e.get("latency_ms") or 0)
            if e.get("model") and e.get("model") not in m_models:
                m_models.append(e.get("model"))
            calls = [str(e.get("model"))]
            if route:
                calls.append(f"via Model Router ({route.get('model_alias')})")
            tokens = f" · {e.get('tokens_in')} → {e.get('tokens_out')} tokens" if e.get("tokens_in") is not None else ""
            calls.append(f"{_secs(e.get('latency_ms'))}{tokens}")
            add("Model", "info", "the model thinks", calls)
            route = {}
        elif t == "OpenAIModelReply":
            if e.get("screened"):
                calls, status = checked()
                add("Reply check", status, f"what {e.get('agent')}'s model wrote", calls)
            else:
                guardian.clear(); skipped.clear()
                add("Reply check", "info", "a tool call only", ["no text to check (arguments checked next)"])
        elif t == "ToolCallScreen":
            calls, status = checked(bool(e.get("allowed")))
            if not e.get("allowed"):
                calls.append(f"refused: {e.get('reason')}")
            add(f"Tool call: {e.get('tool')}", status, "the arguments, before the tool runs", calls)
        elif t == "ToolResultScreen":
            calls, status = checked(bool(e.get("allowed")))
            if not e.get("allowed"):
                calls.append(f"withheld: {e.get('reason')}")
            add(f"Tool result: {e.get('tool')}", status, "what it returned, before the model reads it", calls)
        elif t == "OpenAIRunCheck" and e.get("gate") == "egress":
            calls, status = checked()
            add("Final answer", status, "what the caller receives", calls)
        elif t == "ShieldChain" and e.get("blocked_by"):
            guardian.clear(); skipped.clear()
            add("Blocked", "blocked", f"k9x Shield, {e.get('gate')}", [f"Shield ✗ {e.get('blocked_by')}"])
        elif t == "OpenAIHandoff":
            add("Handoff", "info", f"{e.get('agent')} → {e.get('to_agent')}", [f"→ {e.get('to_agent')}"])

    if running:                                      # the step in progress, while the run streams
        if route:
            stages.append({"box": "Model", "status": "running", "step": "Model", "detail": "thinking",
                           "calls": [str(route.get("model")), f"via Model Router ({route.get('model_alias')})",
                                     "thinking…"]})
        elif guardian:
            ms = sum(int(g.get("latency_ms") or 0) for g in guardian)
            stages.append({"box": "Checking", "status": "running", "step": "Checking", "detail": "checking",
                           "calls": ["Shield ✓", f"Guardian checking… ({len(guardian)} done, {_secs(ms)})"]})
        else:
            stages.append({"box": "Working", "status": "running", "step": "Working", "detail": "next step",
                           "calls": ["working…"]})
        return stages
    for z in zero_trust:                             # a decision with no agent turn after it: it refused
        if not z.get("allowed"):
            add("Blocked", "blocked", "Zero Trust", [f"Zero Trust DENY: {z.get('reason') or ''}"])
    if guardian:                                     # Guardian ended the run before a check was named
        calls, _ = checked()
        add("Blocked", "blocked", "Granite Guardian", calls[1:])
    if totals["points"]:
        stages.append({"box": "Totals", "status": "info", "calls": [], "step": "Totals",
                       "detail": f"{_n(totals['points'], 'point')} checked · Guardian ({', '.join(g_models) or 'not used'}) "
                                 f"{_n(totals['g_calls'], 'call')}, {_secs(totals['g_ms'])} · model ({', '.join(m_models) or 'none'}) "
                                 f"{_n(totals['m_calls'], 'call')}, {_secs(totals['m_ms'])}"})
    return stages


def _start(zip_or_text: str, role: str) -> tuple:
    tid = f"weather-{uuid.uuid4().hex[:12]}"
    question = f"What is the weather in zip code {zip_or_text}?"
    payload = {"message": question, "principal_id": f"demo-{role}", "roles": [role],
               "action_type": "weather.lookup", "trace_id": tid}
    with _LOCK:
        _EVENTS[tid] = []
    return tid, question, payload


async def _run(adapter, tid: str, question: str, payload: Dict[str, Any], role: str, poison: bool) -> Dict[str, Any]:
    token = tools.POISON_NEXT_LOOKUP.set({"armed": poison})   # this request only
    observed: Dict[str, Any] = {}
    seen_token = tools.OBSERVED.set(observed)
    try:
        result = await adapter.execute_async(payload)
        outcome, text = "answer", result["output_text"]
    except PermissionError as exc:
        outcome, text = "refused", str(exc)
    except Exception as exc:                       # reported to the caller, not hidden
        outcome, text = "error", f"{type(exc).__name__}: {exc}"
    finally:
        tools.POISON_NEXT_LOOKUP.reset(token)
        tools.OBSERVED.reset(seen_token)
        with _LOCK:
            events = _EVENTS.pop(tid, [])
            _LISTENERS.pop(tid, None)
    return {"question": question, "role": role, "poisoned": poison, "outcome": outcome, "text": text,
            "trace": checks_from_events(events, question),
            "sky": _sky(observed) if outcome == "answer" else "default"}


async def ask(adapter, zip_or_text: str, role: str, poison: bool = False) -> Dict[str, Any]:
    """Run one request. Returns question, outcome ("answer" | "refused" | "error"), text, trace."""
    tid, question, payload = _start(zip_or_text, role)
    return await _run(adapter, tid, question, payload, role, poison)


async def ask_stream(adapter, zip_or_text: str, role: str, poison: bool = False) -> AsyncIterator[Dict[str, Any]]:
    """The same request, streamed: {"type": "stages", "stages": [...]} each time a check or model call
    happens (the last stage is the one in progress), then {"type": "result", ...} once."""
    tid, question, payload = _start(zip_or_text, role)
    queue: asyncio.Queue = asyncio.Queue()
    with _LOCK:
        _LISTENERS[tid] = (asyncio.get_running_loop(), queue)
    task = asyncio.create_task(_run(adapter, tid, question, payload, role, poison))
    yield {"type": "stages", "stages": checks_from_events([], question, running=True)}
    while not task.done():
        waiter = asyncio.create_task(queue.get())
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        while not queue.empty():                  # several events at once: one update
            queue.get_nowait()
        with _LOCK:
            events = list(_EVENTS.get(tid, []))
        if not task.done():
            yield {"type": "stages", "stages": checks_from_events(events, question, running=True)}
    yield {"type": "result", **task.result()}


def _sky(observed: Dict[str, Any]) -> str:
    """The page background from the weather service's own WMO code and day/night flag."""
    code = observed.get("code")
    if code is None:
        return "default"
    if code >= 95:
        return "storm"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if not observed.get("is_day", True):
        return "evening"
    if code in (2, 3, 45, 48):
        return "cloudy"
    return "clear"
