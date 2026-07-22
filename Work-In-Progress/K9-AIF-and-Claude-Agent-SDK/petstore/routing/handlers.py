"""
Deterministic handlers -- each one is a fixed query against
petstore/services/, never an agent. A handler returns None if it doesn't
recognize the request (the router tries the next one), or a HandlerResult
if it claims and resolves it.

project.md's own table (§3) of what's deterministic vs. genuinely uncertain
is the spec for what belongs here: order status, inventory lookup, cart
operations, return eligibility, product search. None of it is knowable-in-
advance the way customer problem diagnosis is -- every one of these is a
database read, arithmetic, or a fixed small rule.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from petstore.routing.dispositions import Disposition, HandlerResult
from petstore.services import cart, fulfillment, inventory
from petstore.services.order_state import OrderState

_RETURN_ELIGIBLE_STATES = {OrderState.DELIVERED.value}


def order_status_handler(payload: Dict[str, Any]) -> Optional[HandlerResult]:
    if payload.get("event_type") != "order_status":
        return None
    order_id = payload.get("order_id", "")
    status = fulfillment.get_order_status(order_id)
    if status is None:
        response = {"found": False, "order_id": order_id}
    else:
        response = {"found": True, **status}
    return HandlerResult(Disposition.SHORT_CIRCUIT, "order_status_handler", response)


def inventory_lookup_handler(payload: Dict[str, Any]) -> Optional[HandlerResult]:
    if payload.get("event_type") != "inventory_lookup":
        return None
    sku_id = payload.get("sku_id", "")
    sku = inventory.get_sku(sku_id)
    if sku is None:
        response = {"found": False, "sku_id": sku_id}
    else:
        in_stock = inventory.check_stock(sku_id, quantity=1)
        response = {"found": True, "sku_id": sku.sku_id, "name": sku.name,
                    "unit_price_cents": sku.unit_price_cents, "in_stock": in_stock}
    return HandlerResult(Disposition.SHORT_CIRCUIT, "inventory_lookup_handler", response)


_CART_EVENT_TYPES = {"cart_view", "cart_add", "cart_remove", "cart_update"}


def cart_handler(payload: Dict[str, Any]) -> Optional[HandlerResult]:
    event_type = payload.get("event_type")
    if event_type not in _CART_EVENT_TYPES:
        return None

    cart_session_id = payload.get("cart_session_id", "")

    if event_type == "cart_add":
        cart.add_item(cart_session_id, payload["sku_id"], payload.get("quantity", 1))
    elif event_type == "cart_remove":
        cart.remove_item(cart_session_id, payload["sku_id"])
    elif event_type == "cart_update":
        cart.update_quantity(cart_session_id, payload["sku_id"], payload["quantity"])
    # cart_view falls straight through to the read below

    lines = cart.get_cart(cart_session_id)
    response = {
        "item_count": sum(line.quantity for line in lines),
        "lines": [{"sku_id": line.sku.sku_id, "name": line.sku.name,
                    "quantity": line.quantity, "subtotal_cents": line.subtotal_cents}
                  for line in lines],
    }
    return HandlerResult(Disposition.SHORT_CIRCUIT, "cart_handler", response)


def return_eligibility_handler(payload: Dict[str, Any]) -> Optional[HandlerResult]:
    """Simplified demo rule: DELIVERED orders are return-eligible, everything
    else isn't. A real return-policy engine could be arbitrarily more complex
    (return windows, restocking fees, no-return categories) but it would
    still be a rule evaluated against fixed data, not a judgment call."""
    if payload.get("event_type") != "return_eligibility":
        return None
    order_id = payload.get("order_id", "")
    status = fulfillment.get_order_status(order_id)
    if status is None:
        response = {"found": False, "order_id": order_id, "eligible": False}
    else:
        response = {
            "found": True, "order_id": order_id, "state": status["state"],
            "eligible": status["state"] in _RETURN_ELIGIBLE_STATES,
        }
    return HandlerResult(Disposition.SHORT_CIRCUIT, "return_eligibility_handler", response)


def product_search_handler(payload: Dict[str, Any]) -> Optional[HandlerResult]:
    if payload.get("event_type") != "product_search":
        return None
    query = payload.get("query", "")
    results = inventory.search_by_keyword(query)
    response = {
        "query": query,
        "results": [{"sku_id": s.sku_id, "name": s.name, "category": s.category,
                     "unit_price_cents": s.unit_price_cents} for s in results],
    }
    return HandlerResult(Disposition.SHORT_CIRCUIT, "product_search_handler", response)


# Registration order is the architectural argument (project.md §4): every
# deterministic handler is tried, in this order, before anything reaches
# an agent. Visible in one place rather than scattered across registrations.
DETERMINISTIC_HANDLERS = [
    order_status_handler,
    inventory_lookup_handler,
    cart_handler,
    return_eligibility_handler,
    product_search_handler,
]
