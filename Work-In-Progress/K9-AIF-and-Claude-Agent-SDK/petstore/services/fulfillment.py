"""Shipping label generation (template fill) and order status query (database read). project.md §3."""

from __future__ import annotations

import hashlib
from typing import List, Optional

from petstore.services.db import get_cursor
from petstore.services.models import ShippingLabel

_CARRIER = "PetStoreExpress"


def generate_shipping_label(order_id: str) -> ShippingLabel:
    tracking_number = hashlib.sha1(order_id.encode()).hexdigest()[:16].upper()
    label = ShippingLabel(order_id=order_id, carrier=_CARRIER, tracking_number=tracking_number)
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO shipping_labels (order_id, carrier, tracking_number) VALUES (%s, %s, %s) "
            "ON CONFLICT (order_id) DO NOTHING",
            (label.order_id, label.carrier, label.tracking_number),
        )
    return label


def get_order_status(order_id: str) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT state, subtotal_cents, tax_cents, shipping_cents, total_cents, "
            "created_at, updated_at FROM orders WHERE order_id = %s",
            (order_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "order_id": order_id,
        "state": row[0],
        "subtotal_cents": row[1],
        "tax_cents": row[2],
        "shipping_cents": row[3],
        "total_cents": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


def get_order_history_for_user(user_id: str) -> List[dict]:
    """Order history for the user portal -- guest orders (user_id NULL) never appear here."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT order_id, state, total_cents, created_at FROM orders "
            "WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        rows = cur.fetchall()
    return [
        {"order_id": str(r[0]), "state": r[1], "total_cents": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_all_orders() -> List[dict]:
    """All orders, guest and logged-in alike -- for the admin portal."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT order_id, customer_id, user_id, state, total_cents, created_at "
            "FROM orders ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
    return [
        {"order_id": str(r[0]), "customer_id": r[1], "user_id": str(r[2]) if r[2] else None,
         "state": r[3], "total_cents": r[4], "created_at": r[5]}
        for r in rows
    ]
