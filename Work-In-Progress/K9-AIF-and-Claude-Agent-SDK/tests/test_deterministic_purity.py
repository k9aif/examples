"""
Load-bearing test #1 (CLAUDE.md): "Deterministic paths need no agent."

Walks petstore/services/, parses the AST of every module, and fails if
any module imports an agent, an LLM/SDK client, or k9_aif_abb's agent
machinery. The import graph is the proof, not a docstring's claim --
this test is what makes that true rather than merely asserted.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVICES_DIR = Path(__file__).resolve().parents[1] / "petstore" / "services"

_FORBIDDEN_SUBSTRINGS = (
    "agent",
    "claude_agent_sdk",
    "anthropic",
    "openai",
    "llm_invoke",
    "k9_aif_abb.k9_agents",
    "k9_aif_abb.k9_inference",
)


def _service_modules() -> list[Path]:
    return sorted(_SERVICES_DIR.glob("*.py"))


def _imported_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("module_path", _service_modules(), ids=lambda p: p.name)
def test_no_forbidden_imports(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    imported = _imported_names(tree)

    violations = [
        name for name in imported
        if any(forbidden in name.lower() for forbidden in _FORBIDDEN_SUBSTRINGS)
    ]
    assert not violations, (
        f"{module_path.name} imports forbidden module(s): {violations} -- "
        "petstore/services/ must contain zero LLM/agent/SDK imports."
    )


def test_services_directory_is_not_empty() -> None:
    """Guard against this test silently passing over zero collected modules."""
    assert len(_service_modules()) >= 5, (
        "Expected at least the 5 services named in project.md §9 "
        "(inventory, pricing, payment, order_state, fulfillment)."
    )
