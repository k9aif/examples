# SPDX-License-Identifier: Apache-2.0
"""
APOrchestrator: runs the ap_invoice squad. It knows only its squad (K9-DEC-002): the squad YAML names the agents.

A RequiresHIL from the squad (PaymentAgent's paused OpenAI run) is described as a K9X HIL task (k9x.hil.task/v1: the
invoice PDF as its artifact, the rules' approver role as who may decide) and handed to handle_requires_hil(): the
framework's BaseHILOrchestrator publishes hil.requests.openai-ap-payments for K9X HIL and stores the resume payload; the
flow returns pending_hil at once. When the decision comes back, the Router re-routes the resumed payload here,
the squad skips the steps already done, and PaymentAgent continues its OpenAI run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from k9_aif_abb.k9_core.orchestration.base_orchestrator import BaseOrchestrator
from k9_aif_abb.k9_core.orchestration.hil_signal import RequiresHIL

SQUADS_YAML = Path(__file__).resolve().parent / "squads.yaml"
SQUAD_ID = "ap_invoice"
INVOICE_FILES = {"INV-1042", "INV-1043", "INV-2001", "INV-4001"}      # invoices/*.pdf, uploaded by upload_invoices.py
RULES_PAGE = "https://openai.k9x.ai/ap"


def invoice_bucket(config: Dict[str, Any]) -> str:
    return ((config or {}).get("ap") or {}).get("invoice_bucket") or os.environ.get("AP_INVOICE_BUCKET") \
        or "openai-ap-invoices"


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
            # the steps finished before the pause (the resume itself uses resume_state)
            so_far = ((exc.resume_state.get("squad") or {}).get(SQUAD_ID) or {}).get("results") or {}
            self._describe_task(exc, so_far)
            out = self.handle_requires_hil(exc, payload)
            out["so_far"] = so_far
            return out
        return {"status": "completed", **results}

    def _describe_task(self, exc: RequiresHIL, so_far: Dict[str, Any]) -> None:
        """The K9X HIL task (k9x.hil.task/v1) for a paused payment: who may decide (the rules' approver_role), the
        invoice itself (its PDF in object storage, fetched by HIL for the reviewer) and the rule that fired."""
        decision = (so_far.get("rules_check") or {}).get("output") or {}
        facts = decision.get("facts") or {}
        invoice_id, vendor, amount = facts.get("invoice_id"), facts.get("vendor"), facts.get("amount")
        manager = decision.get("approver_role") == "manager"
        artifacts = []
        if invoice_id in INVOICE_FILES:
            artifacts.append({"uri": f"s3://{invoice_bucket(self.config)}/{invoice_id}.pdf",
                              "title": f"Invoice {invoice_id}", "media_type": "application/pdf", "role": "primary"})
        artifacts.append({"uri": RULES_PAGE, "title": "The accounts payable rules (AP-01 to AP-08)",
                          "role": "supporting"})
        exc.context.update({"rule": decision.get("rule"), "rule_reason": decision.get("reason"),
                            "vendor": vendor, "invoice_id": invoice_id, "amount": amount,
                            "vendor_status": facts.get("vendor_status"), "bank_changed": facts.get("bank_changed"),
                            "po_matched": facts.get("po_matched"), "duplicate": facts.get("duplicate")})
        title = (f"Approve payment of {invoice_id}: {vendor}, ${float(amount):,.2f}" if invoice_id and amount is not None
                 else exc.reason)
        exc.set_task_fields(
            title=title, task_type="invoice-approval", artifacts=artifacts,
            required_role="manager" if manager else "worker",
            decision_authority="Accounts payable manager" if manager else "Accounts payable clerk",
            require_comment=manager, ttl_hours=24, ttl_action="reject", priority="high" if manager else "medium")
