"""
ABB contract for gate state.

External to agent context by design — a PreToolUse hook queries this
directly on every tool invocation, so gate state survives context
compaction (see Architecture_Guide.md, "Governance lives in the harness,
not the prompt"). Multiple implementations may satisfy this contract;
which approval mechanism actually resolves a gate (a test fixture, a
CLI command, a real human-review queue) is a substrate decision, not
part of the contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from petstore.gates.models import Gate, GateType


class BaseGateRegistry(ABC):

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}

    @abstractmethod
    async def status(self, order_id: str, gate_type: GateType) -> Gate:
        """Return the current Gate for this order/gate_type, creating a PENDING one if none exists."""

    @abstractmethod
    async def request_approval(
        self, order_id: str, gate_type: GateType, context: Dict[str, Any]
    ) -> Gate:
        """Create (or return the existing) PENDING gate for this order/gate_type."""

    @abstractmethod
    async def resolve(self, gate_id: str, approved: bool, approver: str) -> Gate:
        """Flip a gate to APPROVED or REJECTED. Called by whatever approval mechanism the adapter uses."""

    @abstractmethod
    async def list_pending(self, gate_type: Optional[GateType] = None) -> List[Gate]:
        """All gates currently PENDING, optionally filtered by gate_type -- an admin review queue."""
