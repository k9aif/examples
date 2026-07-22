"""
PetstoreRouter -- extends K9-AIF's BaseRouter (k9_core/router/base_router.py).

Phase 1 of the Router/Orchestrator/Squad build-out (see PLAN.md). This
router only tries deterministic handlers; it does not yet dispatch to an
Orchestrator on CONTINUE -- that arrives in Phase 2. Falling through to
CONTINUE here is the correct, honest behavior for this phase: there is
nothing to hand off to yet.

route() is a synchronous override. BaseRouter's abstract method is
`route(self, payload) -> dict` with no async requirement -- the real OOB
RouterAgent happens to implement it as async (for its own Kafka-registry
lookup), but that's a choice, not the contract. Petstore's storefront is
synchronous throughout (see BaseSquad.execute(), BaseAgent.execute()), so
this router stays synchronous too.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k9_aif_abb.k9_core.router.base_router import BaseRouter

from petstore.routing.dispositions import Disposition, HandlerResult
from petstore.routing.handlers import DETERMINISTIC_HANDLERS


class PetstoreRouter(BaseRouter):

    layer = "Petstore Router"

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        config = dict(config or {})
        config.setdefault("k9_env", "development")  # reference impl; never claims production
        super().__init__(config=config, **kwargs)
        self._handlers: List = list(DETERMINISTIC_HANDLERS)
        self._stats: Dict[str, int] = {Disposition.SHORT_CIRCUIT.value: 0, Disposition.CONTINUE.value: 0}

    def route(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.normalize(payload)

        for handler in self._handlers:
            result: Optional[HandlerResult] = handler(payload)
            if result is not None:
                self._stats[result.disposition.value] += 1
                self.logger.info(
                    "[%s] %s -> %s (event_type=%s)",
                    self.layer, result.handler_name, result.disposition.value,
                    payload.get("event_type"),
                )
                return {
                    "disposition": result.disposition.value,
                    "handler": result.handler_name,
                    "response": result.response,
                }

        self._stats[Disposition.CONTINUE.value] += 1
        self.logger.info(
            "[%s] no deterministic handler claimed event_type=%s -> CONTINUE",
            self.layer, payload.get("event_type"),
        )
        return {"disposition": Disposition.CONTINUE.value, "payload": payload}

    def disposition_stats(self) -> Dict[str, Any]:
        """Counts by disposition, plus the fraction that never reached an agent --
        the number project.md's thesis asks a reader to be able to see."""
        total = sum(self._stats.values())
        short_circuited = self._stats[Disposition.SHORT_CIRCUIT.value]
        return {
            "counts": dict(self._stats),
            "total": total,
            "short_circuit_fraction": (short_circuited / total) if total else 0.0,
        }
