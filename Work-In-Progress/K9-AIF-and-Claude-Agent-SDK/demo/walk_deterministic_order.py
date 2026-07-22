#!/usr/bin/env python3
"""
Phase 1 demo — a complete, non-livestock order, start to finish, with zero
LLM calls anywhere in the path. This is Success Criterion 1 from project.md
§13, made runnable: "Confirm the order pipeline contains no LLM calls, by
reading the code" — run this and watch it happen instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from petstore.services import fulfillment, inventory, order_state, payment, pricing
from petstore.services.models import CartItem, SKU
from petstore.services.order_state import OrderState


def _seed_demo_catalog() -> None:
    skus = [
        SKU("SUP-FOOD-01", "Tropical Fish Flakes (200g)", "supplies",
            "Balanced daily flake food for tropical fish.", 899, False, False),
        SKU("SUP-FILT-01", "50-Gallon Canister Filter", "supplies",
            "Whisper-quiet canister filter for tanks up to 50 gallons.", 4599, False, False),
        SKU("SUP-TOY-01", "Cat Feather Wand", "supplies",
            "Interactive feather wand toy.", 699, False, False),
    ]
    inventory.seed_catalog(skus, stock_by_sku={
        "SUP-FOOD-01": 50, "SUP-FILT-01": 12, "SUP-TOY-01": 30,
    })


def main() -> None:
    print("=" * 70)
    print("Pet Store Agentic -- Phase 1: Deterministic Order Walkthrough")
    print("(No agent, no LLM, no SDK anywhere in this path.)")
    print("=" * 70)

    _seed_demo_catalog()

    cart = [
        CartItem("SUP-FOOD-01", quantity=2),
        CartItem("SUP-FILT-01", quantity=1),
    ]
    print(f"\n1. Cart: {cart}")

    for item in cart:
        ok = inventory.check_stock(item.sku_id, item.quantity)
        print(f"   check_stock({item.sku_id}, {item.quantity}) -> {ok}")
        if not ok:
            print("   Insufficient stock -- aborting.")
            return

    breakdown = pricing.calculate_total(cart)
    print(f"\n2. Pricing: {breakdown}")

    order_id = order_state.create_order(customer_id="demo-customer-001")
    print(f"\n3. Order created: {order_id} (state={order_state.get_state(order_id).value})")

    order_state.set_price_breakdown(
        order_id, breakdown.subtotal_cents, breakdown.tax_cents,
        breakdown.shipping_cents, breakdown.total_cents,
    )
    for item in cart:
        sku = inventory.get_sku(item.sku_id)
        order_state.add_order_item(order_id, item.sku_id, item.quantity, sku.unit_price_cents)

    payment_result = payment.authorize_payment(
        order_id, breakdown.total_cents, payment_method="4111-1111-1111-1234"
    )
    print(f"\n4. Payment: {payment_result}")
    if not payment_result.authorized:
        order_state.transition(order_id, OrderState.CANCELLED)
        print(f"   Payment declined -- order cancelled (state={order_state.get_state(order_id).value})")
        return

    order_state.transition(order_id, OrderState.PAYMENT_AUTHORIZED)
    print(f"\n5. State -> {order_state.get_state(order_id).value}")

    for item in cart:
        inventory.decrement_stock(item.sku_id, item.quantity)
    print("   Stock decremented for all items.")

    order_state.transition(order_id, OrderState.FULFILLING)
    print(f"\n6. State -> {order_state.get_state(order_id).value}")

    label = fulfillment.generate_shipping_label(order_id)
    print(f"   Shipping label: {label}")

    order_state.transition(order_id, OrderState.SHIPPED)
    print(f"\n7. State -> {order_state.get_state(order_id).value}")

    order_state.transition(order_id, OrderState.DELIVERED)
    print(f"\n8. State -> {order_state.get_state(order_id).value}")

    status = fulfillment.get_order_status(order_id)
    print(f"\n9. Final order status (database read): {status}")

    print("\n" + "=" * 70)
    print("Done. Zero LLM calls. Zero agent invocations. Just deterministic code.")
    print("=" * 70)


if __name__ == "__main__":
    main()
