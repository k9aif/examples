# Pet Store Agentic — Plan

**Status: work in progress.** Phases 1, 3, 4, and the gates prototype (part of Phase 5) are real, running, tested code. Phase 2 (Router) and Phase 6 (Neo4j graph provenance) are still design-only.

**What's actually running right now:**
- `database/schema.sql` — Postgres `petstore` schema (catalog, inventory, orders, order_items, order_state_history, shipping_labels), applied against a live database
- `petstore/services/` — inventory, pricing, payment, order_state, fulfillment — zero LLM imports, verified by `tests/test_deterministic_purity.py` (including a negative-control check that the test genuinely detects violations, not just passes vacuously)
- `demo/walk_deterministic_order.py` — a complete non-livestock order, start to finish, run successfully end-to-end against the live database
- `petstore/gates/` — `BaseGateRegistry` contract + `SimpleGateRegistry` (SQLite)
- `petstore/abb/diagnosis.py` — the `DiagnosisAgent` ABB contract (`DiagnosisRequest`/`DiagnosisResult`, sync/async bridge for `BaseAgent.execute()`)
- `petstore/sbb/direct_diagnosis.py` — `DirectApiDiagnosisAgent`, real `llm_invoke`/`K9ModelRouter` call, built first per project.md's own ordering rationale
- `petstore/sbb/sdk_diagnosis.py` + `sdk_tools.py` — `SdkDiagnosisAgent`, real `claude-agent-sdk` (0.2.125) integration: `query()`, in-process MCP tools via `@tool`/`create_sdk_mcp_server`, `can_use_tool`-based livestock gate, subagents never enabled
- `webui/index.html` — a homage to the original Java Pet Store's look, using the *real* 2001 artwork (mascot, category icons, background tiles), reused under its original BSD-style license with attribution — not yet wired to the backend
- `DEVIATIONS.md` — where the real installed `claude-agent-sdk` differs from `project.md`'s assumptions (hook payload shapes, the `can_use_tool` vs. hook mechanism, subagents-are-opt-in, the fulfillment-tool spec ambiguity)

**30 tests passing total:**
`test_deterministic_purity.py` (9) · `test_gate_registry.py` (8) · `test_direct_diagnosis.py` (4) · `test_gate_cannot_be_bypassed.py` (4) · `test_no_sdk_subagents.py` (1) · `test_sbb_contract_parity.py` (4) — three of the five load-bearing tests from `CLAUDE.md` now exist and pass: gate-cannot-be-bypassed, substrate-is-interchangeable, delegation-hierarchy-stays-single.

Full spec: [`project.md`](project.md) (the authoritative build spec — this file summarizes it, not replaces it).
Project conventions: [`CLAUDE.md`](CLAUDE.md).
Design docs: [`Architecture_Guide.md`](Architecture_Guide.md) (why), [`Detailed_Design.md`](Detailed_Design.md) (exact class shapes).
Diagrams: [`diagrams/`](diagrams/) — four PlantUML views of the architecture, described below.

---

## What this proves

> Agentic autonomy is warranted only where genuine uncertainty exists. Most enterprise workflow is deterministic and should stay that way. The architecture — not the model — decides which is which.

The Claude Agent SDK appears as **one interchangeable substrate** behind a K9-AIF ABB contract (`DiagnosisAgent`) — never as the backbone of the system. `SdkDiagnosisAgent` and `DirectApiDiagnosisAgent` are both real, both tested, and `test_sbb_contract_parity.py` proves they produce the same result shape. That's the deliberate answer to "how do K9-AIF and the Agent SDK coexist": the SDK is wrapped, not adopted wholesale, and K9-AIF's substitutability guarantee applies to it exactly as it applies to any LLM provider.

---

## Diagrams

| File | Shows |
|---|---|
| [`01-architecture-component.puml`](diagrams/01-architecture-component.puml) | Full layered view — Storefront API → Intent Router (SHORT_CIRCUIT / RESOLVED / CONTINUE) → deterministic services or the agentic fallthrough → Orchestrator → Squad → ABB → the two SBBs → GateRegistry + graph |
| [`02-abb-sbb-class.puml`](diagrams/02-abb-sbb-class.puml) | The ABB/SBB substrate swap — `DiagnosisAgent` contract, `SdkDiagnosisAgent` vs `DirectApiDiagnosisAgent`, the request/result dataclasses, config-driven binding |
| [`03-gate-enforcement-sequence.puml`](diagrams/03-gate-enforcement-sequence.puml) | The adversarial case — an authoritative-framing prompt trying to bypass the livestock gate, denied by `can_use_tool` querying `GateRegistry` directly rather than trusting context (see `DEVIATIONS.md` #2 for why `can_use_tool`, not a `PreToolUse` hook, ended up being the real mechanism) |
| [`04-intent-router-activity.puml`](diagrams/04-intent-router-activity.puml) | Chain-of-responsibility dispatch logic — why most traffic never reaches an agent, and where the gate check sits in the one path that does |

Render any of them with `plantuml diagrams/<file>.puml` (or paste into any PlantUML renderer).

---

## Build order (from `project.md` §10 — see there for full detail)

1. **Deterministic core** — ✅ done. Services, order state machine, Postgres-backed catalog/inventory/orders. `test_deterministic_purity.py` passing. Not yet done: livestock-flagged SKUs and the gate-triggering path through this phase — the current demo only exercises a non-livestock order, per spec.
2. **Routing** — ⬜ not started. Intent router, deterministic handlers registered first. Prove ordinary traffic short-circuits.
3. **ABB + first SBB** — ✅ done. `DiagnosisAgent` contract defined; `DirectApiDiagnosisAgent` implemented and tested (4 tests, `llm_invoke` mocked).
4. **SDK SBB** — ✅ done. `SdkDiagnosisAgent` built against the *verified* real `claude-agent-sdk` API (see `DEVIATIONS.md`), not the spec's guess. Subagents never enabled (1 test). Both SBBs pass `test_sbb_contract_parity.py` (4 tests).
5. **Gates** — 🟡 partial. `GateRegistry` (8 tests) and the `can_use_tool` gate callback (4 tests, `test_gate_cannot_be_bypassed.py`) are done and tested against `SdkDiagnosisAgent`. Not yet done: the equivalent explicit gate branch inside `DirectApiDiagnosisAgent` (project.md §6 requires both SBBs enforce it identically — currently only the SDK side has a wired gate check). A K9x HIL-backed `GateRegistry` adapter remains a deliberately deferred later phase.
6. **Graph provenance** — ⬜ not started. Sessions, tool invocations, gates, decisions. Confirm `SATISFIED_BY` distinguishes the two substrates in Neo4j.
7. **Docs** — ⬜ not started (written last, from what was actually built — see `DEVIATIONS.md` for material already gathered toward this).

---

## Verify, don't assume — what actually happened

`project.md` §0 asked for this before Phase 4 started; it happened for real, not hypothetically:

```bash
pip show claude-agent-sdk                 # 0.2.125, already installed
python -c "import claude_agent_sdk as s; print(dir(s))"
python -c "from claude_agent_sdk import ClaudeAgentOptions; import dataclasses; ..."
```

Findings recorded in `DEVIATIONS.md`, all six of them, including the one that mattered most for correctness: the spec assumed `PreToolUse` hook returning `deny()`; the real, purpose-built mechanism is `ClaudeAgentOptions.can_use_tool`, a dedicated callback. `SdkDiagnosisAgent` uses the verified real mechanism, not the spec's guess.

One thing still genuinely unverified (`DEVIATIONS.md` #6): the exact qualified tool-name string the CLI transport expects for in-process SDK MCP tools. Can't be confirmed by reading Python source alone — needs a live run.

---

## Not doing yet

Router/Intent dispatch (Phase 2), the equivalent gate branch in `DirectApiDiagnosisAgent`, Neo4j provenance (Phase 6), and wiring `webui/index.html` to the actual backend. No live `claude-agent-sdk` session has actually been run end-to-end yet either — everything in Phase 4 is verified against the SDK's real *type signatures*, and tested with `query()` mocked, but not yet run live against the Claude CLI/API. That's the natural next verification step before calling Phase 4 fully proven.
