# Pet Store Agentic — Plan

**Status: work in progress.** Phases 1, 3, 4, and the gates prototype (part of Phase 5) are real, running, tested code. On top of that, the storefront now has a genuinely working web frontend — accounts, checkout, order history, and an admin portal — which is new scope beyond `project.md`'s original 7 phases, added because a static mockup wasn't satisfying to click through. Phase 6 (Neo4j graph provenance) is still design-only.

**Full K9-AIF hierarchy build-out, in progress.** This project previously only reached the Agent layer (`BaseAgent`, `BaseAdapter`, `k9_inference`). Now extending it to exercise Router → Orchestrator → Squad → Agent for real, plus wiring `SdkDiagnosisAgent` to a live route. Build order: **Router (done, below)** → Orchestrator + Diagnosis Squad → Setup Planning Squad (second agentic juncture, second squad) → SDK live wiring → second gate placement (setup planner). Two real K9-AIF-framework deviations found and recorded in `DEVIATIONS.md` #7–#8 during §0 verification before writing any of this: `HandlerResult`/`SHORT_CIRCUIT`/`RESOLVED`/`CONTINUE` don't exist anywhere in the installed framework (Petstore's own application-level vocabulary, not a framework primitive), and `BaseSquad` matches flow steps by the agent instance's real class name, not by its `AgentRegistry` alias — a real gotcha for `DiagnosisAgent`'s swappable substrate.

**Phase — Router (done).** `petstore/routing/router.py` — `PetstoreRouter` extends the real `BaseRouter` (`k9_core/router/base_router.py`). Five deterministic handlers (`petstore/routing/handlers.py`, registration order visible in one list): order status, inventory lookup, cart operations, return eligibility, product search — each a fixed query against `petstore/services/`, none of them an agent. `route()` tries each in order; unclaimed requests return `CONTINUE` (there's no Orchestrator yet to hand off to — that's Phase 2). The router counts dispositions (`disposition_stats()`) so the demo can report what fraction of traffic never reaches an agent — proven directly in `test_router.py::test_majority_of_realistic_traffic_never_reaches_an_agent` (7 of 8 realistic requests short-circuit; only the one genuine diagnosis narrative falls through). 10 new tests, all passing.

**What's actually running right now:**
- `database/schema.sql` — Postgres `petstore` schema: catalog, inventory, orders (+ nullable `user_id`), order_items, order_state_history, shipping_labels, **users, admin, sessions** — applied against a live database
- `petstore/services/` — inventory, pricing, payment, order_state, fulfillment, **auth** (PBKDF2 password hashing + session tokens), **checkout** (full order orchestration) — zero LLM imports, verified by `tests/test_deterministic_purity.py`
- `demo/walk_deterministic_order.py`, `demo/seed_original_catalog.py`, `demo/seed_admin.py` — runnable end to end against the live database
- `petstore/gates/` — `BaseGateRegistry` contract + `SimpleGateRegistry` (SQLite), now with `list_pending()` for the admin dashboard
- `petstore/abb/diagnosis.py` — the `DiagnosisAgent` ABB contract
- `petstore/sbb/direct_diagnosis.py` — `DirectApiDiagnosisAgent`, real `llm_invoke`/`K9ModelRouter` call
- `petstore/sbb/sdk_diagnosis.py` + `sdk_tools.py` — `SdkDiagnosisAgent`, real `claude-agent-sdk` (0.2.125) integration
- `webui/webui_server.py` — a real backend: category browsing, a real session-based **shopping cart** (`petstore/services/cart.py` — add/remove/update, its own anonymous `petstore_cart` cookie, works identically for guests and logged-in users), guest and logged-in checkout from the cart (`petstore/services/checkout.py`, tying the livestock gate to a real order for the first time), registration/login/logout, order history, and an admin portal (all orders + livestock gate approve/reject) — verified end to end live: add multiple items to cart → checkout → livestock item stops at FULFILLING → admin sees pending gate → approves it → order ships and cart clears
- `demo/seed_demo_user.py` — a `demo`/`demo` account pre-seeded with sample orders across every state (shipped, delivered, pending gate, cancelled from a declined card), so trying the site doesn't require registering and shopping from scratch first
- `webui/index.html` + category/cart/checkout pages — real 2001 artwork throughout, including per-product photos (fish1.jpg, dog2.gif, etc., all 16 species), reused under the original BSD-style license with attribution
- `DEVIATIONS.md` — where the real installed `claude-agent-sdk` differs from `project.md`'s assumptions

**68 tests passing total:**
`test_deterministic_purity.py` (13) · `test_gate_registry.py` (8) · `test_direct_diagnosis.py` (4) · `test_gate_cannot_be_bypassed.py` (4) · `test_no_sdk_subagents.py` (1) · `test_sbb_contract_parity.py` (4) · `test_auth.py` (8) · `test_checkout.py` (8) · `test_cart.py` (8) · **`test_router.py` (10, new)** — three of the five load-bearing tests from `CLAUDE.md` exist and pass: gate-cannot-be-bypassed, substrate-is-interchangeable, delegation-hierarchy-stays-single. `test_checkout.py` is the first test proving the gate against a *real order*, not just the registry or the SDK callback in isolation.

A real state-machine bug was caught and fixed along the way: `FULFILLING → CANCELLED` wasn't a legal transition, which broke gate rejection (an order sitting at FULFILLING awaiting approval has nowhere to go if rejected). Fixed in `order_state.py`.

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

Router/Intent dispatch (Phase 2), the equivalent gate branch in `DirectApiDiagnosisAgent`, Neo4j provenance (Phase 6). No live `claude-agent-sdk` session has actually been run end-to-end yet either — everything in Phase 4 is verified against the SDK's real *type signatures*, and tested with `query()` mocked, but not yet run live against the Claude CLI/API. That's the natural next verification step before calling Phase 4 fully proven.

On the storefront side: no cart merge on login (a guest's cart and an account's cart are separate; adding to cart before logging in doesn't carry over — a real classic e-commerce edge case, deliberately out of scope here), no password reset, no admin ability to manage the catalog itself (only orders and gates), and the diagnosis agents (Direct API / SDK) aren't wired into the storefront UI at all yet -- that integration (a "having trouble with your pet?" flow calling into `DiagnosisAgent`) is still ahead.

An `/about` page now exists (linked from every page's topbar, including the static `index.html` homepage). It covers the original J2EE Pet Store in one paragraph, then gives K9-AIF Framework and the Claude Agent SDK equal-length treatment — each does a real job the other doesn't (K9-AIF: governance, contracts, substitutability, provenance; the SDK: the actual tool-use loop, context compaction, session persistence, MCP wiring), with the framing drawn straight from this repo's own `README.md`. It embeds both `diagrams/01-architecture-component.png` and `diagrams/02-abb-sbb-class.png` (copied into `webui/images/`) and links out to `github.com/k9aif/examples`. No K9X logo in the top-left, by explicit decision — the plain "← Pet Store Agentic" link stays as-is.
