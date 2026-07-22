"""Shared plain-data contracts for the deterministic services. No behavior, no LLM, no agent imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SKU:
    sku_id: str
    name: str
    category: str  # "supplies" | "livestock" | "veterinary"
    description: str
    unit_price_cents: int
    is_livestock: bool
    is_prescription: bool
    species: Optional[str] = None


@dataclass(frozen=True)
class CartItem:
    sku_id: str
    quantity: int


@dataclass(frozen=True)
class PriceBreakdown:
    subtotal_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int


@dataclass(frozen=True)
class PaymentResult:
    authorized: bool
    authorization_code: Optional[str]
    reason: Optional[str] = None


@dataclass(frozen=True)
class ShippingLabel:
    order_id: str
    carrier: str
    tracking_number: str
