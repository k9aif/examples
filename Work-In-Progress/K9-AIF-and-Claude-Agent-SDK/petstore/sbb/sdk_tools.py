"""
Tools exposed to the Claude Agent SDK session in SdkDiagnosisAgent.

Lives in petstore/sbb/, not petstore/services/ -- these wrap the SDK's
@tool decorator, which is exactly the kind of import
test_deterministic_purity.py forbids inside services/. The underlying
deterministic services stay pure; only this SBB-layer wrapper touches
the SDK.
"""

from __future__ import annotations

from typing import Any, Dict

from claude_agent_sdk import tool

from petstore.services import inventory

# initiate_fulfillment isn't a diagnosis capability -- it's included here
# specifically so the livestock gate (project.md §6) has a concrete tool
# call to enforce against, matching the adversarial test scenario described
# there. See DEVIATIONS.md #5.
FULFILLMENT_TOOL_NAME = "initiate_fulfillment"


@tool("search_catalog", "Search the pet store catalog by keyword.", {"query": str})
async def search_catalog(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "").lower()
    # Deliberately simple substring match over whatever's seeded --
    # this is a diagnosis aid, not a search engine.
    with_matches = []
    for sku_id in _known_demo_skus():
        sku = inventory.get_sku(sku_id)
        if sku and query in sku.name.lower():
            with_matches.append({"sku_id": sku.sku_id, "name": sku.name})
    return {"content": [{"type": "text", "text": str(with_matches)}]}


@tool("check_species_compatibility", "Check whether a treatment or product is safe for a given species.",
      {"species": str, "product_query": str})
async def check_species_compatibility(args: Dict[str, Any]) -> Dict[str, Any]:
    # Deliberately conservative placeholder -- a real implementation would
    # consult a species/product compatibility table. Returning "unknown"
    # rather than fabricating an authoritative-sounding yes/no.
    return {"content": [{"type": "text", "text": "compatibility data not available in this demo"}]}


@tool("retrieve_care_guide", "Retrieve general care guidance for a species or situation.", {"topic": str})
async def retrieve_care_guide(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": [{"type": "text",
            "text": f"No structured care guide database in this demo build for: {args.get('topic')}"}]}


@tool("check_inventory", "Check current stock level for a SKU.", {"sku_id": str})
async def check_inventory(args: Dict[str, Any]) -> Dict[str, Any]:
    sku_id = args.get("sku_id", "")
    sku = inventory.get_sku(sku_id)
    if sku is None:
        return {"content": [{"type": "text", "text": f"Unknown SKU: {sku_id}"}]}
    in_stock = inventory.check_stock(sku_id, quantity=1)
    return {"content": [{"type": "text", "text": f"{sku_id} in stock: {in_stock}"}]}


@tool(FULFILLMENT_TOOL_NAME, "Initiate fulfillment for an order. Gated for livestock orders.",
      {"order_id": str})
async def initiate_fulfillment(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reaching this function body means can_use_tool already allowed the
    call -- the livestock gate lives in SdkDiagnosisAgent's can_use_tool
    callback, evaluated before this ever runs (project.md §6).
    """
    return {"content": [{"type": "text",
            "text": f"Fulfillment initiated for order {args.get('order_id')}"}]}


def _known_demo_skus() -> list[str]:
    # Placeholder finite list for the demo tool -- a real search_catalog
    # would query the catalog table directly rather than enumerate.
    return ["SUP-FOOD-01", "SUP-FILT-01", "SUP-TOY-01"]
