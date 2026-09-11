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

### Pipeline order — decision (2026-09-10): mapping document first, no LLM for structured input

**Do not use the backend LLM (e.g. qwen3.8:27b) to generate the canvas for structured Process
Studio input.** The `.md`/`.bpmn` already carries everything needed — coded IDs, explicit
GREEN/AMBER/RED zones, explicit HITL specs — via deterministic parsing (exactly what
`bpmn_service.py`/`spec_parsing_service.py` already do, rule-based, no LLM). Feeding an
already-structured document through an LLM "suggest" step (`force_llm`, `LLMGroupingAgent`) would
trade a traceable extraction for a probabilistic one, for input that doesn't need interpreting.
The LLM-suggest path still has a real job — genuinely unstructured input (free-text description, a
hand-drawn BPMN with no ID/zone convention) — just not this.

**Reorders the pipeline, not just "skip the LLM":** today's flow is *import → suggestion JSON →
canvas (nodes/edges) → re-serialize edges → scaffold* — three independent re-representations of
the same relationships. That's the same shape of problem as the orchestrator/squad wiring bug we
just fixed (which was pure array-indexing, not an LLM issue at all — the risk is re-deriving
relationships at each hop, with or without an LLM in the loop). The fix: generate the **mapping
document first**, as a deterministic crosswalk (this *is* the Traceability Matrix above, built at
import time rather than reconstructed after the fact) — then canvas and scaffold are both
**rendered from the mapping document**, not independently re-derived from raw parsing or from
each other. The "Match?" column becomes true by construction instead of something to verify by
parsing generated code after the fact.

**Cheapest concrete check, falls out for free from this architecture:** orchestrator/squad/agent
*counts* in the mapping document must equal counts in the generated canvas and in the generated
scaffold — exactly, not approximately. If the mapping doc says 7 agents, the canvas must show 7
agent nodes and the scaffold must contain 7 agent files. Any mismatch is an immediate, legible
signal something broke, cheaper to check than the full per-ID row comparison.

### Implementation steps (2026-09-10, merged — mine + Ravi's refinements, confirmed "good")

Status: **1, 2, 3, 4, 5, 8 done and verified (including a real browser click-through, not just
direct calls) — 6, 7 not started.** Working autonomously per Ravi's "keep implementing, I'll
review tomorrow morning." See each step below for what's verified and what's an open judgment
call flagged for review.

**Update (same evening, Ravi reviewed live):** found and fixed a real bug in step 5 — the
Traceability tab went blank after clicking Confirm (`handleConfirm()` was nulling out the exact
state the tab renders from). Fixed with a `mappingDocumentConfirmed` flag that persists the matrix
instead of clearing it (`studiox_v2` commit `6d40d40`). Also wrote `studio_rules.md` (studiox_v2
root) consolidating the Arch Guide tab's classification rules with this session's zone-mapping
rules and the HIL Orchestrator gap Ravi flagged ("HIL is a separate orchestrator," "canvas has no
HIL") — confirmed in code that HIL wiring is Kafka-direct/event-driven and currently
manual-only with generic placeholders, not derived from real AMBER/RED agents; stated as an open
Step 6 design item. **Also ran the generic-studio verification that was outstanding**: a second,
deliberately different BPMN (insurance claims, 3 lanes not 7, zero color extension at all) against
the live running backend — correct output throughout, including graceful zone=None fallback to
name-keyword heuristics. Test file + response saved in `cross-domain-test/`. This was asked for
directly by Ravi ("what if I upload a totally different BPMN file? will it work?") rather than
just asserted from code-reading confidence.

**Update (same evening, continued live with Ravi) — Step 6 built and verified:**
`studiox_v2` commit `19094ab`. Canvas sub-tabs (All/Orchestrators/Squads/Adapters/HIL) — Ravi's
design, a pure filter over the same nodes/edges (`canvasLayers.ts`), never a second layout;
orchestrators with zero matching children hidden per layer (Ravi confirmed this is right).
Column backgrounds ("first column is Router, and so on") — computed from `layout.ts`'s own
`LEVEL_X` table so they can't drift from actual node positions; fixed a real pre-existing bug
found along the way (`hil_orchestrator` had no `LEVEL_X` entry, was silently landing in the
adapter column). JPG export button (`html-to-image`, new dep). Refresh persistence
(`zustand`'s `persist` → `localStorage`) for a real bug Ravi hit ("if I refresh the page,
everything disappears") — first pass persisted data but not which tab was showing, so it still
*looked* broken after reload; caught and fixed via the same real-browser verification, not
assumed fixed. All verified via Playwright on a separate port (not Ravi's running instance) —
screenshots `04`–`07` in `verification-screenshots/`.

**Update (same stretch) — column spacing + zoom floor, commit `17e4b5f`:** widened `layout.ts`'s
`LEVEL_X` column spacing (Squad↔Adapter was only 160px apart, now 250px) per Ravi's "panes can be
wider" note, and capped auto-fit at 75% zoom minimum (`minZoom={0.75}` — Ravi's own constraint:
"25% shrink to the best... making it too small is useless") so a wide process pans instead of
shrinking into unreadable text. Along the way, found and fixed a real instance of the session's
recurring bug class: `canvasLayers.ts`'s `computeColumnBands()` had its **own hardcoded copy** of
the column x-positions instead of importing `layout.ts`'s `LEVEL_X` — hadn't drifted yet, but this
same widening change would have been the first real drift had it not been caught. Verified via
Playwright, screenshot `08` in `verification-screenshots/`.

**Confirmed, not fixed:** `theme`/`toggleTheme` exist in `store.ts` but are referenced nowhere in
any component — orphaned state, no UI control. Every component (including everything built
tonight) hardcodes dark-mode hex colors directly rather than theme tokens. A real light/dark
toggle would be a substantial refactor across every component, not a quick switch — flagged to
Ravi as its own dedicated pass, not undertaken tonight.

**Open, smaller items from this stretch, not yet done:**
- Canvas area width is whatever's left after the ~290px palette sidebar; a collapse toggle for
  that sidebar would give the canvas more room — separate, valid UI change.
- Class Diagram tab's "open full size" view is missing a scroll bar (right side cut off) and has
  no zoom/magnify control, unlike the Canvas tab's +/− controls — Ravi flagged both; not yet
  fixed (existing studiox feature, not something built tonight).
- Session/user identity (Ravi's k9x_satan-style auto-generated unique ID idea): explicitly
  deferred — nothing server-side currently uses per-user data, so there's nothing yet for an ID
  scheme to key against. Revisit once real server-side persistence exists.
- Redis: confirmed not in use and not the right fix for the refresh bug (that was a pure
  client-side gap, `localStorage` is the correct minimal fix — done above). Would only matter for
  genuine multi-device/multi-user session continuity, not asked for yet.
- **Comprehensive generated document** (Ravi's idea, self-scoped down from a fuller ops-config
  generator): traceability matrix + a subset-of-canvas JPEG + governance/static framework info +
  the existing class diagram, **plus a checklist of things for a Solutions Architect to do**
  (not filled-in tables for Kafka topics/DB tables/S3 buckets/vault credentials — Ravi decided
  against building that, a checklist is enough). Ties together `ARCHITECTURE.md` generation
  (existing), the mapping document (built tonight), canvas JPEG export (built tonight), and the
  class diagram (existing) into one document. Not started — real next step after the smaller
  items above.

**For tomorrow's review, in one paragraph:** the full pipeline works end-to-end and is proven,
not assumed — upload the real AP invoice BPMN, land on a new Traceability tab (not Canvas) showing
the matrix with real governance/zero-trust/HITL findings, review or edit zone/agent-type, confirm,
and the canvas builds correctly with every orchestrator wired to its own squad (screenshots in
`verification-screenshots/`). Steps 6 (tabbed multi-flow canvas — Main + HIL) and 7 (scaffold
generated directly from the mapping document, not re-serialized canvas edges) are genuinely
bigger architectural changes — I deliberately did not rush into them without your input, since 6
requires a real design decision (how to partition a flow into named tabs) and 7 changes how
scaffold generation gets its data. Recommend reviewing 1–5+8 first, then deciding 6/7's shape
together rather than me guessing overnight.

1. **✅ DONE — carry the BPMN's own task/lane element ids through.** `classify_task()` currently looks up
   zone by task `id` (`Task_1`, `Lane_1`, ...) then discards the id. Needs to be kept — it's the
   Process ID column source. Process Studio's ATS#/AGN# numbering only lives in the `.md`, not the
   `.bpmn`, so for BPMN-only import the BPMN's own element id is the generic, always-available
   identifier (works for *any* BPMN, not just Process Studio's convention).
2. **✅ DONE — build `build_mapping_document()`** — columns wider than originally scoped, per Ravi's point:
   not just structural wiring (Process ID | Element | Zone | Orchestrator | Squad | Agent | Agent
   Base Type | HITL Touchpoint) but **which framework mechanisms wrap each component**:
   - **Governance** — whether/how `require_governance()`/`enforce_governance()` applies. Not yet
     investigated whether generated agent templates actually call `enforce_governance()` — check
     during implementation, don't assume.
   - **Zero Trust** — every generated orchestrator already calls `self.apply_zero_trust(payload)`
     unconditionally (seen in `orchestrator.py.j2` this session). Open question for
     implementation: does/should this vary by zone (e.g. stricter policy for RED), or is it
     uniform today? Don't assume either answer yet.
   - **Model Router** — `K9ModelRouter`'s weighted-scoring inputs (task_type, sensitivity,
     latency_budget, cost_profile) currently collapse to a flat `model: "reasoning"|"general"`
     field with no *why* traced. Note: actual model selection is a **runtime** decision (scored
     per-request), not fixed at generation time — the matrix can show the static *inputs* to
     routing (configured per agent), not a fixed routing outcome. Don't conflate the two.
3. **✅ DONE — expose it from `/api/bpmn/import`, additively** — `"mapping_document": {...}`
   alongside the existing `"suggestion"` key. Verified via live HTTP round-trip.
4. **✅ DONE (came for free from step 2's design) — count-check** —
   `mapping_document.counts = {orchestrators, squads, agents, adapters}` already in the response.
5. **✅ DONE, real-browser-verified (commits `4c7f5fe`, `40daffe`) — surface it in the UI, editable,
   as a hard gate.** New "Traceability" tab, `MappingDocumentPanel.tsx`. Verified via Playwright
   against the actual running app (not just direct calls/HTTP — first real browser-level check
   this session): logged in, uploaded the real AP invoice BPMN, landed on Traceability
   automatically (not Canvas), matrix rendered correctly, clicked "Confirm & Build Canvas", canvas
   rendered with every orchestrator wired to its own squad — Agn4's squad visibly has a **red top
   border** (the exact wiring bug, now proven fixed end-to-end in the real UI). Zero console/page
   errors. Screenshots in `verification-screenshots/`. Found and fixed a real row-height bug along
   the way (governance/zero-trust/HITL text was wrapping to 8-10 lines per row — now truncated
   with a hover tooltip).
   Scope note: only the BPMN import path is gated — spec-doc import and template paths still go
   straight to canvas, not touched in this pass. Ravi's
   refinement: human can verify *or modify* the mapping document; scaffold generation is blocked
   until explicit confirmation. Nice resonance for the pitch — the studio practices the same
   human-in-the-loop discipline on its own output that the AMBER/RED agents it generates practice
   on theirs.
6. **Canvas rendered from the mapping document — as tabbed, possibly-multiple flows, not one
   canvas.** Ravi's addition: one **Main** tab for the full end-to-end flow, plus named tabs for
   coherent sub-flows when the process is complex enough to warrant it — **HIL** being the obvious
   first case (5 of 7 agents in the AP invoice example are AMBER/RED with HITL touchpoints; a
   dedicated HIL-flow tab showing just that path is concretely useful here, not hypothetical).
   Fits the existing HIL Orchestrator palette component rather than inventing something new.
   `Palette.tsx.buildCanvas()` reads from mapping-document rows instead of the separate
   `suggestion` shape — collapses two parallel representations into one.
7. **Scaffold generation from the mapping document, gated on step 5's confirmation** — not
   reverse-parsing generated files to check correctness after the fact (what I did by hand this
   session). "Match?" becomes true by construction; count-check (step 4) plus a spot audit is
   enough.
8. **✅ DONE (commit `83fe3d5`) — lock down "no LLM for structured input" explicitly.** Confirmed
   the gap was real, not hypothetical: `bpmn_import` took the LLM path whenever `llm_config` was
   truthy, and the frontend sent it automatically whenever *any* LLM was configured
   session-wide — with no BPMN-specific UI to opt into that deliberately. Backend now requires
   `force_llm` alongside `llm_config` (mirrors spec_import's existing pattern); frontend stopped
   sending `llm_config` on BPMN upload at all. BPMN import is deterministic, always, now — not
   just by accident.

Steps 1–4 are backend-only, independently verifiable via direct calls (same pattern as this
session's bug fixes). 5–7 touch the frontend and are where the real re-architecture happens
(tabs, edit+confirm gate). 8 is small, can slot in anywhere.

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

1. **✅ FIXED (studiox_v2, commit `15041b4`) — every orchestrator loaded the wrong squad.**
   Traced all 7 generated orchestrators' `_SQUAD_ID` and imports: each one was wired to a
   different lane's squad (Agn1→Agn2's squad, Agn2→Agn3's, Agn3→Agn4's, Agn4→Agn6's, Agn5→Agn7's,
   Agn6→Agn2's, Agn7→Agn2's). Concretely: invoking "AGN4 Anomaly/Fraud Detection" (the RED-zone,
   dual-approval step) actually ran the expense-audit agent instead. Root cause: purely
   positional pairing (`orchestrators[i]` ↔ `squads[i]` by array index) in
   `frontend/src/components/Palette.tsx`, plus a matching `squads[0]` fallback anti-pattern in
   `Studio.tsx` and `backend/services/scaffold_service.py`. `bpmn_service.py`'s orchestrators list
   includes every lane (GREEN adapter-only lanes included) while its squads list only includes
   lanes that produced an agent — so array positions diverge the moment any earlier lane has no
   squad. Fix: `bpmn_service.py` now emits an explicit `squads` list per orchestrator (all three
   BPMN shapes — lanes, subprocesses, flat tasks); the frontend uses that explicit linkage
   (falling back to name-stem matching, never position, for suggestion shapes that lack it); the
   `squads[0]` fallbacks were removed — an orchestrator can legitimately own zero squads.
   Verified end-to-end: all 7 orchestrators now load their own squad/agent; AGN1/AGN5 (GREEN)
   correctly generate with no squad instead of stealing one.
2. **✅ FIXED (studiox_v2, commit `15041b4`) — RED-zone agent under-generated.**
   `ReviewDetectMatchingExceptionsAgent` (AGN2, AMBER) was correctly generated as
   `K9ValidationLoopAgent`; `DetectInvoiceAnomaliesAgent` (AGN4, RED — dual human approval,
   cannot be overridden per the source blueprint) was generated as a bare `BaseAgent`, single LLM
   call, no escalation. Root cause: `_agent_type()` in `bpmn_service.py` selected agent type by
   name-keyword heuristic only, and "Detect Invoice Anomalies" matched none of the keywords
   (validat/verif/check/review/audit/... or generat/draft/critique/...) — silently falling
   through to `BaseAgent` regardless of zone. This is also the zone-color-extraction step scoped
   below. Fix: read each task's zone color from its BPMNShape fill (matched generically by
   attribute suffix, not a hardcoded namespace URI) and use zone as the authoritative signal,
   falling back to the name-keyword heuristic only when no zone color is present. Verified:
   `DetectInvoiceAnomaliesAgent` now generates as `K9CriticActorAgent`.
3. **`config/scenario.json` is generic/unrelated** ("Overnight Risk Run — Portfolio PF-10231"),
   not derived from the imported AP invoice process at all. Lower severity, not yet fixed.
4. **Confirmed (2026-09-10, not a bug fix — a scoping finding for the mapping document): GREEN
   zone (adapters) generate zero executable code.** Checked `scaffold_service.py` for every
   "adapter" reference — all of them are inside `ARCHITECTURE.md` generation (descriptive
   markdown only). No `.py` file is ever produced for an adapter, and a GREEN-only orchestrator's
   `execute_flow()` calls `execute_squads([])` — a no-op, confirmed via the earlier `_SQUAD_IDS =
   []` verification. In the AP invoice example this is 9 of 14 steps (the majority — AGN1 +
   AGN5). Not something to silently paper over in the mapping document — the Agent Base Type
   column should say plainly "no code generated" for adapter rows, not a fabricated class name.
   Also checked governance: no generated agent template (`agent_base.py.j2`,
   `agent_validation_loop.py.j2`) calls `enforce_governance()` — every generated agent silently
   runs under `NoopGovernance` regardless of environment. Zero Trust *is* real: every generated
   orchestrator calls `self.apply_zero_trust(payload)` unconditionally, but it's uniform, not
   zone-differentiated. These three facts (no adapter code, unenforced governance, uniform zero
   trust) are what the mapping document's new Governance/Zero-Trust/Agent-Base-Type columns will
   actually report — verified, not assumed.

**Regression check:** `backend/tests/test_scaffold_service.py` — 8/9 pass (all previously
unrunnable without `K9X_GENERATOR_TEMPLATES_DIR` set, an undocumented requirement this exposed).
The 1 remaining failure (`test_multi_squad_orchestrators_load_independently`) is pre-existing,
confirmed via `git stash` — an unrelated `k9-aif` framework API mismatch (`BaseOrchestrator` has
no `.start()` method), not a regression from this fix.

## Step-by-step enhancement plan (in `studiox_v2`)

1. **✅ DONE — local runnable baseline.** `.venv` + `pip install -r requirements.txt` (works;
   `K9X_GENERATOR_TEMPLATES_DIR` must point at `k9-aif-framework/generator/templates` — undocumented
   until this pass, now noted), `.env` from `.env.sample` (placeholder LLM endpoint — fill in the
   real one before live inference tests). Frontend `npm install` not yet run (fix so far verified
   via direct backend calls + `pytest`, not through the actual UI).
2. **✅ DONE — `bpmn_service.py` zone-color extraction**, folded together with the orchestrator/squad
   wiring fix since both root-caused in the same investigation (see "Known bugs" above, commit
   `15041b4`). Verified against the real AP invoice BPMN: all 7 agents land in the zone Process
   Studio assigned.
3. **✅ DONE — canvas zone tint (commit `acd0a92`).** Both a per-agent badge and a per-squad
   ("lane") top-edge accent, per the 2026-09-10 decision. `zone` threaded as its own explicit
   field (`types.ts`: new `Zone` type) all the way from `bpmn_service.py` through `Palette.tsx` to
   `K9Node.tsx`, additive to existing role-based coloring. Carbon strong-accent triad
   (`#24a148`/`#f1c21b`/`#da1e28`). Verified: `npm install` + `tsc --noEmit` + `vite build` clean;
   live HTTP round-trip against a running backend confirms the real API response carries correct
   zone data, not just direct function-call testing.
4. **Mapping document generator / Traceability Matrix** — not yet done. This is now the primary
   deliverable (see above) — a new small agent/service emitting the Process→Implementation
   Traceability Matrix from data already extracted during import (steps 2–3), including the
   "Match?" self-check column.
5. **(Deferred, low priority)** `spec_parsing_service.py` §1.8 vs §3.1.8 heading regex fix — only
   if spec-doc (`.md`) import needs to work for this demo too, alongside BPMN.
6. **Demo dry run** — import both AP invoice artifacts (BPMN primary, `.md` if step 5 is done),
   confirm canvas + mapping doc together tell a clean story before showing IBM. Also need to
   actually run the app through the real UI at least once (frontend `npm install` + `run.sh`) —
   everything verified so far is backend-only, direct-call testing.

## Open items

- [ ]  Confirm `studiox_v2` visibility (public/private) — not yet decided
- [ ]  Decide where the Sonnet-vs-local-model positioning note gets used

**Update (same stretch) — node label trim, `studiox_v2` commit `7475e5b`:** dropped the redundant
"Agent" filler word from squad/orchestrator labels (`Agn4AnomalyDetectionAgentSquad` →
`Agn4AnomalyDetectionSquad`) since the type badge above each box already says SQUAD/ORCHESTRATOR —
display-only, underlying names unchanged everywhere else. Screenshot `09` in
`verification-screenshots/`.

**Update (same stretch) — Orchestrator abbreviated to Orch, `studiox_v2` commit `53ff03f`:**
node labels now show `...Orch` instead of `...Orchestrator` (Squad stays full, per Ravi's
"in Canvas, it can be Squad"). Display-only, same `displayLabel()` trim point. Screenshot `10`.

**Update (working overnight per Ravi's "keep working on other steps to make it much richer") —
detailed-design.md + a real production bug fix, `studiox_v2` commits `d252f05`, `853ea7e`:**

1. **Class Diagram scroll/zoom fixed** (`d252f05`). Root cause: `.classdiagram-canvas img` had
   `max-width:100%`, which meant the image could never actually overflow its container — so
   `overflow:auto` had structurally nothing to scroll (matches Ravi's report: "no scroll bar to
   scroll, right side is cut off"). Removed the cap, added zoom controls (+/−/Reset, 25%-300%) per
   Ravi's ask ("a + sign to magnify"). Verified: `scrollWidth` (6258px) now genuinely exceeds
   `clientWidth` (1305px) after zooming — real overflow, not theoretical. Screenshot `11`.

2. **`detailed-design.md` added to every generated scaffold** (`853ea7e`) — the "detailed-design.doc
   to be expanded by the SA" Ravi asked for. Built from `build_mapping_document()` reused directly
   (same source of truth as the Traceability tab, not reimplemented). Contains: executive summary
   + zone breakdown, the full traceability matrix, governance/zero-trust notes (stated once, not
   per row), and a **Solutions Architect checklist** (governance enforcement, zero trust policy,
   Kafka topics, DB schema, object storage, secrets/vault, HITL routing, model selection,
   observability) — a checklist, not filled-in ops tables, per Ravi's explicit scope-down. Links
   to `https://k9x.ai/developer_guide` and `https://patterns.k9x.ai/` in both `detailed-design.md`
   and `README.md`.

3. **Found and fixed a real, previously-undiscovered production bug** while verifying the above:
   `ProjectDef`/`AgentDef`/`SquadDef`/`OrchestratorDef` (the Pydantic models validating
   `/api/generate` and `/api/scaffold-preview` — the actual endpoints "Generate Scaffold" calls)
   had **no `adapters` field at all**, and no `zone`/`process_id` fields on Agent/Squad/
   Orchestrator. Pydantic silently drops undeclared fields, so **every real scaffold-generation
   request through the actual UI has been dropping all adapter data** and all zone/process_id
   data, regardless of what the frontend or `bpmn_service.py` sent. Confirmed via live HTTP test
   (sent 13 adapters, `ARCHITECTURE.md` showed 0) before fixing; re-verified after (correct count,
   correct zone breakdown, all 18 matrix rows). This means every scaffold generated all evening —
   including the ones used for the earlier bug-hunting session — had this gap; the direct
   Python-function-call testing done earlier tonight bypassed it entirely, which is exactly why it
   wasn't caught until testing the real HTTP path specifically for this feature.

4. **Full real-UI verification, not just API**: logged in, uploaded the real AP invoice BPMN,
   confirmed the mapping document, clicked "Generate Scaffold" for real (download event fired),
   opened "View Scaffold" — `detailed-design.md` visible in the actual file tree alongside
   `ARCHITECTURE.md`/`README.md`. Screenshot `12`. Zero console errors throughout.

**Not yet done, explicitly deferred:** embedding an actual canvas JPEG into the scaffold
automatically (would require the frontend to capture and POST the image alongside the scaffold
request; `detailed-design.md` currently just instructs the SA to export and attach it manually).
Sidebar collapse for a wider canvas — still open, lower priority than what's been done tonight.
