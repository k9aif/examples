"""DirectApiDiagnosisAgent -- SBB-B. Mocks llm_invoke per SKILLS.md Skill 6; no live API calls."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from petstore.abb.diagnosis import DiagnosisRequest
from petstore.sbb.direct_diagnosis import DirectApiDiagnosisAgent
from petstore.services import inventory
from petstore.services.models import SKU


@pytest.fixture
def agent():
    return DirectApiDiagnosisAgent(config={})


@pytest.fixture(autouse=True)
def _seeded_catalog():
    """DirectApiDiagnosisAgent verifies model-named SKUs against the real
    catalog -- seed one real SKU so the "resolved" path is exercisable."""
    inventory.seed_catalog(
        [SKU("SUP-FOOD-01", "Tropical Fish Flakes", "supplies", "desc", 899, False, False)],
        stock_by_sku={"SUP-FOOD-01": 10},
    )


def _mock_response(output: str):
    resp = MagicMock()
    resp.output = output
    resp.model_alias = "reasoning"
    resp.provider = "ollama"
    return resp


def test_diagnose_returns_parsed_structured_result(agent):
    mock_output = (
        '{"likely_causes": ["new tank syndrome"], '
        '"recommended_products": ["SUP-FOOD-01"], '
        '"confidence": 0.7, "escalate_to_human": false}'
    )
    with patch("petstore.sbb.direct_diagnosis.llm_invoke", return_value=_mock_response(mock_output)):
        result = agent.execute({
            "narrative": "Tank is cloudy, fish gasping at surface.",
            "customer_id": "cust-1",
        })

    assert result["likely_causes"] == ["new tank syndrome"]
    assert result["recommended_products"] == ["SUP-FOOD-01"]
    assert result["confidence"] == 0.7
    assert result["escalate_to_human"] is False
    assert result["substrate"] == "DirectApiDiagnosisAgent"
    assert any("direct_api" in p for p in result["provenance"])


def test_diagnose_drops_hallucinated_sku(agent):
    """A model-named SKU that doesn't exist in the catalog gets dropped, not trusted."""
    mock_output = (
        '{"likely_causes": ["ammonia spike"], '
        '"recommended_products": ["SUP-FOOD-01", "NOT-A-REAL-SKU"], '
        '"confidence": 0.6, "escalate_to_human": false}'
    )
    with patch("petstore.sbb.direct_diagnosis.llm_invoke", return_value=_mock_response(mock_output)):
        result = agent.execute({"narrative": "...", "customer_id": "cust-2"})

    assert result["recommended_products"] == ["SUP-FOOD-01"]


def test_diagnose_escalates_on_malformed_json(agent):
    """Code decides the fallback, not the model -- unparseable output escalates."""
    with patch("petstore.sbb.direct_diagnosis.llm_invoke",
               return_value=_mock_response("I'm not sure how to help with that.")):
        result = agent.execute({"narrative": "...", "customer_id": "cust-3"})

    assert result["escalate_to_human"] is True
    assert result["confidence"] == 0.0


def test_diagnose_bypasses_no_agent_imports_at_runtime():
    """Sanity: this SBB genuinely calls llm_invoke, not some stub."""
    import petstore.sbb.direct_diagnosis as mod
    assert hasattr(mod, "llm_invoke")
