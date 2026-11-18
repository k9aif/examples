# SPDX-License-Identifier: Apache-2.0
"""
The squad's agents. Two are OpenAI agents (K9OpenAIAgent): everything they do is in their YAML. The rules step is
K9-AIF's K9RulesAgent, deciding through the K9X Rules Engine (GoRulesAdapter); it only reports the decision
(hil_decisions are not used), because the pause for a person is the OpenAI SDK's own, on pay_invoice.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from k9_aif_abb.k9_adapters.openai_agents import K9OpenAIAgent
from k9_aif_abb.k9_agents.rules.k9_rules_agent import K9RulesAgent

from .tools import record_facts


class InvoiceAgent(K9OpenAIAgent):
    pass


class PaymentAgent(K9OpenAIAgent):
    pass


class APRulesAgent(K9RulesAgent):
    """K9RulesAgent (K9X Rules Engine) whose facts come from the records, not the model: InvoiceAgent read the vendor,
    invoice number and amount; the vendor's status, a changed bank account, a PO match and a duplicate are looked up
    here, deterministically, and sent to the rules. Takes the OpenAI agents' squad kwargs and ignores them."""

    def __init__(self, config: Any = None, governance: Any = None, monitor: Any = None, **_openai_kwargs: Any):
        super().__init__(config=config, governance=governance, monitor=monitor)

    def evaluate_rules(self, request: Dict[str, Any]) -> Dict[str, Any]:
        read = (request.get("invoice_agent") or {}).get("output")
        if isinstance(read, str):
            read = json.loads(read)
        facts = record_facts(read.get("vendor"), read.get("invoice_id"), read.get("amount"))
        out = super().evaluate_rules({**request, "invoice_agent": {"output": facts}})
        out["output"]["facts"] = facts
        return out
