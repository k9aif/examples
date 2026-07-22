"""Shopping cart -- keyed by an anonymous cart-session token, same for guests and logged-in users."""

from __future__ import annotations

import uuid

import pytest

from petstore.services import cart, inventory
from petstore.services.models import SKU


@pytest.fixture(autouse=True)
def _seeded_items():
    unique = uuid.uuid4().hex[:6]
    sku_a = f"TEST-CART-A-{unique}"
    sku_b = f"TEST-CART-B-{unique}"
    inventory.seed_catalog(
        [
            SKU(sku_a, "Test Item A", "supplies", "desc", 500, False, False),
            SKU(sku_b, "Test Item B", "supplies", "desc", 1200, False, False),
        ],
        stock_by_sku={sku_a: 20, sku_b: 20},
    )
    return {"sku_a": sku_a, "sku_b": sku_b}


def _cart_session() -> str:
    return f"test-cart-{uuid.uuid4().hex}"


def test_add_item_appears_in_cart(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 2)

    lines = cart.get_cart(session)
    assert len(lines) == 1
    assert lines[0].sku.sku_id == _seeded_items["sku_a"]
    assert lines[0].quantity == 2
    assert lines[0].subtotal_cents == 1000


def test_adding_same_sku_twice_accumulates_quantity(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 1)
    cart.add_item(session, _seeded_items["sku_a"], 2)

    lines = cart.get_cart(session)
    assert len(lines) == 1
    assert lines[0].quantity == 3


def test_remove_item(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 1)
    cart.add_item(session, _seeded_items["sku_b"], 1)

    cart.remove_item(session, _seeded_items["sku_a"])

    lines = cart.get_cart(session)
    assert len(lines) == 1
    assert lines[0].sku.sku_id == _seeded_items["sku_b"]


def test_update_quantity_to_zero_removes_item(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 3)

    cart.update_quantity(session, _seeded_items["sku_a"], 0)

    assert cart.get_cart(session) == []


def test_get_item_count_sums_quantities(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 2)
    cart.add_item(session, _seeded_items["sku_b"], 3)

    assert cart.get_item_count(session) == 5


def test_clear_cart(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 1)

    cart.clear_cart(session)

    assert cart.get_cart(session) == []
    assert cart.get_item_count(session) == 0


def test_carts_are_isolated_by_session(_seeded_items):
    session_1 = _cart_session()
    session_2 = _cart_session()
    cart.add_item(session_1, _seeded_items["sku_a"], 1)

    assert len(cart.get_cart(session_1)) == 1
    assert len(cart.get_cart(session_2)) == 0


def test_as_checkout_items_matches_checkout_cart_item_shape(_seeded_items):
    session = _cart_session()
    cart.add_item(session, _seeded_items["sku_a"], 2)
    cart.add_item(session, _seeded_items["sku_b"], 1)

    items = cart.as_checkout_items(session)
    assert {(i.sku_id, i.quantity) for i in items} == {
        (_seeded_items["sku_a"], 2), (_seeded_items["sku_b"], 1),
    }
