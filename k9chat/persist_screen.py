# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework — k9chat screening for anything a visitor persists

"""
Anything a visitor's input leaves behind -- a Project file, a Project's
name/instructions, a learned correction in the shared knowledge base --
outlives the message that carried it and is read back into later prompts
(and, for the knowledge base, into other visitors' prompts). Transient
input (a chat message, a one-message attachment, a fetched page) is
screened on its way to the model and gone after the reply; persisted input
has to be screened before it's stored, or a planted instruction or
hostile link sits there and fires on every later retrieval.

Two layers, both required, fail closed:
  1. k9x Shield -- the app's own Shield profile (security.shield in
     config.yaml, the same checks a chat message gets: InputSizeCheck,
     PromptInjectionCheck, PIIBoundaryCheck). Deterministic and cheap, so
     it runs first over the whole text.
  2. Granite Guardian -- GuardAgent forced on with fail_closed, whatever
     K9CHAT_GUARDIAN_ENABLED says (that switch governs live chat messages;
     it doesn't get to waive screening of what's stored). Run over
     overlapping windows, because a guardian model reads a bounded context
     and a long file would otherwise be judged on its first page only.
     A guardian that can't be reached means nothing is stored.

ScreenRefused carries a visitor-safe reason; callers turn it into a 4xx.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("k9chat.persist_screen")


class ScreenRefused(Exception):
    """Content refused for storage. str(exc) is safe to show the visitor."""


class PersistScreen:
    def __init__(self, config: Dict[str, Any]) -> None:
        from k9_aif_abb.k9_security.vulnerability.shield_governance import ShieldGovernance
        from k9chat.guard_agent import GuardAgent

        cfg = config.get("persist_screening", {}) or {}
        self.max_chars = int(cfg.get("max_chars", 100_000))
        self.window = int(cfg.get("guardian_window_chars", 4000))
        self.overlap = int(cfg.get("guardian_overlap_chars", 200))
        self.shield = ShieldGovernance(config)
        self.guard = GuardAgent(config)
        self.guard.enabled = True
        self.guard.fail_closed = True

    def _windows(self, text: str):
        step = max(1, self.window - self.overlap)
        for start in range(0, max(len(text), 1), step):
            yield text[start:start + self.window]
            if start + self.window >= len(text):
                break

    def screen(self, text: str, kind: str, ctx: Optional[Dict[str, Any]] = None) -> None:
        """Raise ScreenRefused unless *text* may be stored. *kind* names what
        it is ("project file 'notes.md'") for the visitor and the log."""
        if not text or not text.strip():
            return
        if len(text) > self.max_chars:
            raise ScreenRefused(
                f"{kind} is too large ({len(text):,} characters; the limit is {self.max_chars:,})."
            )
        context = {"component": "k9chat:persist", "kind": kind, **(ctx or {})}
        try:
            self.shield.pre_process({"query": text, "source": "persist"}, context)
        except PermissionError as exc:
            log.warning("[PersistScreen] Shield refused %s: %s", kind, exc)
            raise ScreenRefused(f"{kind} was not saved: k9x Shield flagged its content.") from exc

        for i, window in enumerate(self._windows(text)):
            try:
                result = self.guard.execute({"text": window})
            except PermissionError as exc:   # GuardAgent's own (framework) Shield ingress
                log.warning("[PersistScreen] Shield refused %s window %d: %s", kind, i, exc)
                raise ScreenRefused(f"{kind} was not saved: k9x Shield flagged its content.") from exc
            if not result.get("checked"):
                log.warning("[PersistScreen] Guardian unavailable for %s: %s", kind, result.get("error"))
                raise ScreenRefused(f"{kind} was not saved: the safety check is unavailable, try again later.")
            if not result.get("passed"):
                log.warning("[PersistScreen] Guardian refused %s window %d: %s",
                            kind, i, result.get("guardian_output"))
                raise ScreenRefused(f"{kind} was not saved: Guardian flagged its content as unsafe.")
        log.info("[PersistScreen] passed %s (%d chars)", kind, len(text))
