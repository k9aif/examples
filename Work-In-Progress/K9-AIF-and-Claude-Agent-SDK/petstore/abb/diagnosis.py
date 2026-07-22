"""
DiagnosisAgent — the one genuinely agentic capability in this application.

Customer problem diagnosis is the only step where the sequence of actions
isn't knowable in advance (project.md §3). Two SBBs satisfy this same
contract: SdkDiagnosisAgent (Claude Agent SDK) and DirectApiDiagnosisAgent
(direct Messages API). Selected by config, never by code change at the
call site — see config/sbb_bindings.yaml.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Coroutine, Dict, List, Optional

from k9_aif_abb.k9_core.agent.base_agent import BaseAgent


def _run_coro_sync(coro: "Coroutine[Any, Any, Any]") -> Any:
    """
    Run an async coroutine from BaseAgent's synchronous execute() contract.

    Mirrors k9_aif_abb.k9_inference.routers.k9_model_router._run_coro_sync
    (module-private there, so reimplemented here rather than imported) --
    same reasoning applies: BaseAgent.execute() is synchronous, but this
    diagnosis path is naturally async (SDK sessions, HTTP calls), and a
    caller embedding this inside an already-running event loop (FastAPI,
    etc.) would hit "asyncio.run() cannot be called from a running event
    loop" if we called asyncio.run() unconditionally here.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass(frozen=True)
class DiagnosisRequest:
    narrative: str
    customer_id: str
    tank_profile: Optional[Dict[str, Any]] = None
    order_id: Optional[str] = None  # set when a livestock order is what triggered diagnosis


@dataclass(frozen=True)
class DiagnosisResult:
    likely_causes: List[str]
    recommended_products: List[str]
    confidence: float
    escalate_to_human: bool
    provenance: List[str] = field(default_factory=list)


class DiagnosisAgent(BaseAgent):
    """
    ABB contract. Concrete SBBs implement diagnose(); execute() (BaseAgent's
    synchronous contract, required to sit inside a Squad flow) adapts
    the dict payload <-> DiagnosisRequest/DiagnosisResult at the boundary.
    """

    layer = "DiagnosisAgent ABB"

    @abstractmethod
    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
        raise NotImplementedError

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = DiagnosisRequest(
            narrative=payload.get("narrative", ""),
            customer_id=payload.get("customer_id", "unknown"),
            tank_profile=payload.get("tank_profile"),
            order_id=payload.get("order_id"),
        )
        result = _run_coro_sync(self.diagnose(request))

        self.publish_event({
            "type": "DiagnosisCompleted",
            "agent": self.layer,
            "substrate": self.__class__.__name__,
            "escalate_to_human": result.escalate_to_human,
            "confidence": result.confidence,
        })

        return {
            "agent": self.layer,
            "substrate": self.__class__.__name__,
            "likely_causes": result.likely_causes,
            "recommended_products": result.recommended_products,
            "confidence": result.confidence,
            "escalate_to_human": result.escalate_to_human,
            "provenance": result.provenance,
        }
