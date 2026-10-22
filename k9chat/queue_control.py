# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework

"""
K9Chat's job queue: how many generations run against the model at once,
and who waits for the next free slot. Same shape as DAS's Job Queue
(dow-k9-aif: MAX_QUEUE_SIZE, per-visitor cap, refuse when full):

  - at most K9CHAT_MAX_CONCURRENT (5) generations run at once;
  - at most K9CHAT_MAX_QUEUE (5) more wait, first come first served;
    beyond that a request is refused straight away (QueueBusy) rather
    than joining an endless line;
  - one job per visitor at a time (queued or running);
  - a waiter gives up after K9CHAT_QUEUE_TIMEOUT_SECONDS (120).

Waiting holds no thread. The old version parked a worker thread on a
semaphore per waiter: ~30 waiters filled the shared pool the running
chats also need (link fetching), so the whole app could stall, and a
visitor who closed the tab mid-wait still took a slot later and never gave
it back. Now a waiter polls every _POLL_SECONDS (asyncio.sleep on the
async path), and a cancelled or timed-out waiter simply leaves the line.

The GPU thermal gate stays: no new job starts while the GPU is at or above
K9CHAT_GPU_TEMP_LIMIT_C (gpu_telemetry.py); running jobs are never killed.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from k9chat import gpu_telemetry

_MAX_CONCURRENT = int(os.environ.get("K9CHAT_MAX_CONCURRENT", "5"))
_MAX_QUEUE = int(os.environ.get("K9CHAT_MAX_QUEUE", "5"))
_TIMEOUT_SECONDS = float(os.environ.get("K9CHAT_QUEUE_TIMEOUT_SECONDS", "120"))
_POLL_SECONDS = 0.25

_lock = threading.Lock()
_running: dict = {}            # job_id -> {"visitor": str, "started": float}
_waiting: list = []            # job dicts, FIFO: {"id", "visitor", "queued"}
_seq = 0


class QueueBusy(Exception):
    """A job can't be queued or waited too long. str(exc) is shown to the visitor."""


def _admit(visitor: Optional[str]) -> dict:
    """Join the line, or raise QueueBusy (line full / visitor already has a job)."""
    global _seq
    with _lock:
        if visitor and (any(j["visitor"] == visitor for j in _running.values())
                        or any(j["visitor"] == visitor for j in _waiting)):
            raise QueueBusy("You already have a request running or waiting. "
                            "Wait for it to finish, then send the next one.")
        # Cap running + waiting together: in a burst everyone arrives before
        # anything has started, so checking "slots full" first lets the
        # line grow past its limit.
        if len(_running) + len(_waiting) >= _MAX_CONCURRENT + _MAX_QUEUE:
            raise QueueBusy(f"K9Chat is busy: {_MAX_CONCURRENT} chats are running and {_MAX_QUEUE} "
                            "are waiting, which is the most this one GPU takes. Please try again in a minute.")
        _seq += 1
        job = {"id": f"J{_seq:05d}", "visitor": visitor, "queued": time.monotonic()}
        _waiting.append(job)
        return job


def _eligible(job: dict) -> bool:
    """True if *job* is within the first N in line, N = free slots. Keeps
    first-come-first-served while letting several jobs start at once."""
    with _lock:
        free = _MAX_CONCURRENT - len(_running)
        return job in _waiting and _waiting.index(job) < free


def _try_start(job: dict) -> bool:
    """Start *job* if it's eligible (see _eligible)."""
    with _lock:
        free = _MAX_CONCURRENT - len(_running)
        if job not in _waiting or _waiting.index(job) >= free:
            return False
        _waiting.remove(job)
        _running[job["id"]] = {"visitor": job["visitor"], "started": time.monotonic()}
        return True


def _leave(job: dict) -> None:
    with _lock:
        if job in _waiting:
            _waiting.remove(job)
        _running.pop(job["id"], None)


def _position(job: dict) -> int:
    with _lock:
        return _waiting.index(job) if job in _waiting else 0


def status(visitor: Optional[str] = None) -> dict:
    """Live snapshot for the Job Queue panel. Jobs carry a short id and a
    status only -- never anyone's message -- plus "mine" for the caller."""
    with _lock:
        jobs = [{"id": jid, "status": "running", "mine": bool(visitor) and j["visitor"] == visitor}
                for jid, j in sorted(_running.items(), key=lambda kv: kv[1]["started"])]
        jobs += [{"id": j["id"], "status": "waiting", "mine": bool(visitor) and j["visitor"] == visitor}
                 for j in _waiting]
        return {"active": len(_running), "waiting": len(_waiting),
                "max_concurrent": _MAX_CONCURRENT, "max_queue": _MAX_QUEUE, "jobs": jobs}


# ── Who's here right now ─────────────────────────────────────────────────
# Every open K9Chat tab already polls /chat/queue-status every 4s (the
# waitlist widget), so presence rides on that poll -- no extra requests. A
# visitor counts as "here" if any of their tabs polled within the window;
# keyed by visitor_id, so one person with three tabs is one, not three.
_PRESENCE_WINDOW_SECONDS = 15
_presence: dict[str, float] = {}
_presence_lock = threading.Lock()


def touch_presence(visitor_id: str | None) -> int:
    """Record that *visitor_id* is here; return how many visitors are."""
    now = time.monotonic()
    with _presence_lock:
        if visitor_id:
            _presence[visitor_id] = now
        for vid in [v for v, seen in _presence.items() if now - seen > _PRESENCE_WINDOW_SECONDS]:
            del _presence[vid]
        return len(_presence)


# ── Model-switch cooldown ────────────────────────────────────────────────
# A different, heavier cost than a normal chat message -- switching loads
# a fresh multi-GB model into VRAM (apply_settings()'s warm-up call is a
# real generation). Two people casually flipping between models back and
# forth, with no malice at all, would mean real repeated reload cost on
# the GPU -- flagged directly by Ravi (2026-09-20) as the concrete
# scenario this guards against. A cooldown, not a per-visitor counter,
# because the cost is per-switch (global, process-wide), not per-visitor.
_SWITCH_COOLDOWN_SECONDS = int(os.environ.get("K9CHAT_MODEL_SWITCH_COOLDOWN_SECONDS", "60"))
_switch_lock = threading.Lock()
_last_switch_at = 0.0


def check_switch_cooldown() -> tuple[bool, int]:
    """(allowed, retry_after_seconds). Reserves the slot immediately on
    success (not just checks) so two near-simultaneous switch requests
    can't both pass the check before either updates the timestamp."""
    global _last_switch_at
    with _switch_lock:
        now = time.monotonic()
        elapsed = now - _last_switch_at
        if elapsed < _SWITCH_COOLDOWN_SECONDS:
            return False, int(_SWITCH_COOLDOWN_SECONDS - elapsed) + 1
        _last_switch_at = now
        return True, 0


class QueueSlot:
    """One job's turn at a generation slot, sync (`with`) or async
    (`async with`). Raises QueueBusy on entry if the line is full, the
    visitor already has a job, or the wait times out. `position` is how
    many were ahead of this job when it joined (0 = started straight away)."""

    def __init__(self, visitor: Optional[str] = None) -> None:
        self.visitor = visitor
        self.position = 0
        self.job: Optional[dict] = None
        self._t0 = 0.0

    def _timed_out(self) -> bool:
        return time.monotonic() - self._t0 > _TIMEOUT_SECONDS

    def _give_up(self):
        _leave(self.job)
        return QueueBusy("K9Chat is busy and your request waited too long. Please try again in a minute.")

    def __enter__(self) -> "QueueSlot":
        self.job = _admit(self.visitor)
        self._t0 = time.monotonic()
        self.position = _position(self.job)
        try:
            while True:
                if _eligible(self.job) and not gpu_telemetry.is_over_temp_limit() and _try_start(self.job):
                    return self
                if self._timed_out():
                    raise self._give_up()
                time.sleep(_POLL_SECONDS)
        except BaseException:
            _leave(self.job)
            raise

    def __exit__(self, *exc) -> bool:
        _leave(self.job)
        return False

    async def __aenter__(self) -> "QueueSlot":
        import asyncio
        self.job = _admit(self.visitor)
        self._t0 = time.monotonic()
        self.position = _position(self.job)
        try:
            while True:
                # The temperature lookup is a short HTTP call (cached 1.5s):
                # run it off the event loop, and only once this job may start.
                if _eligible(self.job):
                    hot = await asyncio.to_thread(gpu_telemetry.is_over_temp_limit)
                    if not hot and _try_start(self.job):
                        return self
                if self._timed_out():
                    raise self._give_up()
                await asyncio.sleep(_POLL_SECONDS)
        except BaseException:          # includes CancelledError: a closed tab leaves the line
            _leave(self.job)
            raise

    async def __aexit__(self, *exc) -> bool:
        _leave(self.job)
        return False

    async def wait(self):
        """Async generator for streaming callers: joins the line (QueueBusy
        if it can't), yields the current position each time it changes
        while waiting, and returns once the job has started. The caller
        must call release() when the job is done."""
        import asyncio
        self.job = _admit(self.visitor)
        self._t0 = time.monotonic()
        self.position = _position(self.job)
        last = None
        try:
            while True:
                if _eligible(self.job):
                    hot = await asyncio.to_thread(gpu_telemetry.is_over_temp_limit)
                    if not hot and _try_start(self.job):
                        return
                pos = _position(self.job)
                if pos != last:
                    last = pos
                    yield pos
                if self._timed_out():
                    raise self._give_up()
                await asyncio.sleep(_POLL_SECONDS)
        except BaseException:          # cancelled (tab closed) or gave up: leave the line
            _leave(self.job)
            raise

    def release(self) -> None:
        if self.job is not None:
            _leave(self.job)

    @property
    def waited_seconds(self) -> float:
        return time.monotonic() - self._t0 if self._t0 else 0.0
