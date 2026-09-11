# IBM Process Studio → K9-AIF Studio: Plan

Status: **forked and pushed. Enhancement work not yet started.**

**Working location:** `/Users/ravinatarajan/ai/studiox_v2` — remote `github.com/k9aif/studiox_v2`,
branch `main`, seeded from studiox's working tree with fresh history (commit `a74f593`).

## Goal

Take IBM Process Studio's generated process artifacts (complex `.md` blueprint and/or `.bpmn`)
and have `studiox_v2` turn them into a working canvas (Router → Orchestrator → Squad → Agent),
preserving Process Studio's own GREEN/AMBER/RED autonomy-zone coding, and — this is the headline
deliverable — produce a **Process-to-Implementation Traceability Matrix** proving every process
element actually landed correctly in the generated implementation.

## Primary deliverable: Process → Implementation Traceability Matrix (2026-09-10)

This is the main goal, restated plainly: `studiox_v2` must ingest Process Studio's complex input
(`.md` and/or `.bpmn`) and produce, as output, a traceability matrix — not just a canvas and a
scaffold. Process Studio already hands us the mechanism for this on a plate: every element in its
output carries a stable, coded ID (ATS# steps, AGN# agents, TOL# tools, DPS# data products) that
recurs across every phase and every artifact. A traceability matrix is just: for each such ID,
what did we generate, and does it match.

**Proposed columns:**

| Process ID | Process Element | Zone | → Orchestrator | → Squad | → Agent (class) | Agent Base Type | HITL Touchpoint | Match? |
|---|---|---|---|---|---|---|---|---|
| ATS6 | Detect Invoice Anomalies | RED | Agn4AnomalyDetectionAgentOrchestrator | *(actual squad loaded)* | *(actual agent invoked)* | *(actual base class)* | AP Manager + Internal Audit | ✓ / ✗ |

The "Match?" column is the whole point — computed by cross-checking what the generator *intended*
(from the process ID → agent/zone mapping established at import) against what the generated code
*actually* wires up (parsed back out of the scaffold's orchestrator/squad/agent files). This is
exactly the check that would have caught the orchestrator-wiring bug in "Known Bugs" above
automatically, on every generation — not something we'd have had to find by hand-inspecting files.

**This supersedes the vaguer "fidelity trace" idea** in the artifact-mapping table below (the
`eval-trace.json` counterpart row) — the traceability matrix *is* that artifact, made concrete.

**Must stay generic (per the design principle above):** matrix rows are driven entirely by
whatever IDs/zones/agents were actually extracted from the given input — no AP-invoice-specific
column, no hardcoded AGN1–7 assumption. A differently-shaped BPMN (different lane count, no
explicit ID scheme at all) must still produce a matrix, using whatever identifiers are available
(task IDs, lane names) if Process Studio's ATS#/AGN# convention isn't present.

**Ambition calibration (2026-09-10):** IBM Process Studio is a mature, team-built product
(over a year of development) about to be released to IBM's Federal customers, and its output is
correspondingly deep — a 6-phase EAEF blueprint with atomic step register, business ontology,
HITL specs, data products, MCP tool register, context/memory engineering, 81-case eval plan, and
an LLM-judge quality trace on the blueprint itself. This demo's bar is not "get the canvas to
render" — it's **artifact-for-artifact parity**: each Process Studio output should map to an
equally detailed k9x_studio counterpart artifact, not just a bare canvas + scaffold. The
BPMN/scaffold work below is the structural core; the doc/eval/trace counterparts are what make
the demo read as matching IBM's own level of polish rather than a toy import.

**Design principle — generic studio, not a one-off for this example (2026-09-10):** We are not
building studiox_v2 to handle *this* accounts-payable BPMN. We're building a generic studio whose
input is *any* BPMN model or process-output document, from *any* domain — financial, accounting,
insurance, healthcare, whatever a customer's process-authoring tool hands us next. The AP invoice
files in `process_studio_generated_files/` are a **validation test case**, not the target. Every
fix below must be implemented generically:
- Zone-color extraction reads whatever hex Process Studio (or any BPMN source) puts on a task —
  not the three specific hex codes in this one file, if avoidable, or at minimum the extraction
  point must be a single swappable mapping, not inlined per-call.
- Orchestrator/squad wiring must be correct for *any* lane count and *any* mix of GREEN/AMBER/RED
  lanes — the bug found last turn is a generic indexing bug in the generator, not something
  specific to 7 lanes or to AP invoice naming, and the fix must be verified against a
  differently-shaped BPMN too (different lane count, different zone mix) before being called done.
- The architecture-doc / eval-suite / fidelity-trace generators must derive their content from
  whatever was actually imported (domain, agent names, zones, steps) — never hardcode
  "accounts payable," "invoice," or any AP-specific term into the generator code itself.
- Before calling any fix "done," it should be sanity-checked against at least one *other* domain
  shape (e.g. a differently-structured insurance or claims BPMN), not just re-run against this
  same AP file.

## Decision log

- **Do not touch the current studiox** (`k9x-ecosystem/k9x_studio`, remote `github.com/k9aif/studiox`).
  It's the live studio.k9x.ai codebase and the reference point for the IEEE paper submission.
  All new work for this IBM demo happens in a separate copy.
- **Forked (2026-09-10).** Copied studiox's working tree (files only, no shared git history) into
  `/Users/ravinatarajan/ai/studiox_v2`, committed, pushed to `github.com/k9aif/studiox_v2` (main).
  `.env`, `node_modules`, `dist`, `.venv`, `__pycache__` excluded per its `.gitignore` — needs
  `.env` recreated from `.env.sample`, `npm install` in `frontend/`, and a fresh `.venv` before
  it will run.
- **Working name:** `studiox_v2` (settled — this is the actual repo name). Earlier considered
  `k9x_agent_studio`; rejected because IBM already has a product called "Agent Studio" (alongside
  Context Studio, Process Studio), so that name would collide with IBM's own naming.
- **Note for positioning:** IBM Process Studio generates its EAEF blueprints via Claude Sonnet.
  k9x/DAS runs on local qwen2.5:32b. Worth using in the pitch ("consumes Process Studio's
  Claude-generated output, runs the resulting agents on your own infra") — not yet decided where
  (demo talk track vs. IEEE paper vs. background only).
- Repo location/visibility for `k9x_studio_v2` (same `k9aif` org vs. personal, public vs. private):
  **deferred**, to be decided before any fork actually happens.

## Process Studio output artifact inventory

Source: `/Users/ravinatarajan/ai/k9-aif-examples/ibm-process-studio-demo/process_studio_generated_files/`
(demo case: Accounts Payable & Expense Reimbursements, APQC PCF 9.5)


| # | Process Studio Output                                     | Description                                                                                                                                   | Related k9x_studio_v2 Need                                                                                                                                                                                                                                                                                                                                                                                                |
| --- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `accounts-payable-expense-reimbursements-bpmn.bpmn`       | BPMN 2.0 XML — 7 lanes (AGN1–7), 14 tasks (ATS1–14), each task carries`color:background-color` = GREEN/AMBER/RED zone, plus a color legend | **Primary input.** Import already works structurally today (lanes→Orchestrator+Squad, tasks→Agent) in current studiox's `bpmn_service.py`. **Gap:** zone color per task is never read. Needs a `_zone_from_color()` extraction feeding the existing `zone_to_agent_type()` logic (GREEN→adapter/BaseAgent, AMBER→K9ValidationLoopAgent, RED→K9CriticActorAgent). This is the one must-fix for the chosen input path. |
| 2 | `accounts-payable-expense-reimbursements.md`              | Full EAEF blueprint, 6 phases, §1.1 step register, §1.3 zone map,**§1.8** Agent Definition Register                                        | Handled by`spec_parsing_service.py` in current studiox — **but** its regex looks for heading `### 3.1.8`, while this file's actual heading is `### 1.8`. Won't match; spec-import of this exact file currently falls through to the generic 3-agent `default_suggestion()` instead of the real 7-agent register. One-line regex fix if spec-doc import stays in scope. Lower priority since BPMN is the chosen input.    |
| 3 | `accounts-payable-eaef-blueprint.docx`                    | Word rendering of the same blueprint content as#2                                                                                             | No parser exists; same content as#2 in a distribution format. Out of scope.                                                                                                                                                                                                                                                                                                                                               |
| 4 | `accounts-payable-expense-reimbursements.html`            | Styled, read-only HTML rendering (IBM Carbon design tokens) of the same blueprint                                                             | Same content as#2/#3, human-reading format only. Not an import target. Out of scope.                                                                                                                                                                                                                                                                                                                                      |
| 5 | `accounts-payable-expense-reimbursements-evals.md`        | Human-readable eval plan: 81 test cases (functional/behavioral/adversarial/HITL/observability) mapped to AGN#/ATS#                            | Not ingested today.**Future opportunity, not a blocker:** could seed per-agent test scaffolding in the generated scaffold.                                                                                                                                                                                                                                                                                                |
| 6 | `accounts-payable-expense-reimbursements-evals.csv`       | Same 81 test cases, machine-readable                                                                                                          | Same as#5 — future test-scaffold generation input.                                                                                                                                                                                                                                                                                                                                                                       |
| 7 | `accounts-payable-expense-reimbursements-eval-trace.json` | LLM-judge quality score of the blueprint doc itself (hallucination/consistency checks; score 0.33; judge model`litellm:claude-opus-4-8`)      | Process Studio grading its own output — not a studio input. Out of scope.                                                                                                                                                                                                                                                                                                                                                |

## Process Studio's output style — what "detailed" actually means

Read through the full `.md` blueprint and the `.html` rendering to extract the *style DNA*, not
just the data fields. This is the bar for our own generated docs (content structure below; visual
system is IBM-branded, so we match the rigor, not the literal Carbon/Plex skin):

**Content/document style:**
- **Full agentic SDLC, not just architecture.** Six phases: Cognitive Deconstruction → Context &
  Memory Engineering → Agentic App Engineering → Hardening & Verification → Agentic Activation →
  Agentic Operations & Evolution. Most tools stop at "here's the architecture" — this one covers
  build, test, rollout, *and* steady-state governance.
- **Everything is coded and cross-referenced.** ATS# (steps), AGN# (agents), TOL# (tools), DPS#
  (data products), FUN-##/eval IDs — the same identifiers recur across every phase and every
  artifact (blueprint, BPMN, evals), so any element is traceable end-to-end. Nothing is described
  in prose only; nothing loses its identity between sections.
- **Every table is followed by a synthesis sentence**, not left as a raw data dump — e.g. "This
  domain has 14 atomic steps: 9 Green (64%), 4 Amber (29%), 1 Red (7%)." Tables carry the data;
  prose carries the "so what."
- **Executive framing up front:** Target Outcome/KPIs and a process-taxonomy citation (APQC PCF
  9.5) appear in the first few lines, before any architecture detail.
- **Operational realism, not just design:** model selection includes cost and p95 latency per
  agent; A2A contracts specify message schema, shared state, protocol, and timeout per agent pair;
  guardrails are split into four concrete categories (pre-filters, post-validators, circuit
  breakers, compliance gates); error handling is a per-agent table (failure mode → detection →
  response → human fallback → cascade impact); observability is a per-agent table (metrics →
  alert thresholds → dashboard).
- **Rollout is a first-class artifact:** a three-wave activation plan (Shadow Mode → Green Zone →
  Full Activation) with per-wave scope, duration, instrumented telemetry, and quantified exit
  criteria — plus a stakeholder enablement plan and a formal operational-handover checklist.
- **Steady-state governance, not a one-time handoff:** continuous eval cadence, a model-version
  registry with mandatory regression testing on upgrade, monthly override-pattern analysis, and an
  outcome-measurement table (metric → baseline → target → frequency → data source → owner).

**Visual style (`.html`, IBM Carbon-based):** fixed left sidebar nav grouped by phase with an
active-section indicator, fixed breadcrumb header, light/dark theme via CSS custom-property
overrides, and the GREEN/AMBER/RED zone expressed twice — as a proportional segmented bar in the
executive summary *and* as inline badges in every table row that touches a zoned step. Zone color
is never just one XML attribute (as in the BPMN) — it's a consistent semantic thread through the
prose, the tables, and the visual summary alike.

**Implication for k9x_studio's own output:** the architecture-doc/eval/trace generators we scope
below shouldn't just emit the data we already extract — they should adopt this shape: coded
cross-referenced IDs, a synthesis sentence per table, per-agent operational tables (not just a
role/goal blob), and the zone shown consistently across canvas, docs, and any HTML export we
eventually add.

**Decision (2026-09-10): adopt Process Studio's zone colors as k9x_studio's own standard**, not
just match the GREEN/AMBER/RED concept. This is a de facto standard worth inheriting rather than
inventing our own triad. Note Process Studio itself actually uses **two different concrete hex
sets** for the same three zones across its own two artifacts — worth knowing before picking one:
- `.bpmn` task fills (Tailwind-style): GREEN `#dcfce7`, AMBER `#fef3c7`, RED `#fee2e2`
- `.html` doc (IBM Carbon tokens): strong accents `green-60 #24a148` / `yellow-30 #f1c21b` /
  `red-60 #da1e28`, paired with light tints `green-10 #defbe6` / `yellow-10 #fcf4d6` /
  `red-10 #fff1f1` for badge backgrounds

**Recommendation for studiox_v2:** use the Carbon strong-accent triad (`#24a148` / `#f1c21b` /
`#da1e28`) for canvas node borders/badges — studio's canvas is dark-themed (`#1e1e2e` background,
existing role colors like indigo `#6366f1`/purple `#8b5cf6`), and these accent tones read clearly
against dark, the same way the light tints would on IBM's white doc background. Reserve the light
tints (`#defbe6`/`#fcf4d6`/`#fff1f1`) for if/when we build a light-mode doc/HTML export, matching
Carbon's own badge pattern (light background + strong text/border). Read *from* the BPMN's
Tailwind hexes on import (that's what's actually in the file), but *render* with the Carbon triad
for consistency with the rest of k9x_studio's own visual language.

## Artifact-to-artifact mapping (target ambition, not yet built)

What k9x_studio should produce as the counterpart to each *kind* of Process Studio output, at
comparable depth — this is the fuller version of the inventory table above, framed as "their
output → our output" rather than just "their output → our gap." Validated here against the AP
invoice example, but every row describes a general capability (any BPMN, any spec-doc format),
not something specific to this file:

| Process Studio Output | k9x_studio Counterpart (target) | Current State |
|---|---|---|
| `.bpmn` (lanes/tasks/zone colors) | Canvas (Router→Orchestrator→Squad→Agent) + generated scaffold, zone-typed | Canvas import works structurally; zone color not read (plan gap #1); **scaffold wiring is actively broken — see Known Bugs below** |
| `.md` blueprint (6 phases: ontology, HITL spec, data products, MCP tools, context/memory engineering, orchestration topology, guardrails, observability) | `ARCHITECTURE.md` / a generated project doc covering the same ground, mapped onto K9-AIF's equivalents (Neo4j ontology, GovernancePipeline, MCP HTTP connectors, K9 context/memory ABBs, Kafka topology, observability hooks) | Today's generated `ARCHITECTURE.md` is thin (~4KB) — no ontology, data-products, or context/memory sections. Needs a real generator, not a template stub. |
| `.docx` / `.html` (polished renderings of the blueprint) | A polished doc export of the above (nice-to-have, lower priority) | Not built — markdown only today |
| `evals.md` / `evals.csv` (81 test cases, categorized by functional/behavioral/adversarial/HITL/observability, mapped to agent+step) | Generated per-agent eval suite in `tests/`, seeded from the same zone/HITL data already extracted at import | Today's `tests/test_financial_analysis_ai.py` is a bare stub (~500 bytes, no real cases) |
| `eval-trace.json` (LLM-judge fidelity score of the blueprint against its own source) | **The Process → Implementation Traceability Matrix** (see "Primary deliverable" above) — this is the concrete form of the fidelity-trace idea, and is the main goal of the whole project, not a secondary artifact | Not built — the headline deliverable |

## Framework code lives in one place (2026-09-10)

`studiox_v2` inherited a stale vendored copy of the framework, `context/k9_aif_abb` (1.6MB, full
source), carried over by the fork's wholesale rsync. Verified it had zero functional role: studio
runtime uses the pip-installed `k9-aif` package (`k9-aif[s3]>=1.8.0` per `pyproject.toml`, `1.9.0`
actually installed); production deploy (`ubuntu/Containerfile`) installs it from PyPI the same
way and says so explicitly; the only `k9_aif_abb` references in studiox's own source are inside
Jinja2 templates (`backend/templates/*.j2`) — text that becomes *generated downstream projects'*
own imports, resolved via their own `pip install`, not this copy. The vendored copy was also
stale — its own `pyproject.toml` said `version = "0.1.0.dev1"`, last synced (per studiox git
history) from framework `1.5.0`, several minor versions behind what's actually in use, with no
automated re-sync.

**Decision:** framework code lives in exactly one place — the pip package, plus the framework
repo itself (`/Users/ravinatarajan/ai/k9-aif-framework`) if a session needs to read real source
for grounding. Removed `context/k9_aif_abb` from `studiox_v2` (commit `a112813`, pushed). Left
`studiox` (the original) untouched with the same staleness — known, not fixed there, per "do not
touch." **Open:** `context/CLAUDE.md`/`context/SKILLS.md` in `studiox_v2` are also not studiox's
own docs — they're the framework repo's own CLAUDE.md/SKILLS.md copied in verbatim (setup
commands reference a `k9_aif_abb/` layout and `.claude/hooks/*.sh` that don't exist in studiox at
all). Not yet resolved — deferred separately from the k9_aif_abb removal.

## Known bugs found in current studiox scaffold generation (2026-09-10)

Verified by inspecting a real generated scaffold (`financial_analysis_ai`, from the AP invoice
BPMN) — **more urgent than the zone-color gap**, since this breaks correctness outright:

1. **Every orchestrator loads the wrong squad.** Traced all 7 generated orchestrators' `_SQUAD_ID`
   and imports: each one is wired to a different lane's squad (Agn1→Agn2's squad, Agn2→Agn3's,
   Agn3→Agn4's, Agn4→Agn6's, Agn5→Agn7's, Agn6→Agn2's, Agn7→Agn2's). Concretely: invoking "AGN4
   Anomaly/Fraud Detection" (the RED-zone, dual-approval step) actually runs the expense-audit
   agent instead; the real `DetectInvoiceAnomaliesAgent` is only ever invoked by AGN3's
   orchestrator (GL Coding) — unrelated to fraud detection. Looks like an index-shift bug from
   pairing the full 7-orchestrator list against a shorter squad list (GREEN lanes Agn1/Agn5 have
   no squad) without re-aligning indices.
2. **RED-zone agent under-generated.** `ReviewDetectMatchingExceptionsAgent` (AGN2, AMBER) is
   correctly generated as `K9ValidationLoopAgent` with a real hypothesis/validate/escalate loop
   ("Generated by k9x_studio"). `DetectInvoiceAnomaliesAgent` (AGN4, RED — the step requiring
   dual human approval, cannot be overridden per the source blueprint) is generated as a bare
   `BaseAgent`, single LLM call, no escalation ("Generated by K9-AIF Generator" — a different
   code path than the AMBER agent). The most safety-critical agent got the least oversight.
3. **`config/scenario.json` is generic/unrelated** ("Overnight Risk Run — Portfolio PF-10231"),
   not derived from the imported AP invoice process at all. Lower severity, but the runtime demo
   payload doesn't match the imported domain either.

## Step-by-step enhancement plan (in `studiox_v2`)

1. **Local runnable baseline first** — before any code change, get `studiox_v2` actually running
   standalone: recreate `.env` from `.env.sample`, `npm install` in `frontend/`, fresh `.venv` +
   `pip install -r requirements.txt`, confirm `run.sh` boots and today's BPMN import still works
   unchanged (regression baseline against `accounts-payable-expense-reimbursements-bpmn.bpmn`).
2. **`bpmn_service.py` — zone-color extraction.** Add `_zone_from_color(hex) -> GREEN/AMBER/RED`
   reading each task's `color:background-color` attribute (`#dcfce7`/`#fef3c7`/`#fee2e2` in this
   demo file). Thread the result into the existing `zone_to_agent_type()` call so BPMN-only import
   assigns `BaseAgent`/`K9ValidationLoopAgent`/`K9CriticActorAgent` and HITL flags exactly like
   spec-import already does. Test: re-import the AP invoice BPMN, confirm all 7 agents land in the
   zone Process Studio assigned (9 GREEN / 4 AMBER / 1 RED across the 14 steps).
3. **Canvas zone tint.** Add a zone-colored border/badge to agent nodes in `Canvas.tsx`, sourced
   from the zone the backend now computes in step 2. Additive only — doesn't touch the existing
   role-based node coloring (router/orchestrator/squad).
4. **Mapping document generator.** New small agent/service that emits a downloadable `.md`
   crosswalk (BPMN lane/task ↔ K9-AIF component ↔ zone ↔ HITL touchpoint) from data already
   extracted in steps 2–3 — no new parsing, just a formatted report step at the end of the import
   squad.
5. **(Deferred, low priority)** `spec_parsing_service.py` §1.8 vs §3.1.8 heading regex fix — only
   if spec-doc (`.md`) import needs to work for this demo too, alongside BPMN.
6. **Demo dry run** — import both AP invoice artifacts (BPMN primary, `.md` if step 5 is done),
   confirm canvas + mapping doc together tell a clean story before showing IBM.

## Open items

- [ ]  Confirm `studiox_v2` visibility (public/private) — not yet decided
- [ ]  Decide where the Sonnet-vs-local-model positioning note gets used
