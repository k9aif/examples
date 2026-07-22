"""
Order state transitions — a finite state machine with enumerated
transitions (project.md §3). Not a general workflow engine: the legal
transition set is fixed and small, and enforcing it is the entire point —
an "impossible" transition is a bug to raise on, not a case to handle.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from petstore.services.db import get_cursor


class OrderState(str, Enum):
    CREATED = "created"
    PAYMENT_AUTHORIZED = "payment_authorized"
    FULFILLING = "fulfilling"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


_LEGAL_TRANSITIONS: Dict[OrderState, List[OrderState]] = {
    OrderState.CREATED: [OrderState.PAYMENT_AUTHORIZED, OrderState.CANCELLED],
    OrderState.PAYMENT_AUTHORIZED: [OrderState.FULFILLING, OrderState.CANCELLED],
    OrderState.FULFILLING: [OrderState.SHIPPED],
    OrderState.SHIPPED: [OrderState.DELIVERED],
    OrderState.DELIVERED: [],
    OrderState.CANCELLED: [],
}


class IllegalTransitionError(ValueError):
    pass


def create_order(customer_id: str) -> str:
    order_id = str(uuid4())
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO orders (order_id, customer_id, state) VALUES (%s, %s, %s)",
            (order_id, customer_id, OrderState.CREATED.value),
        )
        cur.execute(
            "INSERT INTO order_state_history (order_id, from_state, to_state) VALUES (%s, %s, %s)",
            (order_id, None, OrderState.CREATED.value),
        )
    return order_id


def get_state(order_id: str) -> Optional[OrderState]:
    with get_cursor() as cur:
        cur.execute("SELECT state FROM orders WHERE order_id = %s", (order_id,))
        row = cur.fetchone()
    return OrderState(row[0]) if row else None


def transition(order_id: str, to_state: OrderState) -> None:
    current = get_state(order_id)
    if current is None:
        raise ValueError(f"No such order: {order_id}")

    if to_state not in _LEGAL_TRANSITIONS[current]:
        raise IllegalTransitionError(
            f"Cannot transition order {order_id} from {current.value} to {to_state.value}"
        )

    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE orders SET state = %s, updated_at = now() WHERE order_id = %s",
            (to_state.value, order_id),
        )
        cur.execute(
            "INSERT INTO order_state_history (order_id, from_state, to_state) VALUES (%s, %s, %s)",
            (order_id, current.value, to_state.value),
        )


def set_price_breakdown(order_id: str, subtotal_cents: int, tax_cents: int,
                         shipping_cents: int, total_cents: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE orders SET subtotal_cents = %s, tax_cents = %s, "
            "shipping_cents = %s, total_cents = %s, updated_at = now() WHERE order_id = %s",
            (subtotal_cents, tax_cents, shipping_cents, total_cents, order_id),
        )


def add_order_item(order_id: str, sku_id: str, quantity: int, unit_price_cents: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO order_items (order_id, sku_id, quantity, unit_price_cents_at_order) "
            "VALUES (%s, %s, %s, %s)",
            (order_id, sku_id, quantity, unit_price_cents),
        )
