
# CLAUDE.md — Pet Store Agentic (Project Level)

Framework-level conventions live in the K9-AIF `CLAUDE.md`. This file covers only what is specific to Pet Store Agentic. Where both apply, framework conventions govern unless contradicted here explicitly.

Build plan and full design rationale: `PETSTORE_AGENTIC_SPEC.md`.

---

## What this project is

A **reference implementation**, not a product. Pet Store Agentic exists to demonstrate one claim:

> Agentic autonomy is warranted only where genuine uncertainty exists. Most enterprise workflow is deterministic and should stay that way. The architecture — not the model — decides which is which.

The domain is deliberately mundane. If a change makes the demo more impressive but blurs the deterministic/agentic boundary, it is the wrong change.

---

## Project invariants

These are specific to this application. Do not violate them without asking first.

1. **`petstore/services/` contains no LLM.** No SDK imports, no model clients, no agents. Enforced by `test_deterministic_purity.py`. The import graph is the proof — a reader must be able to `grep` and find nothing.
2. **Deterministic handlers register before the agentic fallthrough.** The agentic path is what happens when no deterministic handler claims the request. That ordering is the architectural argument, not a performance optimization.
3. **Gates are enforced in the harness, never in the prompt.** Gate state lives in `GateRegistry`, external to agent context. Hooks query the registry on every invocation and never trust context.
4. **Squads own all fan-out.** SDK subagents stay disabled inside K9-AIF-managed agents. Two delegation hierarchies would break provenance and leave `DELEGATES_TO` incomplete.
5. **Both SBBs satisfy the same ABB contract.** Adding a capability to one means adding it to the contract and to both, or not adding it.
6. **One agentic juncture.** Customer problem diagnosis is the only genuinely uncertain step in this application. Resist adding more.

---

## When the installed API differs from the spec

The installed package wins. Record the difference in `DEVIATIONS.md` with the actual signature.

If a K9-AIF capability the spec assumes does not exist, **stop and say so.** Do not stub a substitute — a missing capability is useful information, a fabricated one corrupts the reference implementation.

Signatures worth re-verifying whenever SDK work resumes: `PreToolUse` payload shape, the hook deny contract, `ClaudeAgentOptions` fields, subagent disable mechanism.

---

## The five load-bearing tests

These carry the project's claims. They are not routine coverage.


| Test                               | Claim it defends                     |
| ------------------------------------ | -------------------------------------- |
| `test_deterministic_purity.py`     | Deterministic paths need no agent    |
| `test_gate_cannot_be_bypassed.py`  | Governance is enforced, not advisory |
| `test_gate_survives_compaction.py` | Gates outlive context loss           |
| `test_sbb_contract_parity.py`      | Substrate is interchangeable         |
| `test_no_sdk_subagents.py`         | Delegation hierarchy stays single    |

If one starts failing, that is an architectural regression. Fix the architecture, not the test.

`test_gate_cannot_be_bypassed.py` is the highest-value artifact in the repo. Governance claims are cheap; a passing adversarial test is not.

---

## Documentation standards for this repo

Every capability claim in `docs/` must correspond to a passing test. If it cannot be tested, phrase it as intent rather than fact.

Be explicit about tradeoffs rather than hiding them. The direct-API SBB handles open-ended narratives worse than the SDK-backed one — that belongs in the docs. Substitutability means the contract holds, not that implementations are equivalent in quality.

Do not claim production readiness.
