"""
Phase 5 minimal GateRegistry — SQLite-backed, no external dependencies,
no queue UI. resolve() is called directly (by a test, a CLI command, or
a minimal local endpoint) rather than through a real human-review queue.

See Detailed_Design.md for the K9x HIL-backed adapter this same
BaseGateRegistry contract is designed to support later, unchanged.
"""

from __future__ import annotations

import ast
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from petstore.gates.base_gate_registry import BaseGateRegistry
from petstore.gates.models import Gate, GateState, GateType


class SimpleGateRegistry(BaseGateRegistry):

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        db_path = self._config.get("db_path", "gates.db")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gates (
                gate_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                gate_type TEXT NOT NULL,
                state TEXT NOT NULL,
                context TEXT,
                approver TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """
        )
        self._conn.commit()

    async def status(self, order_id: str, gate_type: GateType) -> Gate:
        existing = self._find(order_id, gate_type)
        if existing:
            return existing
        return await self.request_approval(order_id, gate_type, context={})

    async def request_approval(
        self, order_id: str, gate_type: GateType, context: Dict[str, Any]
    ) -> Gate:
        existing = self._find(order_id, gate_type)
        if existing:
            return existing

        gate = Gate(
            gate_id=str(uuid.uuid4()),
            order_id=order_id,
            gate_type=gate_type,
            state=GateState.PENDING,
            context=context,
        )
        self._conn.execute(
            "INSERT INTO gates "
            "(gate_id, order_id, gate_type, state, context, approver, created_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                gate.gate_id,
                gate.order_id,
                gate.gate_type.value,
                gate.state.value,
                repr(gate.context),
                None,
                gate.created_at.isoformat(),
                None,
            ),
        )
        self._conn.commit()
        return gate

    async def resolve(self, gate_id: str, approved: bool, approver: str) -> Gate:
        row = self._conn.execute(
            "SELECT * FROM gates WHERE gate_id = ?", (gate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No gate with id {gate_id}")

        state = GateState.APPROVED if approved else GateState.REJECTED
        resolved_at = datetime.now(timezone.utc)
        self._conn.execute(
            "UPDATE gates SET state = ?, approver = ?, resolved_at = ? WHERE gate_id = ?",
            (state.value, approver, resolved_at.isoformat(), gate_id),
        )
        self._conn.commit()

        row = self._conn.execute(
            "SELECT * FROM gates WHERE gate_id = ?", (gate_id,)
        ).fetchone()
        return self._row_to_gate(row)

    async def list_pending(self, gate_type: Optional[GateType] = None) -> List[Gate]:
        if gate_type is not None:
            rows = self._conn.execute(
                "SELECT * FROM gates WHERE state = ? AND gate_type = ? ORDER BY created_at ASC",
                (GateState.PENDING.value, gate_type.value),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM gates WHERE state = ? ORDER BY created_at ASC",
                (GateState.PENDING.value,),
            ).fetchall()
        return [self._row_to_gate(row) for row in rows]

    def _find(self, order_id: str, gate_type: GateType) -> Optional[Gate]:
        row = self._conn.execute(
            "SELECT * FROM gates WHERE order_id = ? AND gate_type = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (order_id, gate_type.value),
        ).fetchone()
        return self._row_to_gate(row) if row else None

    @staticmethod
    def _row_to_gate(row: Tuple) -> Gate:
        gate_id, order_id, gate_type, state, context, approver, created_at, resolved_at = row
        return Gate(
            gate_id=gate_id,
            order_id=order_id,
            gate_type=GateType(gate_type),
            state=GateState(state),
            context=ast.literal_eval(context) if context else {},
            approver=approver,
            created_at=datetime.fromisoformat(created_at),
            resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
        )
