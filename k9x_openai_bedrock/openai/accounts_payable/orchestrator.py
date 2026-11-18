# SPDX-License-Identifier: Apache-2.0
"""
APOrchestrator: runs the ap_invoice squad. It knows only its squad (K9-DEC-002): the squad YAML names the agents.

A RequiresHIL from the squad (PaymentAgent's paused OpenAI run) is handed to handle_requires_hil(): the framework's
BaseHILOrchestrator publishes hil.requests.openai-ap-payments for K9X HIL and stores the resume payload; the
flow returns pending_hil at once. When the decision comes back, the Router re-routes the resumed payload here,
the squad skips the steps already done, and PaymentAgent continues its OpenAI run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from k9_aif_abb.k9_core.orchestration.base_orchestrator import BaseOrchestrator
from k9_aif_abb.k9_core.orchestration.hil_signal import RequiresHIL

SQUADS_YAML = Path(__file__).resolve().parent / "squads.yaml"
SQUAD_ID = "ap_invoice"


class APOrchestrator(BaseOrchestrator):
    layer = "APOrchestrator"

    def execute_flow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        zt = self.apply_zero_trust(payload)
        if not zt["allowed"]:
            raise PermissionError(f"[{self.layer}] Zero Trust denied: {zt.get('reason')}")
        squad = self.squads.load_one(SQUADS_YAML, SQUAD_ID)
        try:
            results = self.execute_squads([squad], payload)
        except RequiresHIL as exc:
            out = self.handle_requires_hil(exc, payload)
            # the steps finished before the pause (for the page; the resume itself uses resume_state)
            out["so_far"] = ((exc.resume_state.get("squad") or {}).get(SQUAD_ID) or {}).get("results") or {}
            return out
        return {"status": "completed", **results}
