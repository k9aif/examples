"""
GateRegistry — SimpleGateRegistry (Phase 5 minimal implementation).

Not one of the five load-bearing tests in CLAUDE.md (those need the full
PreToolUse hook + SDK integration to exist first). This is a narrower,
earlier check: does the ABB contract behave correctly on its own, before
any agent or hook depends on it.
"""

import os
import tempfile

import pytest

from petstore.gates.base_gate_registry import BaseGateRegistry
from petstore.gates.gate_registry_factory import GateRegistryFactory
from petstore.gates.models import GateState, GateType


@pytest.fixture
def registry():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "gates.db")
        yield GateRegistryFactory.create({"gates": {"provider": "simple", "db_path": db_path}})


@pytest.mark.asyncio
async def test_new_order_starts_pending(registry):
    gate = await registry.status("order-1", GateType.LIVESTOCK)
    assert gate.state == GateState.PENDING


@pytest.mark.asyncio
async def test_resolve_flips_to_approved(registry):
    gate = await registry.status("order-2", GateType.LIVESTOCK)
    resolved = await registry.resolve(gate.gate_id, approved=True, approver="reviewer@example.com")
    assert resolved.state == GateState.APPROVED
    assert resolved.approver == "reviewer@example.com"
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_rejected(registry):
    gate = await registry.status("order-2b", GateType.LIVESTOCK)
    resolved = await registry.resolve(gate.gate_id, approved=False, approver="reviewer@example.com")
    assert resolved.state == GateState.REJECTED


@pytest.mark.asyncio
async def test_status_is_idempotent(registry):
    """Re-querying an unresolved order returns the same gate, not a new PENDING one each time."""
    first = await registry.status("order-3", GateType.LIVESTOCK)
    second = await registry.status("order-3", GateType.LIVESTOCK)
    assert first.gate_id == second.gate_id


@pytest.mark.asyncio
async def test_resolve_unknown_gate_raises(registry):
    with pytest.raises(KeyError):
        await registry.resolve("nonexistent-id", approved=True, approver="x")


@pytest.mark.asyncio
async def test_status_survives_a_fresh_query_object(registry):
    """
    Mirrors the compaction-safety claim in Architecture_Guide.md: gate
    state lives in external storage, not in any in-memory/session object.
    A brand new status() call against the same order sees the same state
    another 'process' set — here simulated by resolving via one call and
    reading via another on the same underlying store.
    """
    gate = await registry.status("order-4", GateType.LIVESTOCK)
    await registry.resolve(gate.gate_id, approved=True, approver="reviewer@example.com")
    reread = await registry.status("order-4", GateType.LIVESTOCK)
    assert reread.state == GateState.APPROVED


def test_factory_returns_a_base_gate_registry():
    instance = GateRegistryFactory.get("simple", config={"gates": {"db_path": ":memory:"}})
    assert isinstance(instance, BaseGateRegistry)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        GateRegistryFactory.get("nonexistent_provider")
