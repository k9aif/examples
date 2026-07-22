"""
DirectApiDiagnosisAgent — SBB-B. Single-shot structured call via K9-AIF's
standard llm_invoke() chain. No autonomous loop: this method decides what
to check, not the model.

Built first, deliberately (project.md §10 Phase 3) -- it forces the
DiagnosisAgent contract to be proven substrate-neutral using only the
standard K9-AIF inference chain, before any Agent SDK detail could leak
into it.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from k9_aif_abb.k9_inference.models.inference_request import InferenceRequest
from k9_aif_abb.k9_utils.llm_invoke import llm_invoke

from petstore.abb.diagnosis import DiagnosisAgent, DiagnosisRequest, DiagnosisResult
from petstore.services import inventory

_SYSTEM_PROMPT = (
    "You are a fish-keeping and pet-care diagnostic assistant for an online "
    "pet store. A customer has described a problem in their own words. "
    "Identify the most likely causes and recommend relevant products from "
    "the catalog if you can name specific ones. Respond ONLY with a JSON "
    "object matching this shape, no other text:\n"
    '{"likely_causes": ["..."], "recommended_products": ["..."], '
    '"confidence": 0.0, "escalate_to_human": false}\n'
    "Set escalate_to_human to true if the situation sounds urgent, "
    "ambiguous, or outside routine care advice (e.g. suspected disease "
    "outbreak, water chemistry emergency, livestock in acute distress)."
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class DirectApiDiagnosisAgent(DiagnosisAgent):

    layer = "DirectApiDiagnosisAgent SBB"

    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
        provenance: List[str] = [f"direct_api: single-shot call for narrative from {request.customer_id}"]

        prompt = self._build_prompt(request)
        req = InferenceRequest(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            task_type="reasoning",
            metadata={"agent": self.layer, "customer_id": request.customer_id},
        )

        resp = llm_invoke(self.config, req)
        provenance.append(f"direct_api: model={resp.model_alias} provider={resp.provider}")

        parsed = self._parse_response(resp.output)
        provenance.append("direct_api: parsed structured JSON from single response, no re-querying")

        recommended = self._resolve_products(parsed.get("recommended_products", []))

        return DiagnosisResult(
            likely_causes=parsed.get("likely_causes", []),
            recommended_products=recommended,
            confidence=float(parsed.get("confidence", 0.0)),
            escalate_to_human=bool(parsed.get("escalate_to_human", False)),
            provenance=provenance,
        )

    def _build_prompt(self, request: DiagnosisRequest) -> str:
        parts = [f"Customer narrative:\n{request.narrative}"]
        if request.tank_profile:
            parts.append(f"\nTank profile: {request.tank_profile}")
        return "\n".join(parts)

    def _parse_response(self, output: str) -> Dict[str, Any]:
        match = _JSON_BLOCK.search(output)
        if not match:
            # Code decides the fallback here -- not the model. A single-shot
            # call that didn't return valid JSON escalates rather than
            # guessing at structure, per this SBB's "code orchestrates
            # explicitly" design (project.md §5).
            return {"likely_causes": [], "recommended_products": [],
                    "confidence": 0.0, "escalate_to_human": True}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"likely_causes": [], "recommended_products": [],
                    "confidence": 0.0, "escalate_to_human": True}

    def _resolve_products(self, sku_ids: List[str]) -> List[str]:
        """Only return SKUs that actually exist in the catalog -- the model
        naming a product is a suggestion, not a fact; the code verifies it."""
        resolved = []
        for sku_id in sku_ids:
            if inventory.get_sku(sku_id) is not None:
                resolved.append(sku_id)
        return resolved
