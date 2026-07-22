"""
Petstore's own routing vocabulary -- NOT a K9-AIF framework primitive.

project.md §4 assumed the framework shipped a HandlerResult/SHORT_CIRCUIT/
RESOLVED/CONTINUE disposition enum for chain-of-responsibility routing. It
doesn't -- verified by grepping the installed k9_aif_abb package tree; see
DEVIATIONS.md #7. The real BaseRouter contract is just
`route(payload: dict) -> dict`, which permits any dict shape in return.
This module defines Petstore's own disposition vocabulary on top of that
contract, kept separate so it's never mistaken for framework behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class Disposition(str, Enum):
    SHORT_CIRCUIT = "short_circuit"  # resolved here, no agent involved
    CONTINUE = "continue"            # no deterministic handler claimed it


@dataclass(frozen=True)
class HandlerResult:
    disposition: Disposition
    handler_name: str
    response: Dict[str, Any] = field(default_factory=dict)
