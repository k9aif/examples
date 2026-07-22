"""
SdkDiagnosisAgent -- SBB-A. Wraps a Claude Agent SDK session at the Agent
layer (Architecture_Guide.md principle #1 -- same BaseAdapter discipline as
the framework's existing CrewAIOrchestratorAdapter, one layer down, because
the SDK's unit of encapsulation is one session, not a crew).

Does NOT go through llm_invoke/K9ModelRouter -- the SDK owns its own
inference loop. That's the one substrate in this whole example that
doesn't go through the standard K9-AIF inference chain (Detailed_Design.md).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    TextBlock,
    ToolPermissionContext,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
)

from k9_aif_abb.k9_core.base_adapter import BaseAdapter

from petstore.abb.diagnosis import DiagnosisAgent, DiagnosisRequest, DiagnosisResult
from petstore.gates import GateRegistryFactory, GateState, GateType
from petstore.sbb.sdk_tools import (
    FULFILLMENT_TOOL_NAME,
    check_inventory,
    check_species_compatibility,
    initiate_fulfillment,
    retrieve_care_guide,
    search_catalog,
)

_MCP_SERVER_NAME = "petstore"

_SYSTEM_PROMPT = (
    "You are a fish-keeping and pet-care diagnostic assistant for an online "
    "pet store. Use the available tools to investigate the customer's "
    "problem -- search the catalog, check species compatibility, retrieve "
    "care guidance, check inventory -- as needed, in whatever order makes "
    "sense. When you're done investigating, end your final message with a "
    "JSON object on its own line matching this shape, no other text after it:\n"
    '{"likely_causes": ["..."], "recommended_products": ["..."], '
    '"confidence": 0.0, "escalate_to_human": false}'
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class SdkDiagnosisAgent(DiagnosisAgent, BaseAdapter):

    layer = "SdkDiagnosisAgent SBB"

    def __init__(self, config: Dict[str, Any] | None = None, **kwargs: Any) -> None:
        DiagnosisAgent.__init__(self, config or {}, **kwargs)
        BaseAdapter.__init__(self, adapter_name="SdkDiagnosisAgent")
        self._gate_registry = GateRegistryFactory.create(self.config)

    # ------------------------------------------------------------------
    # BaseAdapter contract
    # ------------------------------------------------------------------
    def adapt_input(self, request: DiagnosisRequest) -> str:
        parts = [f"Customer narrative:\n{request.narrative}"]
        if request.tank_profile:
            parts.append(f"\nTank profile: {request.tank_profile}")
        if request.order_id:
            parts.append(f"\nRelated order_id: {request.order_id}")
        return "\n".join(parts)

    def adapt_output(self, sdk_result: Dict[str, Any]) -> DiagnosisResult:
        return DiagnosisResult(
            likely_causes=sdk_result.get("likely_causes", []),
            recommended_products=sdk_result.get("recommended_products", []),
            confidence=float(sdk_result.get("confidence", 0.0)),
            escalate_to_human=bool(sdk_result.get("escalate_to_human", False)),
            provenance=sdk_result.get("provenance", []),
        )

    # ------------------------------------------------------------------
    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
        prompt = self.adapt_input(request)
        provenance: List[str] = ["sdk: multi-turn session started"]
        tool_calls: List[str] = []

        options = self._build_options(request, provenance)

        final_text = ""
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, "content"):
                for block in getattr(message, "content", []) or []:
                    if isinstance(block, TextBlock):
                        final_text = block.text
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append(block.name)
            result_text = getattr(message, "result", None)
            if result_text:
                final_text = result_text

        provenance.append(f"sdk: tool calls made = {tool_calls}")
        parsed = self._parse_final_text(final_text)
        parsed["provenance"] = provenance

        return self.adapt_output(parsed)

    # ------------------------------------------------------------------
    def _build_options(self, request: DiagnosisRequest, provenance: List[str]) -> ClaudeAgentOptions:
        server = create_sdk_mcp_server(
            name=_MCP_SERVER_NAME,
            tools=[search_catalog, check_species_compatibility, retrieve_care_guide,
                   check_inventory, initiate_fulfillment],
        )

        async def can_use_tool(tool_name: str, tool_input: Dict[str, Any],
                                context: ToolPermissionContext):
            if FULFILLMENT_TOOL_NAME in tool_name:
                order_id = tool_input.get("order_id") or request.order_id
                if order_id is None:
                    return PermissionResultDeny(
                        behavior="deny", message="No order_id provided for fulfillment.",
                        interrupt=False,
                    )
                gate = await self._gate_registry.status(order_id, GateType.LIVESTOCK)
                if gate.state is not GateState.APPROVED:
                    provenance.append(
                        f"sdk: can_use_tool DENIED {tool_name} for order {order_id} "
                        f"(gate state={gate.state.value})"
                    )
                    return PermissionResultDeny(
                        behavior="deny",
                        message=(
                            f"Livestock fulfillment requires human approval. "
                            f"Gate {gate.gate_id} is {gate.state.value}."
                        ),
                        interrupt=False,
                    )
            return PermissionResultAllow(behavior="allow", updated_input=None, updated_permissions=None)

        return ClaudeAgentOptions(
            system_prompt=_SYSTEM_PROMPT,
            mcp_servers={_MCP_SERVER_NAME: server},
            # NOTE (DEVIATIONS.md #5): the exact qualified tool-name string
            # Claude sees for in-process SDK MCP tools isn't verifiable
            # without a live run against the real CLI transport. Using bare
            # tool names here; if the real qualified form differs (observed
            # empirically once this is actually run), update this list and
            # note the correction in DEVIATIONS.md.
            allowed_tools=["search_catalog", "check_species_compatibility",
                           "retrieve_care_guide", "check_inventory", FULFILLMENT_TOOL_NAME],
            can_use_tool=can_use_tool,
            max_turns=6,
            # Deliberately omitting `agents=` -- subagents are opt-in in this
            # SDK (DEVIATIONS.md #3); never populating this field is the
            # entire disable mechanism. See test_no_sdk_subagents.py.
        )

    def _parse_final_text(self, text: str) -> Dict[str, Any]:
        match = _JSON_BLOCK.search(text or "")
        if not match:
            return {"likely_causes": [], "recommended_products": [],
                    "confidence": 0.0, "escalate_to_human": True}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"likely_causes": [], "recommended_products": [],
                    "confidence": 0.0, "escalate_to_human": True}
