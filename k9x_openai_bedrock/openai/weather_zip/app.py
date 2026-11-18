# SPDX-License-Identifier: Apache-2.0
"""
Application wiring: builds the governed OpenAI agent adapter once.

Everything here is the solution's own content: which checks Shield runs (config.yaml), which
roles may reach which action (the Zero Trust role policy below), which tools exist (tools.py)
and which agent uses them (agents/yaml). The framework supplies the mechanisms.
"""

from __future__ import annotations

import os
from pathlib import Path

from k9_aif_abb.k9_adapters.openai_agents import K9OpenAIAgentsAdapter
from k9_aif_abb.k9_core.governance.pipeline import governance_from_config
from k9_aif_abb.k9_security.zero_trust.guards import DefaultZeroTrustGuard, RoleBasedAuthorizationGuard
from k9_aif_abb.k9_utils.config_loader import load_yaml

from .tools import CAPABILITIES

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config" / "config.yaml"
AGENTS_DIR = APP_DIR / "agents" / "yaml"

# Who may do what. The run itself is the action "weather.lookup"; each agent that takes a
# turn is the action "openai_agent:<name>". A principal without one of these roles is denied.
ROLE_POLICY = {
    "weather.lookup": ["customer", "staff"],
    "openai_agent:WeatherAgent": ["customer", "staff"],
}


def build_adapter() -> K9OpenAIAgentsAdapter:
    os.chdir(APP_DIR)                      # runtime/ paths in config.yaml are relative to the app
    config = load_yaml(CONFIG_PATH)
    governance = governance_from_config(config)   # k9x Shield, then Granite Guardian when governance.guardian is on
    guard = DefaultZeroTrustGuard(authorization_guard=RoleBasedAuthorizationGuard(ROLE_POLICY))
    return K9OpenAIAgentsAdapter(
        capabilities=CAPABILITIES,
        agents_dir=AGENTS_DIR,
        entry_agent="WeatherAgent",
        config=config,
        governance=governance,
        zero_trust_guard=guard,
        model_routing="k9",
        name="WeatherZipOrchestrator",
    )
