"""Shipping label generation (template fill) and order status query (database read). project.md §3."""

from __future__ import annotations

import hashlib
from typing import Optional

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
