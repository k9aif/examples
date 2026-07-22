"""
Load-bearing test (CLAUDE.md): "Substrate is interchangeable."

Both SBBs satisfy the same DiagnosisAgent contract and produce the same
DiagnosisResult shape, given equivalent scenarios -- proven by mocking
each substrate's external dependency (llm_invoke for DirectApi, the SDK's
query() for Sdk) rather than requiring live credentials for either.

Per project.md §5: substitutability means the contract holds, not that
implementations are equivalent in quality -- this test checks shape and
key presence, not that the two substrates reach identical conclusions.
"""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import TextBlock

from petstore.abb.diagnosis import DiagnosisAgent
from petstore.sbb.direct_diagnosis import DirectApiDiagnosisAgent
from petstore.sbb.sdk_diagnosis import SdkDiagnosisAgent

_EXPECTED_KEYS = {
    "agent", "substrate", "likely_causes", "recommended_products",
    "confidence", "escalate_to_human", "provenance",
}

_DIAGNOSIS_JSON = (
    '{"likely_causes": ["new tank syndrome"], '
    '"recommended_products": [], '
    '"confidence": 0.65, "escalate_to_human": false}'
)


def _mock_direct_response():
    resp = MagicMock()
    resp.output = _DIAGNOSIS_JSON
    resp.model_alias = "reasoning"
    resp.provider = "ollama"
    return resp


async def _fake_sdk_query(*, prompt, options):
    yield SimpleNamespace(content=[TextBlock(text=_DIAGNOSIS_JSON)])


def test_both_sbbs_are_diagnosis_agents():
    with tempfile.TemporaryDirectory() as tmp:
        sdk_agent = SdkDiagnosisAgent(config={"gates": {"provider": "simple",
                                                          "db_path": os.path.join(tmp, "g.db")}})
        direct_agent = DirectApiDiagnosisAgent(config={})

    assert isinstance(sdk_agent, DiagnosisAgent)
    assert isinstance(direct_agent, DiagnosisAgent)


def test_direct_api_result_shape():
    agent = DirectApiDiagnosisAgent(config={})
    with patch("petstore.sbb.direct_diagnosis.llm_invoke", return_value=_mock_direct_response()):
        result = agent.execute({"narrative": "cloudy tank", "customer_id": "cust-parity-1"})

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["substrate"] == "DirectApiDiagnosisAgent"


def test_sdk_result_shape():
    with tempfile.TemporaryDirectory() as tmp:
        agent = SdkDiagnosisAgent(config={"gates": {"provider": "simple",
                                                      "db_path": os.path.join(tmp, "g.db")}})
        with patch("petstore.sbb.sdk_diagnosis.query", _fake_sdk_query):
            result = agent.execute({"narrative": "cloudy tank", "customer_id": "cust-parity-2"})

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["substrate"] == "SdkDiagnosisAgent"


def test_both_substrates_produce_the_same_result_shape_for_the_same_scenario():
    """The parity claim itself: same keys, same types, for an equivalent scenario."""
    direct_agent = DirectApiDiagnosisAgent(config={})
    with patch("petstore.sbb.direct_diagnosis.llm_invoke", return_value=_mock_direct_response()):
        direct_result = direct_agent.execute({"narrative": "cloudy tank", "customer_id": "cust-parity-3"})

    with tempfile.TemporaryDirectory() as tmp:
        sdk_agent = SdkDiagnosisAgent(config={"gates": {"provider": "simple",
                                                          "db_path": os.path.join(tmp, "g.db")}})
        with patch("petstore.sbb.sdk_diagnosis.query", _fake_sdk_query):
            sdk_result = sdk_agent.execute({"narrative": "cloudy tank", "customer_id": "cust-parity-4"})

    assert set(direct_result.keys()) == set(sdk_result.keys())
    for key in ("likely_causes", "recommended_products", "provenance"):
        assert isinstance(direct_result[key], list)
        assert isinstance(sdk_result[key], list)
    for key in ("confidence",):
        assert isinstance(direct_result[key], float)
        assert isinstance(sdk_result[key], float)
    assert isinstance(direct_result["escalate_to_human"], bool)
    assert isinstance(sdk_result["escalate_to_human"], bool)
