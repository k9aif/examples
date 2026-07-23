"""
PetstoreRouter -- proves the Phase 1 claim: ordinary storefront traffic
short-circuits at deterministic handlers and never reaches an agent, and
only unrecognized event_types fall through to CONTINUE (where an
Orchestrator would take over, once Phase 2 exists).
"""

from __future__ import annotations

import uuid

import pytest

from petstore.routing.dispositions import Disposition
from petstore.routing.handlers import DETERMINISTIC_HANDLERS
from petstore.routing.router import PetstoreRouter
from petstore.services import checkout, inventory
from petstore.services.models import CartItem, SKU
from petstore.services.order_state import OrderState


@pytest.fixture(autouse=True)
def _seeded_items():
    # Name includes the unique suffix too, not just the sku_id -- earlier runs'
    # seeded rows are never cleaned up, and search_by_keyword's LIMIT can push
    # this run's row out of a same-named result set otherwise (a real, observed
    # flake once enough "Test Router Fish Flakes" rows had accumulated).
    unique = uuid.uuid4().hex[:6]
    supply_sku = f"TEST-ROUTER-SUP-{unique}"
    inventory.seed_catalog(
        [SKU(supply_sku, f"Test Router Fish Flakes {unique}", "supplies", "desc", 500, False, False)],
        stock_by_sku={supply_sku: 20},
    )
    return {"supply_sku": supply_sku, "unique": unique}


@pytest.fixture
def router() -> PetstoreRouter:
    return PetstoreRouter()


def _cart_session() -> str:
    return f"test-router-cart-{uuid.uuid4().hex}"


def test_handler_order_is_deterministic_first_then_search_last():
    # The registration order itself is the architectural argument (project.md
    # §4) -- assert it's fixed and visible, not incidental.
    names = [h.__name__ for h in DETERMINISTIC_HANDLERS]
    assert names == [
        "order_status_handler",
        "inventory_lookup_handler",
        "cart_handler",
        "return_eligibility_handler",
        "product_search_handler",
    ]


def test_order_status_short_circuits(router, _seeded_items):
    order_id = checkout.place_order(
        cart=[CartItem(_seeded_items["supply_sku"], 1)],
        customer_id="router-test-cust", payment_method="4111-1111-1111-1234",
    ).order_id

    result = router.route({"event_type": "order_status", "order_id": order_id})

    assert result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert result["handler"] == "order_status_handler"
    assert result["response"]["found"] is True
    assert result["response"]["state"] == OrderState.SHIPPED.value


def test_order_status_unknown_id_still_short_circuits(router):
    result = router.route({"event_type": "order_status", "order_id": str(uuid.uuid4())})

    assert result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert result["response"]["found"] is False


def test_inventory_lookup_short_circuits(router, _seeded_items):
    result = router.route({"event_type": "inventory_lookup", "sku_id": _seeded_items["supply_sku"]})

    assert result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert result["handler"] == "inventory_lookup_handler"
    assert result["response"]["found"] is True
    assert result["response"]["in_stock"] is True


def test_cart_add_and_view_short_circuit(router, _seeded_items):
    session = _cart_session()

    add_result = router.route({
        "event_type": "cart_add", "cart_session_id": session,
        "sku_id": _seeded_items["supply_sku"], "quantity": 3,
    })
    assert add_result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert add_result["response"]["item_count"] == 3

    view_result = router.route({"event_type": "cart_view", "cart_session_id": session})
    assert view_result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert view_result["response"]["item_count"] == 3


def test_return_eligibility_false_for_shipped_order(router, _seeded_items):
    order_id = checkout.place_order(
        cart=[CartItem(_seeded_items["supply_sku"], 1)],
        customer_id="router-test-cust-2", payment_method="4111-1111-1111-1234",
    ).order_id

    result = router.route({"event_type": "return_eligibility", "order_id": order_id})

    assert result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert result["response"]["eligible"] is False  # SHIPPED, not DELIVERED


def test_return_eligibility_true_for_delivered_order(router, _seeded_items):
    from petstore.services import order_state

    order_id = checkout.place_order(
        cart=[CartItem(_seeded_items["supply_sku"], 1)],
        customer_id="router-test-cust-3", payment_method="4111-1111-1111-1234",
    ).order_id
    order_state.transition(order_id, OrderState.DELIVERED)

    result = router.route({"event_type": "return_eligibility", "order_id": order_id})

    assert result["response"]["eligible"] is True


def test_product_search_short_circuits(router, _seeded_items):
    result = router.route({"event_type": "product_search", "query": _seeded_items["unique"]})

    assert result["disposition"] == Disposition.SHORT_CIRCUIT.value
    assert _seeded_items["supply_sku"] in [r["sku_id"] for r in result["response"]["results"]]


def test_unrecognized_event_type_continues_not_short_circuits(router):
    # This is the fallthrough project.md §4 calls the architectural argument:
    # nothing here claims it, so it must not resolve as if something did.
    result = router.route({"event_type": "diagnose_my_pet", "narrative": "fish are gasping"})

    assert result["disposition"] == Disposition.CONTINUE.value
    assert result["payload"]["event_type"] == "diagnose_my_pet"


def test_majority_of_realistic_traffic_never_reaches_an_agent(router, _seeded_items):
    """The demo-visible claim: instrument the router, run a realistic mixed
    batch, and show most traffic short-circuits before any agent exists."""
    order_id = checkout.place_order(
        cart=[CartItem(_seeded_items["supply_sku"], 1)],
        customer_id="router-test-cust-4", payment_method="4111-1111-1111-1234",
    ).order_id
    session = _cart_session()

    realistic_batch = [
        {"event_type": "product_search", "query": "flakes"},
        {"event_type": "inventory_lookup", "sku_id": _seeded_items["supply_sku"]},
        {"event_type": "cart_add", "cart_session_id": session, "sku_id": _seeded_items["supply_sku"], "quantity": 1},
        {"event_type": "cart_view", "cart_session_id": session},
        {"event_type": "order_status", "order_id": order_id},
        {"event_type": "return_eligibility", "order_id": order_id},
        {"event_type": "order_status", "order_id": order_id},
        {"event_type": "diagnose_my_pet", "narrative": "tank's cloudy"},  # the one genuine agentic case
    ]
    for event in realistic_batch:
        router.route(event)

    stats = router.disposition_stats()
    assert stats["total"] == 8
    assert stats["counts"][Disposition.CONTINUE.value] == 1
    assert stats["counts"][Disposition.SHORT_CIRCUIT.value] == 7
    assert stats["short_circuit_fraction"] == pytest.approx(0.875)
