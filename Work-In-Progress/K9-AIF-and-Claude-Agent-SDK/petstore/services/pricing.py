"""Cart total / tax / shipping — arithmetic. No model involved (project.md §3)."""

from __future__ import annotations

from typing import List

from petstore.services import inventory
from petstore.services.models import CartItem, PriceBreakdown

_TAX_RATE = 0.08
_FLAT_SHIPPING_CENTS = 599
_FREE_SHIPPING_THRESHOLD_CENTS = 5000


def calculate_total(items: List[CartItem]) -> PriceBreakdown:
    subtotal = 0
    for item in items:
        sku = inventory.get_sku(item.sku_id)
        if sku is None:
            raise ValueError(f"Unknown SKU: {item.sku_id}")
        subtotal += sku.unit_price_cents * item.quantity

    tax = round(subtotal * _TAX_RATE)
    shipping = 0 if subtotal >= _FREE_SHIPPING_THRESHOLD_CENTS else _FLAT_SHIPPING_CENTS
    total = subtotal + tax + shipping

    return PriceBreakdown(
        subtotal_cents=subtotal, tax_cents=tax,
        shipping_cents=shipping, total_cents=total,
    )
