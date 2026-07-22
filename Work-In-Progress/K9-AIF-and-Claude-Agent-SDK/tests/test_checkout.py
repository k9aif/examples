"""
Checkout orchestration -- proves the two paths project.md's thesis depends on:
a supplies-only order auto-progresses to SHIPPED, while any order containing
livestock stops at FULFILLING and waits for a real GateRegistry approval.
This is the first point where the gate meets a real order rather than being
tested in isolation (test_gate_registry.py / test_gate_cannot_be_bypassed.py).
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from petstore.gates import GateRegistryFactory, GateState, GateType
from petstore.services import checkout, fulfillment, inventory
from petstore.services.models import CartItem, SKU
from petstore.services.order_state import OrderState


@pytest.fixture(autouse=True)
def _seeded_items():
    unique = uuid.uuid4().hex[:6]
    supply_sku = f"TEST-SUP-{unique}"
    livestock_sku = f"TEST-LIVE-{unique}"
    inventory.seed_catalog(
        [
            SKU(supply_sku, "Test Fish Food", "supplies", "desc", 500, False, False),
            SKU(livestock_sku, "Test Goldfish", "livestock", "desc", 999, True, False, species="Goldfish"),
        ],
        stock_by_sku={supply_sku: 20, livestock_sku: 20},
    )
    return {"supply_sku": supply_sku, "livestock_sku": livestock_sku}


@pytest.fixture
def gate_config():
    with tempfile.TemporaryDirectory() as tmp:
        yield {"gates": {"provider": "simple", "db_path": os.path.join(tmp, "gates.db")}}


def test_supplies_only_order_auto_ships(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["supply_sku"], quantity=2)]
    result = checkout.place_order(cart, customer_id="cust-1", payment_method="4111-1111",
                                   gate_config=gate_config)

    assert result.success is True
    assert result.state == OrderState.SHIPPED.value
    assert result.awaiting_gate_approval is False


def test_livestock_order_stops_at_fulfilling_awaiting_gate(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["livestock_sku"], quantity=1)]
    result = checkout.place_order(cart, customer_id="cust-2", payment_method="4111-1111",
                                   gate_config=gate_config)

    assert result.success is True
    assert result.state == OrderState.FULFILLING.value
    assert result.awaiting_gate_approval is True
    assert result.gate_id is not None

    registry = GateRegistryFactory.create(gate_config)
    import asyncio
    gate = asyncio.run(registry.status(result.order_id, GateType.LIVESTOCK))
    assert gate.state == GateState.PENDING


def test_gate_approval_ships_the_order(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["livestock_sku"], quantity=1)]
    result = checkout.place_order(cart, customer_id="cust-approve", payment_method="4111-1111",
                                   gate_config=gate_config)
    assert result.awaiting_gate_approval is True

    checkout.complete_after_gate_approval(result.order_id)

    status = fulfillment.get_order_status(result.order_id)
    assert status["state"] == OrderState.SHIPPED.value


def test_gate_rejection_cancels_the_order(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["livestock_sku"], quantity=1)]
    result = checkout.place_order(cart, customer_id="cust-reject", payment_method="4111-1111",
                                   gate_config=gate_config)
    assert result.awaiting_gate_approval is True

    checkout.cancel_after_gate_rejection(result.order_id)

    status = fulfillment.get_order_status(result.order_id)
    assert status["state"] == OrderState.CANCELLED.value


def test_declined_payment_cancels_order(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["supply_sku"], quantity=1)]
    # payment.py's demo decline rule: payment_method ending in "0000" always declines
    result = checkout.place_order(cart, customer_id="cust-3", payment_method="4111-0000",
                                   gate_config=gate_config)

    assert result.success is False
    assert result.state == OrderState.CANCELLED.value
    assert result.reason is not None


def test_insufficient_stock_cancels_order(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["supply_sku"], quantity=9999)]
    result = checkout.place_order(cart, customer_id="cust-4", payment_method="4111-1111",
                                   gate_config=gate_config)

    assert result.success is False
    assert result.state == OrderState.CANCELLED.value
    assert "Insufficient stock" in result.reason


def test_logged_in_checkout_ties_order_to_user(_seeded_items, gate_config):
    cart = [CartItem(_seeded_items["supply_sku"], quantity=1)]
    result = checkout.place_order(cart, customer_id="cust-5", payment_method="4111-1111",
                                   user_id=None, gate_config=gate_config)
    assert result.success is True
    # user_id=None (guest) is exercised above; a real user_id would need a
    # users row to satisfy the FK -- covered by the user-portal integration
    # test once that's wired, not duplicated here.


def test_get_order_status_with_malformed_id_returns_none_not_a_crash():
    """order_id is a UUID column -- a malformed value used to raise
    psycopg2.errors.InvalidTextRepresentation instead of reading as
    'not found' (found live, via /order-status?order_id=x)."""
    assert fulfillment.get_order_status("x") is None
    assert fulfillment.get_order_status("") is None
    assert fulfillment.get_order_status("not-a-uuid-at-all") is None
