"""Inventory — fixed query, fixed result. No model involved (project.md §3)."""

from __future__ import annotations

from typing import Optional

from petstore.services.db import get_cursor
from petstore.services.models import SKU


def get_sku(sku_id: str) -> Optional[SKU]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT sku_id, name, category, description, unit_price_cents, "
            "is_livestock, is_prescription, species FROM sku WHERE sku_id = %s",
            (sku_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return SKU(
        sku_id=row[0], name=row[1], category=row[2], description=row[3],
        unit_price_cents=row[4], is_livestock=row[5], is_prescription=row[6],
        species=row[7],
    )


def search_by_keyword(query: str, limit: int = 10) -> list[SKU]:
    """Fixed query (case-insensitive substring over name/description/category),
    fixed result -- a database read, not a ranking problem. See project.md §3."""
    like = f"%{query.lower()}%"
    with get_cursor() as cur:
        cur.execute(
            "SELECT sku_id, name, category, description, unit_price_cents, "
            "is_livestock, is_prescription, species FROM sku "
            "WHERE lower(name) LIKE %s OR lower(description) LIKE %s OR lower(category) LIKE %s "
            "ORDER BY name LIMIT %s",
            (like, like, like, limit),
        )
        rows = cur.fetchall()
    return [
        SKU(sku_id=r[0], name=r[1], category=r[2], description=r[3], unit_price_cents=r[4],
            is_livestock=r[5], is_prescription=r[6], species=r[7])
        for r in rows
    ]


def check_stock(sku_id: str, quantity: int) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT quantity_on_hand FROM inventory WHERE sku_id = %s", (sku_id,))
        row = cur.fetchone()
    return row is not None and row[0] >= quantity


def decrement_stock(sku_id: str, quantity: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE inventory SET quantity_on_hand = quantity_on_hand - %s, "
            "updated_at = now() WHERE sku_id = %s AND quantity_on_hand >= %s",
            (quantity, sku_id, quantity),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Insufficient stock for {sku_id}")


def seed_catalog(skus: list[SKU], stock_by_sku: dict[str, int]) -> None:
    """Convenience for demo/test setup — not part of the runtime request path."""
    with get_cursor(commit=True) as cur:
        for sku in skus:
            cur.execute(
                "INSERT INTO sku (sku_id, name, category, description, unit_price_cents, "
                "is_livestock, is_prescription, species) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (sku_id) DO NOTHING",
                (sku.sku_id, sku.name, sku.category, sku.description, sku.unit_price_cents,
                 sku.is_livestock, sku.is_prescription, sku.species),
            )
            qty = stock_by_sku.get(sku.sku_id, 0)
            cur.execute(
                "INSERT INTO inventory (sku_id, quantity_on_hand) VALUES (%s, %s) "
                "ON CONFLICT (sku_id) DO UPDATE SET quantity_on_hand = EXCLUDED.quantity_on_hand",
                (sku.sku_id, qty),
            )
