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

import threading
import uuid
from typing import Any, Dict, List

from k9_aif_abb.k9_utils.trace_events import register_trace_callback

from . import tools

_LOCK = threading.Lock()
_EVENTS: Dict[str, List[Dict[str, Any]]] = {}


def _collect(event: Dict[str, Any]) -> None:
    tid = event.get("trace_id")
    if tid in _EVENTS:
        _EVENTS[tid].append(event)


register_trace_callback(_collect)


def describe(e: Dict[str, Any]) -> Dict[str, str] | None:
    """One trace event as {"step", "status", "detail"}; None for events not shown."""
    t = e.get("type")
    if t == "ZeroTrust":
        ok = e.get("allowed")
        return {"step": "Zero Trust", "status": "allowed" if ok else "blocked",
                "detail": f"{e.get('decision')}: {e.get('reason') or ''}".strip()}
    if t == "OpenAIRunCheck":
        return {"step": f"Shield {e.get('gate')}", "status": "allowed",
                "detail": f"request {e.get('gate')} checks passed" if e.get("gate") == "ingress"
                else "final answer checks passed"}
    if t == "ShieldChain" and e.get("blocked_by"):
        return {"step": "Shield", "status": "blocked", "detail": f"{e.get('gate')} blocked by {e.get('blocked_by')}"}
    if t == "OpenAIAgentStart":
        return {"step": "Agent turn", "status": "info", "detail": f"{e.get('agent')} (Zero Trust {e.get('zero_trust')})"}
    if t == "LLMRoute":
        return {"step": "Model Router", "status": "info",
                "detail": f"task '{e.get('task_type')}' -> {e.get('model_alias')} ({e.get('model')})"}
    if t == "LLMCall":
        return {"step": "Model call", "status": "info",
                "detail": f"{e.get('model')}, {e.get('latency_ms')} ms, tokens {e.get('tokens_in')}/{e.get('tokens_out')}"}
    if t == "ToolCallScreen":
        return {"step": "Shield tool call", "status": "allowed" if e.get("allowed") else "blocked",
                "detail": f"{e.get('tool')}" + ("" if e.get("allowed") else f": {e.get('reason')}")}
    if t == "ToolResultScreen":
        return {"step": "Shield tool result", "status": "allowed" if e.get("allowed") else "blocked",
                "detail": f"{e.get('tool')}" + ("" if e.get("allowed") else f" withheld: {e.get('reason')}")}
    if t == "OpenAIModelReply":
        return {"step": "Shield reply", "status": "allowed" if e.get("screened") else "info",
                "detail": f"{e.get('agent')}: " + ("reply text checked" if e.get("screened")
                                                  else "tool call only, no text to check")}
    if t == "OpenAIHandoff":
        return {"step": "Handoff", "status": "info", "detail": f"{e.get('agent')} -> {e.get('to_agent')}"}
    return None


async def ask(adapter, zip_or_text: str, role: str, poison: bool = False) -> Dict[str, Any]:
    """Run one request. Returns question, outcome ("answer" | "refused" | "error"), text, trace."""
    tid = f"weather-{uuid.uuid4().hex[:12]}"
    question = f"What is the weather in zip code {zip_or_text}?"
    payload = {"message": question, "principal_id": f"demo-{role}", "roles": [role],
               "action_type": "weather.lookup", "trace_id": tid}
    with _LOCK:
        _EVENTS[tid] = []
    token = tools.POISON_NEXT_LOOKUP.set({"armed": poison})   # this request only
    try:
        result = await adapter.execute_async(payload)
        outcome, text = "answer", result["output_text"]
    except PermissionError as exc:
        outcome, text = "refused", str(exc)
    except Exception as exc:                       # reported to the caller, not hidden
        outcome, text = "error", f"{type(exc).__name__}: {exc}"
    finally:
        tools.POISON_NEXT_LOOKUP.reset(token)
        with _LOCK:
            events = _EVENTS.pop(tid, [])
    trace = [d for d in (describe(e) for e in events) if d]
    return {"question": question, "role": role, "poisoned": poison, "outcome": outcome, "text": text,
            "trace": trace}
