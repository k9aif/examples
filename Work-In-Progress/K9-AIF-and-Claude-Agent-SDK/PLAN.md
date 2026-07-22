# Pet Store Agentic — Plan

**Status: work in progress.** Phase 1 (deterministic core) and the gates prototype are real, running, tested code — everything from Phase 2 onward (Router, Diagnosis ABB/SBBs, Agent SDK integration, Neo4j provenance) is still design-only. Main implementation target for the rest: next week.

**What's actually running right now:**
- `database/schema.sql` — Postgres `petstore` schema (catalog, inventory, orders, order_items, order_state_history, shipping_labels), applied against a live database
- `petstore/services/` — inventory, pricing, payment, order_state, fulfillment — zero LLM imports, verified by `tests/test_deterministic_purity.py` (including a negative-control check that the test genuinely detects violations, not just passes vacuously)
- `demo/walk_deterministic_order.py` — a complete non-livestock order, start to finish, run successfully end-to-end against the live database
- `petstore/gates/` — `BaseGateRegistry` contract + `SimpleGateRegistry` (SQLite), 8 passing tests
- `webui/index.html` — a static homage to the original Java Pet Store's look (parrot mascot, category sidebar, top bar) — not yet wired to the backend

17 tests passing total (9 in `test_deterministic_purity.py` + 8 in `test_gate_registry.py`).

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

1. **Deterministic core** — ✅ done. Services, order state machine, Postgres-backed catalog/inventory/orders. `test_deterministic_purity.py` passing. Not yet done: livestock-flagged SKUs and the gate-triggering path through this phase — the current demo only exercises a non-livestock order, per spec.
2. **Routing** — intent router, deterministic handlers registered first. Prove ordinary traffic short-circuits.
3. **ABB + first SBB** — define `DiagnosisAgent`; implement `DirectApiDiagnosisAgent` first, deliberately, so the contract is substrate-neutral before SDK specifics can leak into it.
4. **SDK SBB** — `SdkDiagnosisAgent`. Verify installed SDK signatures before writing anything. Disable subagents. Both SBBs must pass `test_sbb_contract_parity.py`.
5. **Gates** — `GateRegistry`, the `PreToolUse` hook, the equivalent explicit branch in SBB-B. Both adversarial tests must pass. The `BaseGateRegistry` contract and its `SimpleGateRegistry` adapter are already prototyped (`petstore/gates/`, `tests/test_gate_registry.py`, 8 passing tests) — what's left for this phase is the hook and the SBB-side integration, not the registry itself. A K9x HIL-backed adapter (real human-review queue instead of a direct `resolve()` call) is a deliberately deferred later phase — see `Detailed_Design.md`.
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

## Not doing today (still next week)

The Diagnosis ABB/SBBs, the Router/Intent dispatch, the Agent SDK integration itself, and Neo4j provenance. `webui/index.html` is a static homage only — wiring it to the deterministic services happens when the Router/Storefront API phase is built, not before. Today's scope grew well past the original "planning only" intent — Phase 1 and the gates prototype are real, tested, and running against a live Postgres database — but Phases 2, 3, 4, and 6 are still untouched.
