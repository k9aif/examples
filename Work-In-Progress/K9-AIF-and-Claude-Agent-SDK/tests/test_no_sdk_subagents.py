"""
Load-bearing test (CLAUDE.md): "Delegation hierarchy stays single."

Subagents in claude-agent-sdk are opt-in via ClaudeAgentOptions.agents
(DEVIATIONS.md #3) -- never populating that field is the entire disable
mechanism. This asserts SdkDiagnosisAgent never sets it, so Squads remain
the only fan-out authority in this application (Architecture_Guide.md
principle #2).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from petstore.abb.diagnosis import DiagnosisRequest
from petstore.sbb.sdk_diagnosis import SdkDiagnosisAgent


@pytest.fixture
def agent():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "gates.db")
        yield SdkDiagnosisAgent(config={"gates": {"provider": "simple", "db_path": db_path}})


@pytest.mark.asyncio
async def test_agents_field_never_populated(agent):
    request = DiagnosisRequest(narrative="...", customer_id="cust-1", order_id=None)
    options = agent._build_options(request, provenance=[])

    assert options.agents is None, (
        "ClaudeAgentOptions.agents must stay unset -- populating it is what "
        "enables SDK subagents, which would create a second, untracked "
        "delegation hierarchy alongside K9-AIF's Squad -> Agent flow."
    )
