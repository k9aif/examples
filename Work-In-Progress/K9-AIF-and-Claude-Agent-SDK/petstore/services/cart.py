"""
Shopping cart -- keyed by an anonymous cart-session token, not by user_id.
Works identically for guests and logged-in users. Deliberately does not
merge a guest cart into an account's cart on login (a real classic
e-commerce edge case; out of scope for this build, see PLAN.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from petstore.services import inventory
from petstore.services.db import get_cursor
from petstore.services.models import CartItem, SKU


@dataclass(frozen=True)
class CartLine:
    sku: SKU
    quantity: int

    @property
    def subtotal_cents(self) -> int:
        return self.sku.unit_price_cents * self.quantity


def add_item(cart_session_id: str, sku_id: str, quantity: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO cart_items (cart_session_id, sku_id, quantity) VALUES (%s, %s, %s) "
            "ON CONFLICT (cart_session_id, sku_id) DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity",
            (cart_session_id, sku_id, quantity),
        )


def remove_item(cart_session_id: str, sku_id: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM cart_items WHERE cart_session_id = %s AND sku_id = %s",
            (cart_session_id, sku_id),
        )


def update_quantity(cart_session_id: str, sku_id: str, quantity: int) -> None:
    if quantity <= 0:
        remove_item(cart_session_id, sku_id)
        return
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE cart_items SET quantity = %s WHERE cart_session_id = %s AND sku_id = %s",
            (quantity, cart_session_id, sku_id),
        )


def get_cart(cart_session_id: str) -> List[CartLine]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT sku_id, quantity FROM cart_items WHERE cart_session_id = %s ORDER BY added_at",
            (cart_session_id,),
        )
        rows = cur.fetchall()

    lines = []
    for sku_id, quantity in rows:
        sku = inventory.get_sku(sku_id)
        if sku is not None:
            lines.append(CartLine(sku=sku, quantity=quantity))
    return lines


def get_item_count(cart_session_id: str) -> int:
    with get_cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM cart_items WHERE cart_session_id = %s",
            (cart_session_id,),
        )
        return cur.fetchone()[0]


def clear_cart(cart_session_id: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM cart_items WHERE cart_session_id = %s", (cart_session_id,))


def as_checkout_items(cart_session_id: str) -> List[CartItem]:
    """Convert the cart's contents into the plain CartItem list checkout.place_order() expects."""
    return [CartItem(line.sku.sku_id, line.quantity) for line in get_cart(cart_session_id)]
