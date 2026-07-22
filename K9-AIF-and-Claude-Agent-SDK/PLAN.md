# Pet Store Agentic — Plan

**Status: planning only.** No implementation yet. Target start: later this week, not today.

Full spec: [`project.md`](project.md) (the authoritative build spec — this file summarizes it, not replaces it).
Project conventions: [`CLAUDE.md`](CLAUDE.md).
Diagrams: [`diagrams/`](diagrams/) — four PlantUML views of the architecture, described below.

---

## What this proves

> Agentic autonomy is warranted only where genuine uncertainty exists. Most enterprise workflow is deterministic and should stay that way. The architecture — not the model — decides which is which.

The Claude Agent SDK appears as **one interchangeable substrate** behind a K9-AIF ABB contract (`DiagnosisAgent`) — never as the backbone of the system. That's the deliberate answer to "how do K9-AIF and the Agent SDK coexist": the SDK is wrapped, not adopted wholesale, and K9-AIF's substitutability guarantee applies to it exactly as it applies to any LLM provider.

---

## Diagrams

| File | Shows |
|---|---|
| [`01-architecture-component.puml`](diagrams/01-architecture-component.puml) | Full layered view — Storefront API → Intent Router (SHORT_CIRCUIT / RESOLVED / CONTINUE) → deterministic services or the agentic fallthrough → Orchestrator → Squad → ABB → the two SBBs → GateRegistry + graph |
| [`02-abb-sbb-class.puml`](diagrams/02-abb-sbb-class.puml) | The ABB/SBB substrate swap — `DiagnosisAgent` contract, `SdkDiagnosisAgent` vs `DirectApiDiagnosisAgent`, the request/result dataclasses, config-driven binding |
| [`03-gate-enforcement-sequence.puml`](diagrams/03-gate-enforcement-sequence.puml) | The adversarial case — an authoritative-framing prompt trying to bypass the livestock gate, denied by a `PreToolUse` hook that queries `GateRegistry` directly rather than trusting context |
| [`04-intent-router-activity.puml`](diagrams/04-intent-router-activity.puml) | Chain-of-responsibility dispatch logic — why most traffic never reaches an agent, and where the gate check sits in the one path that does |

Render any of them with `plantuml diagrams/<file>.puml` (or paste into any PlantUML renderer).

---

## Build order (from `project.md` §10 — see there for full detail)

1. **Deterministic core** — services, order state machine, livestock-flagged catalog. `test_deterministic_purity.py` ships here.
2. **Routing** — intent router, deterministic handlers registered first. Prove ordinary traffic short-circuits.
3. **ABB + first SBB** — define `DiagnosisAgent`; implement `DirectApiDiagnosisAgent` first, deliberately, so the contract is substrate-neutral before SDK specifics can leak into it.
4. **SDK SBB** — `SdkDiagnosisAgent`. Verify installed SDK signatures before writing anything. Disable subagents. Both SBBs must pass `test_sbb_contract_parity.py`.
5. **Gates** — `GateRegistry`, the `PreToolUse` hook, the equivalent explicit branch in SBB-B. Both adversarial tests must pass.
6. **Graph provenance** — sessions, tool invocations, gates, decisions. Confirm `SATISFIED_BY` distinguishes the two substrates in Neo4j.
7. **Docs** — written last, from what was actually built.

---

## Before Phase 1 starts — verify, don't assume

Per `project.md` §0 and `CLAUDE.md`'s deviation policy — the installed package wins over this spec, always:

```bash
pip show claude-agent-sdk
python -c "import claude_agent_sdk as s; print(dir(s))"
python -c "from claude_agent_sdk import ClaudeAgentOptions; help(ClaudeAgentOptions)"
python -c "import k9_aif; print(k9_aif.__file__)"
```

Specifically re-check: `PreToolUse`/`PostToolUse`/`SubagentStop` hook payload shapes, the hook deny contract, `ClaudeAgentOptions` fields, and the subagent-disable mechanism. Record any drift from the spec in `DEVIATIONS.md` with the actual signature — don't silently adapt the architecture around a guessed API.

One documentation note carried over from review: `SdkDiagnosisAgent` bypasses `llm_invoke`/`K9ModelRouter` by design — the Agent SDK owns its own inference loop. That's the one substrate in this whole example that doesn't go through the standard K9-AIF inference chain, and it should say so explicitly in `docs/sbb-swap.md` when Phase 7 is written, so a reader familiar with framework convention isn't left wondering.

---

## Not doing today

No code, no venv installs beyond what's already set up, no PyPI/GitHub actions. This file and the diagrams are the full scope of today's session.
