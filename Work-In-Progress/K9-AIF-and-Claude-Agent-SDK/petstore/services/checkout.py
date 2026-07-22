"""
Checkout orchestration -- the deterministic path (project.md's Success
Criterion 1), now reused by both demo/walk_deterministic_order.py's
successor and the real web checkout endpoint, instead of being
duplicated inline in each.

This is also where the livestock gate first meets a real order: a cart
containing any livestock SKU stops at FULFILLING and waits for
GateRegistry approval, rather than auto-progressing to SHIPPED like a
supplies-only order does.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Coroutine, Dict, List, Optional

from petstore.gates import GateRegistryFactory, GateType
from petstore.services import fulfillment, inventory, order_state, payment, pricing
from petstore.services.models import CartItem
from petstore.services.order_state import OrderState


def _run_coro_sync(coro: "Coroutine[Any, Any, Any]") -> Any:
    """Same reasoning as petstore/abb/diagnosis.py's copy -- GateRegistry's
    methods are async; this service function is called synchronously."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass(frozen=True)
class CheckoutResult:
    order_id: str
    success: bool
    state: str
    total_cents: int
    reason: Optional[str] = None
    awaiting_gate_approval: bool = False
    gate_id: Optional[str] = None


def place_order(
    cart: List[CartItem],
    customer_id: str,
    payment_method: str,
    user_id: Optional[str] = None,
    gate_config: Optional[Dict[str, Any]] = None,
) -> CheckoutResult:
    for item in cart:
        if not inventory.check_stock(item.sku_id, item.quantity):
            order_id = order_state.create_order(customer_id, user_id=user_id)
            order_state.transition(order_id, OrderState.CANCELLED)
            return CheckoutResult(order_id=order_id, success=False, state=OrderState.CANCELLED.value,
                                   total_cents=0, reason=f"Insufficient stock for {item.sku_id}")

    breakdown = pricing.calculate_total(cart)
    order_id = order_state.create_order(customer_id, user_id=user_id)
    order_state.set_price_breakdown(order_id, breakdown.subtotal_cents, breakdown.tax_cents,
                                     breakdown.shipping_cents, breakdown.total_cents)

    for item in cart:
        sku = inventory.get_sku(item.sku_id)
        order_state.add_order_item(order_id, item.sku_id, item.quantity, sku.unit_price_cents)

    result = payment.authorize_payment(order_id, breakdown.total_cents, payment_method)
    if not result.authorized:
        order_state.transition(order_id, OrderState.CANCELLED)
        return CheckoutResult(order_id=order_id, success=False, state=OrderState.CANCELLED.value,
                               total_cents=breakdown.total_cents, reason=result.reason)

    order_state.transition(order_id, OrderState.PAYMENT_AUTHORIZED)
    for item in cart:
        inventory.decrement_stock(item.sku_id, item.quantity)
    order_state.transition(order_id, OrderState.FULFILLING)

    contains_livestock = any(
        (sku := inventory.get_sku(item.sku_id)) is not None and sku.is_livestock
        for item in cart
    )

    if contains_livestock:
        registry = GateRegistryFactory.create(gate_config)
        gate = _run_coro_sync(registry.request_approval(order_id, GateType.LIVESTOCK, context={
            "customer_id": customer_id, "total_cents": breakdown.total_cents,
        }))
        return CheckoutResult(order_id=order_id, success=True, state=OrderState.FULFILLING.value,
                               total_cents=breakdown.total_cents, awaiting_gate_approval=True,
                               gate_id=gate.gate_id)

    fulfillment.generate_shipping_label(order_id)
    order_state.transition(order_id, OrderState.SHIPPED)
    return CheckoutResult(order_id=order_id, success=True, state=OrderState.SHIPPED.value,
                           total_cents=breakdown.total_cents)


def complete_after_gate_approval(order_id: str) -> None:
    """Called once an admin approves a pending livestock gate -- the order
    was left sitting at FULFILLING by place_order() specifically so this
    step could happen later, out of band from the original request."""
    fulfillment.generate_shipping_label(order_id)
    order_state.transition(order_id, OrderState.SHIPPED)


def cancel_after_gate_rejection(order_id: str) -> None:
    order_state.transition(order_id, OrderState.CANCELLED)
