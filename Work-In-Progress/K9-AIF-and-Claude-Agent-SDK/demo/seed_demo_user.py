#!/usr/bin/env python3
"""
Seed a demo/demo user account with sample orders across different
states, so a visitor can log in immediately and see real order history
instead of starting from an empty account.

Idempotent -- safe to run more than once: reuses the existing demo
account if already registered, and only adds orders the first time
(checks for existing orders before seeding more).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from petstore.gates import GateRegistryFactory, GateType
from petstore.services import auth, checkout, fulfillment, inventory
from petstore.services.db import get_cursor
from petstore.services.models import CartItem, SKU
from petstore.services.original_catalog_data import (
    original_catalog_skus,
    original_catalog_stock,
)

_DEMO_EMAIL = "demo"
_DEMO_PASSWORD = "demo"
_DEMO_NAME = "Demo"

_SUPPLY_SKUS = [
    SKU("SUP-FOOD-01", "Tropical Fish Flakes (200g)", "supplies",
        "Balanced daily flake food for tropical fish.", 899, False, False),
    SKU("SUP-FILT-01", "50-Gallon Canister Filter", "supplies",
        "Whisper-quiet canister filter for tanks up to 50 gallons.", 4599, False, False),
    SKU("SUP-TOY-01", "Cat Feather Wand", "supplies",
        "Interactive feather wand toy.", 699, False, False),
]


def _get_or_create_demo_user() -> str:
    with get_cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE email = %s", (_DEMO_EMAIL,))
        row = cur.fetchone()
    if row:
        print(f"Demo user already exists (user_id={row[0]})")
        return str(row[0])
    user_id = auth.register_user(_DEMO_EMAIL, _DEMO_PASSWORD, _DEMO_NAME)
    print(f"Demo user created: {_DEMO_EMAIL}/{_DEMO_PASSWORD} (user_id={user_id})")
    return user_id


def _demo_already_has_orders(user_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", (user_id,))
        return cur.fetchone()[0] > 0


def main() -> None:
    inventory.seed_catalog(_SUPPLY_SKUS, stock_by_sku={
        "SUP-FOOD-01": 50, "SUP-FILT-01": 12, "SUP-TOY-01": 30,
    })
    inventory.seed_catalog(original_catalog_skus(), original_catalog_stock())

    user_id = _get_or_create_demo_user()

    if _demo_already_has_orders(user_id):
        print("Demo user already has sample orders -- not adding more. "
              "Delete existing orders first if you want to reseed.")
        return

    print("\nPlacing sample orders...")

    # 1. Auto-shipped supplies order.
    r1 = checkout.place_order(
        cart=[CartItem("SUP-FOOD-01", 2), CartItem("SUP-TOY-01", 1)],
        customer_id=_DEMO_EMAIL, payment_method="4111-1111-1111-1234", user_id=user_id,
    )
    print(f"  Order {r1.order_id[:8]}... -- supplies -- state={r1.state}")

    # 2. Another auto-shipped supplies order, further along (mark delivered).
    r2 = checkout.place_order(
        cart=[CartItem("SUP-FILT-01", 1)],
        customer_id=_DEMO_EMAIL, payment_method="4111-1111-1111-1234", user_id=user_id,
    )
    from petstore.services import order_state
    from petstore.services.order_state import OrderState
    order_state.transition(r2.order_id, OrderState.DELIVERED)
    print(f"  Order {r2.order_id[:8]}... -- supplies -- state=delivered")

    # 3. Livestock order awaiting admin gate approval.
    r3 = checkout.place_order(
        cart=[CartItem("EST-18", 1)],  # Amazon Parrot
        customer_id=_DEMO_EMAIL, payment_method="4111-1111-1111-1234", user_id=user_id,
    )
    print(f"  Order {r3.order_id[:8]}... -- Amazon Parrot (livestock) -- "
          f"state={r3.state}, awaiting_gate_approval={r3.awaiting_gate_approval}")

    # 4. A declined-payment cancelled order, for variety.
    r4 = checkout.place_order(
        cart=[CartItem("SUP-FOOD-01", 1)],
        customer_id=_DEMO_EMAIL, payment_method="4111-0000", user_id=user_id,
    )
    print(f"  Order {r4.order_id[:8]}... -- declined payment -- state={r4.state}")

    print(f"\nDone. Log in at /login with {_DEMO_EMAIL}/{_DEMO_PASSWORD} to see order history.")
    print("(Order 3's livestock gate is still pending -- log in as an admin to approve/reject it.)")


if __name__ == "__main__":
    main()
