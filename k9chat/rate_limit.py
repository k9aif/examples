# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework — k9chat per-visitor / per-IP message limits

"""
How much GPU one visitor can use -- the complement to queue_control.py,
which only bounds how many generations run *at once*. Without this, one
script could keep all K9CHAT_MAX_CONCURRENT slots busy indefinitely and
every real visitor would wait behind it.

Two keys, each with a short and a daily window:
  - visitor: the signed-cookie visitor_id from auth.py. Fair-share between
    real people, but a bot can drop its cookie and re-run the name step.
  - ip: the real client address. The one a cookie-dropping bot can't
    shed. Looser than the visitor limit since an office or carrier NAT
    can put several real people behind one address.
A message is refused if ANY window is over its budget.

Counting reuses the framework's own Shield check, RequestFrequencyCheck
(OWASP LLM10, unbounded consumption) -- one instance per window, keyed by
"<scope>:<id>:<window>" so windows never share a counter. It counts in the
process-wide shared cache, so limits are per K9Chat process (one container
today); point its cache at Redis if this ever runs as several replicas.

Every message counts, FAQ-shortcut hits included: they're cheap (CPU
reranker), but a limit that only some messages count against is a limit a
bot can learn to route around.

Client IP: behind the Cloudflare tunnel the TCP peer is cloudflared (a
private/loopback address), and Cloudflare sets CF-Connecting-IP to the real
visitor. That header is only trusted when the peer is private -- a public
peer reached the app directly and could have forged it. A private peer
with NO forwarding header is a LAN visitor, exempt when exempt_lan is on
(the owner's own use shouldn't hit the public demo's limits).
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, Dict, List, Optional

from starlette.requests import Request

log = logging.getLogger("k9chat.rate_limit")


def _flag(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes")


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not addr.is_global


def client_ip(request: Request) -> tuple[str, bool]:
    """(ip, is_lan). Real visitor address behind the tunnel; is_lan is True
    only for a private peer that carried no forwarding header."""
    peer = request.client.host if request.client else ""
    if peer and _is_private(peer):
        forwarded = request.headers.get("cf-connecting-ip") or \
            (request.headers.get("x-forwarded-for") or "").split(",")[0]
        forwarded = forwarded.strip()
        if forwarded:
            return forwarded, False
        return peer, True
    return peer or "unknown", False


def _describe(seconds: int) -> str:
    if seconds >= 86400 and seconds % 86400 == 0:
        days = seconds // 86400
        return "day" if days == 1 else f"{days} days"
    if seconds >= 3600 and seconds % 3600 == 0:
        hours = seconds // 3600
        return "hour" if hours == 1 else f"{hours} hours"
    minutes = max(1, seconds // 60)
    return "minute" if minutes == 1 else f"{minutes} minutes"


def _duration(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        hours = seconds // 3600
        return "1 hour" if hours == 1 else f"{hours} hours"
    minutes = max(1, seconds // 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


class RateLimiter:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        from k9_aif_abb.k9_security.vulnerability.checks.request_frequency_check import (
            RequestFrequencyCheck,
        )
        cfg = (config or {}).get("rate_limit", {}) or {}
        self.enabled = _flag(cfg.get("enabled"), True)
        self.exempt_lan = _flag(cfg.get("exempt_lan"), True)
        self._windows: Dict[str, List[Dict[str, Any]]] = {}
        for scope in ("visitor", "ip"):
            windows = []
            for w in cfg.get(scope, []) or []:
                limit, seconds = int(w["max"]), int(w["window_seconds"])
                windows.append({
                    "max": limit,
                    "seconds": seconds,
                    "check": RequestFrequencyCheck({
                        "max_requests_per_window": limit,
                        "rate_limit_window_seconds": seconds,
                    }),
                })
            self._windows[scope] = windows
        log.info("[RateLimit] enabled=%s exempt_lan=%s visitor=%s ip=%s", self.enabled, self.exempt_lan,
                 [(w["max"], w["seconds"]) for w in self._windows["visitor"]],
                 [(w["max"], w["seconds"]) for w in self._windows["ip"]])

    def check(self, request: Request, visitor_id: Optional[str]) -> Optional[str]:
        """None if the message may proceed, else the reply to show instead.
        Counts this message against every window (all of them, even after
        one is over -- a refused attempt is still an attempt)."""
        if not self.enabled:
            return None
        ip, is_lan = client_ip(request)
        if is_lan and self.exempt_lan:
            return None
        exceeded = []
        for scope, key in (("visitor", visitor_id or "anonymous"), ("ip", ip)):
            for w in self._windows[scope]:
                result = w["check"].check({"session_id": f"k9chat:{scope}:{key}:{w['seconds']}"})
                if result.blocked:
                    exceeded.append(w)
        if not exceeded:
            return None
        # Report the longest window that's over -- that's when they can really come back.
        worst = max(exceeded, key=lambda w: w["seconds"])
        log.warning("[RateLimit] refused visitor=%s ip=%s (limit %d per %ss)",
                    visitor_id, ip, worst["max"], worst["seconds"])
        return (
            f"You've reached the demo limit of {worst['max']} messages per "
            f"{_describe(worst['seconds'])}. K9Chat runs on a single GPU shared by every "
            f"visitor, so please come back a little later (the limit resets within "
            f"{_duration(worst['seconds'])})."
        )
