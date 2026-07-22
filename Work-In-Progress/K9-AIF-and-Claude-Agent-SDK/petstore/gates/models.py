"""State contracts for gate enforcement — no execution logic, deliberately."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class GateType(str, Enum):
    LIVESTOCK = "livestock"


class GateState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Gate:
    gate_id: str
    order_id: str
    gate_type: GateType
    state: GateState
    context: Dict[str, Any]
    approver: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
