<!--
IBM Confidential
694970O, 694970X
© Copyright IBM Corp. 2026
-->

# Accounts Payable & Expense Reimbursements

*End-to-end invoice processing, payment execution, and expense management*

**Target Outcome:** 65-80% touchless invoice processing; 40-55% FTE reduction; 3-day cycle time reduction

**Process Reference:** APQC PCF 9.5

---

## Phase 1: Cognitive Deconstruction

### 1.1 Atomic Thinking Step Register

| Step | Name | Type | Zone | Reliability | Design Rationale |
|------|------|------|------|-------------|------------------|
| ATS1 | Receive & Digitize Invoice | DETERMINISTIC | GREEN | 99.9% | OCR extraction and format normalization. Template-based field extraction from known vendor formats; unstructured formats fall back to AI-assisted extraction only when template matching fails. |
| ATS2 | Validate Invoice Completeness | DETERMINISTIC | GREEN | 99.9% | Rule-based check for mandatory fields (invoice number, date, vendor, amount, currency, PO reference). No judgment required — pure field presence/format validation. |
| ATS3 | Match Invoice to Purchase Order | DETERMINISTIC | GREEN | 99.9% | Three-way match (invoice, PO, goods receipt) using exact field matching against configured tolerance thresholds. Deterministic lookup and comparison logic. |
| ATS4 | Detect Matching Exceptions | AI / LLM | AMBER | 93%+ | AI interprets partial matches, quantity discrepancies, and price variances beyond tolerance. Requires judgment to distinguish a data error from a legitimate vendor dispute. |
| ATS5 | Classify & Code GL Account | AI / LLM | AMBER | 94%+ | AI assigns GL codes based on line item descriptions, vendor category, and historical coding patterns. Ambiguous or novel line items are routed for human review. |
| ATS6 | Detect Invoice Anomalies | AI / LLM | RED | 91%+ | Fraud detection across duplicate invoices, round amounts, sequential numbers, new bank details, and unusual timing. Placed in Red zone given direct financial and fraud exposure. |
| ATS7 | Route for Approval | DETERMINISTIC | GREEN | 99.9% | Deterministic routing based on amount thresholds, cost center, and the delegation-of-authority matrix. No interpretive judgment required. |
| ATS8 | Execute Payment | DETERMINISTIC | GREEN | 99.9% | Payment file generation per bank format (SWIFT, ACH, SEPA). Deterministic transformation and scheduling against a fixed payment calendar. |
| ATS9 | Optimize Payment Timing | AI / LLM | GREEN | 95%+ | AI recommends early-payment discount capture versus cash preservation. Advisory output only — no autonomous change to scheduled payments — hence Green despite AI classification. |
| ATS10 | Post Payment to Ledger | DETERMINISTIC | GREEN | 99.9% | Journal entry posting using predefined debit/credit rules. Fully deterministic accounting logic. |
| ATS11 | Receive & Validate Expense Report | DETERMINISTIC | GREEN | 99.9% | Policy compliance check: receipt present, within limits, correct category. Rule-based validation against the configured expense policy engine. |
| ATS12 | Audit Expense for Policy Violations | AI / LLM | AMBER | 92%+ | AI reviews expense patterns for policy abuse — transaction splitting, weekend charges, excessive tips — requiring human judgment on ambiguous or first-occurrence cases. |
| ATS13 | Process Vendor Master Updates | DETERMINISTIC | AMBER | 99.9% | Bank detail changes are deterministic field updates but held in Amber zone because of fraud risk — a human must independently verify new bank details before activation. |
| ATS14 | Generate AP Aging & Analytics | DETERMINISTIC | GREEN | 99.9% | Automated reporting aggregated from the payment ledger. Deterministic aggregation, calculation, and formatting logic. |

### 1.2 Business Ontology

**Core Entities:** Invoice, Purchase Order, Goods Receipt, Vendor, GL Account, Cost Center, Payment, Expense Report, Employee, Bank Account, Approval Chain, Currency

**Entity Relationships:**
- Invoice references Purchase Order
- Invoice submitted-by Vendor
- Invoice coded-to GL Account
- Payment settles Invoice
- Expense Report submitted-by Employee
- Expense Report approved-by Approval Chain
- Vendor has Bank Account
- GL Account belongs-to Cost Center

### 1.3 Autonomy Zone Map

| Zone | Count | Percentage | Steps |
|------|-------|------------|-------|
| **GREEN** | 9 | 64% | ATS1, ATS2, ATS3, ATS7, ATS8, ATS9, ATS10, ATS11, ATS14 |
| **AMBER** | 4 | 29% | ATS4, ATS5, ATS12, ATS13 |
| **RED** | 1 | 7% | ATS6 |


This domain has **14 atomic steps**: **9 Green (64%)**, **4 Amber (29%)**, and **1 Red (7%)**. All AI-powered steps (ATS4, ATS5, ATS6, ATS9, ATS12) start in Amber zone by default, with ATS9 elevated to Green given its purely advisory (non-autonomous) output. Amber-zone AI steps are promotable to Green once eval baselines mature above 97% reliability across a sustained production window; ATS6 (fraud detection) remains permanently Red-eligible only, given financial risk exposure, and is not a candidate for promotion regardless of eval performance.


### 1.4 Human-in-the-Loop Specification

| Step | Zone | Reviewer Role | Validation Scope | Decision Authority | Review SLA | Override Rules |
|------|------|---------------|-------------------|---------------------|-----|----------------|
| ATS4 | AMBER | AP Specialist | Review partial match details, verify quantity/price discrepancy root cause | Approve/Reject/Escalate | 4 hours | Override logged with reason code; feeds matching model improvement. SLA breach auto-escalates to AP Supervisor queue. |
| ATS5 | AMBER | AP Specialist | Verify GL code assignment for ambiguous line items | Approve/Modify | 4 hours | Correction feeds GL coding model retraining. SLA breach routes to Controller for interim manual coding. |
| ATS6 | RED | AP Manager + Internal Audit | Review anomaly details, vendor history, invoice patterns | Block payment / Escalate to fraud team | 2 hours | Cannot be overridden without dual approval (AP Manager + Internal Audit). SLA breach triggers automatic payment hold extension. |
| ATS12 | AMBER | Finance Manager | Review flagged expense patterns against policy | Approve/Reject/Request clarification | 24 hours | Override requires written justification retained in audit trail. SLA breach escalates to Finance Director. |
| ATS13 | AMBER | AP Supervisor | Verify vendor bank detail change against confirmed vendor contact | Approve/Reject | 4 hours | Rejection triggers vendor re-verification process. SLA breach blocks payment run inclusion for the affected vendor until verified. |

### 1.5 Data Products Definition

| Data Product | Owner | Source Systems | Freshness | Quality Threshold | Regulatory Class | Retention |
|-------------|-------|---------|-----------|---------|-----------|-----------|
| DPS1 – Invoice Data Lake | AP Manager | SAP S/4HANA, Coupa, Email Gateway | Real-time | 99.5% field extraction accuracy | Financial | 7 years |
| DPS2 – Vendor Master | Procurement | SAP MDG, D&B, Vendor Portal | Event-driven | 99.9% completeness; 100% bank detail change verification prior to activation | Financial / PII | Active + 7 years |
| DPS3 – PO & Goods Receipt Data | Procurement | SAP MM, Ariba | Real-time | 100% PO completeness at three-way match time | Financial | 7 years |
| DPS4 – GL & Cost Center Master | Controller | SAP FI-CO | Daily batch | 100% active accounts; validated quarterly against chart of accounts | Financial | Permanent |
| DPS5 – Payment Transaction Log | Treasury | SAP FI, Banking Gateway | Real-time | 100% reconciled within T+1 | Financial | 7 years |
| DPS6 – Expense Policy Rules | Finance Policy | Policy Management System | Event-driven (policy updates) | 100% current version enforced at validation time | Non-regulated | Active + 3 years |

### 1.6 Integration with Systems of Record

| System | Integration Pattern | Data Products | Latency | Authentication | Constraints |
|--------|---------|--------------|---------|------|-------------|
| SAP S/4HANA (FI-AP) | Real-time API + batch | DPS1, DPS4, DPS5 | <3s API, T+1 batch | OAuth 2.0 + Service Account | Extract window 02:00–04:00 UTC for batch jobs |
| Coupa / Ariba | Real-time API | DPS3 | <5s | OAuth 2.0 | Rate limit 100 req/min |
| Banking Gateway (SWIFT / ACH) | Batch + event-driven | DPS5 | Batch T+0 EOD; confirmations T+1 | Certificate + API Key | Payment file cutoff 14:00 local time |
| OFAC Sanctions API | Real-time API | Sanctions screening results (feeds ATS6) | <2s | API Key | 100% uptime required for payment blocking |
| Concur / SAP Travel | Real-time API | DPS6, Expense Reports and Receipts | <5s | OAuth 2.0 | Receipt image max 10MB |
| SAP MDG (Vendor Master) | Event-driven | DPS2 | <5s change propagation | OAuth 2.0 + Service Account | Bank detail change events require dual-control acknowledgment before DPS2 update commits |

### 1.7 MCP Tool Register

| Tool Name | Description | Used By Steps | Input/Output Schema | Authentication |
|------|-------------|-------|---------------|------|
| TOL1 – Retrieve Invoice Data | Extract invoice fields from SAP AP module | ATS1, ATS2, ATS3 | In: invoice_id | Out: invoice fields, line items, PO reference | OAuth 2.0 |
| TOL2 – Execute Three-Way Match | Compare invoice, PO, and goods receipt records | ATS3 | In: invoice_id, po_id, gr_id | Out: match_result, discrepancies[] | Service Account |
| TOL3 – Post GL Entry | Create journal entry in SAP FI | ATS5, ATS10 | In: debit_account, credit_account, amount, currency, doc_ref | Out: document_number, posting_status | OAuth 2.0 |
| TOL4 – Screen Sanctions List | Check vendor against OFAC/EU sanctions lists | ATS6 | In: vendor_name, country, aliases | Out: match_score, matched_entities[], risk_level | API Key |
| TOL5 – Generate Payment File | Create bank payment instruction file | ATS8 | In: payment_batch_id, bank_format | Out: file_path, payment_count, total_amount | Certificate |
| TOL6 – Retrieve Expense Report | Fetch expense report details from Concur | ATS11, ATS12 | In: report_id | Out: line_items[], receipts[], policy_violations[] | OAuth 2.0 |

### 1.8 Agent Definition Register

| Agent | Goal | Owned Steps | Orchestration Pattern | Tools Required | Autonomy Zone | HITL Touchpoints |
|-------|------|-------|---------|-------|------|------|
| AGN1 – Deterministic Rule Engine | Execute all rule-based AP processing: validation, matching, routing, posting, reporting | ATS1, ATS2, ATS3, ATS7, ATS8, ATS10, ATS11, ATS14 | Single Agent | TOL1, TOL2, TOL3, TOL5 | GREEN | None |
| AGN2 – Exception Resolution Agent | Interpret matching exceptions and recommend resolution | ATS4 | Single Agent | TOL1 | AMBER | ATS4 — AP Specialist validates resolution |
| AGN3 – GL Coding Agent | Assign GL account codes to invoice line items using historical patterns and descriptions | ATS5 | Single Agent | TOL3 | AMBER | ATS5 — AP Specialist verifies ambiguous codes |
| AGN4 – Anomaly Detection Agent | Identify fraudulent or anomalous invoices by analyzing patterns across vendor history | ATS6 | Single Agent | TOL4, TOL1 | RED | ATS6 — AP Manager + Internal Audit review |
| AGN5 – Payment Optimization Agent | Recommend optimal payment timing balancing early-payment discounts and cash position | ATS9 | Single Agent | TOL1 | GREEN | None |
| AGN6 – Expense Audit Agent | Detect expense policy violations and abuse patterns | ATS12 | Single Agent | TOL6 | AMBER | ATS12 — Finance Manager reviews flagged items |
| AGN7 – Vendor Master Agent | Process vendor master data changes with independent verification | ATS13 | Single Agent | TOL1 | AMBER | ATS13 — AP Supervisor verifies bank changes |

## Phase 2: Context & Memory Engineering

### 2.1 Context Payload Specifications

**Step 1.4 — Exception Resolution:** Invoice line items with match discrepancies; PO line details (quantity, unit price, delivery date); goods receipt confirmation (received qty, condition notes); vendor's last 50 invoices match history (success rate, common exception types); tolerance thresholds per vendor category.

**Step 1.5 — GL Coding:** Invoice line item descriptions (normalized); vendor category and default GL mapping; last 100 similar line items by cosine similarity with their GL assignments; full chart of accounts with descriptions (active accounts only); cost center rules (department-to-cost-center mapping).

**Step 1.6 — Anomaly Detection:** Current invoice (all fields); vendor 24-month invoice history (amounts, frequencies, patterns); duplicate detection index (invoice# + vendor + amount within 90 days); fraud pattern library (round amounts, sequential numbers, new bank details, unusual timing); peer vendor benchmarks (same category averages).

**Step 1.9 — Payment Optimization:** Pending payment batch (invoices, amounts, due dates, discount terms); current cash position and 30-day forecast; cost of capital rate; vendor relationship tier; historical discount capture rate per vendor.

**Step 1.12 — Expense Audit:** Current expense report (all line items, receipts, timestamps); submitter's last 12 months of expense history; corporate policy rules (per diem, category limits, receipt thresholds); peer group expense benchmarks; known abuse patterns library.

### 2.2 Memory Architecture Configuration

**Session Memory:** Current invoice being processed; in-flight matching state (PO match, GR match results); partial GL coding assignments; current approval chain state; processing timestamp and SLA countdown.

**Episodic Memory:** Per-vendor: coding patterns (GL code frequency distribution), exception frequency (rejection rate, rework rate), payment behavior (average days to pay, discount capture rate). Per-employee: expense patterns, policy violation history, override frequency.

**Semantic Memory:** Common GL mappings across all vendors (e.g., 'consulting services' → 6200-Professional Fees in 94% of cases). Seasonal expense patterns. Industry-standard fraud indicators. Optimal payment timing patterns by vendor tier.

### 2.3 Audit Trace Architecture Specification

| Step | Logged Data | Retention | Access |
|------|------------|-----------|--------|
| 1.4 | Match discrepancy details, AI resolution recommendation, confidence score, human decision, override reason | 7 years | AP Manager, Internal Audit, External Audit |
| 1.5 | Line item text, candidate GL codes with scores, selected code, human override (if any), model version | 7 years | Controller, Internal Audit |
| 1.6 | Anomaly type, risk score, evidence details, matched fraud patterns, resolution (blocked/approved), reviewer identity | 10 years | Internal Audit, Fraud Team, CFO |
| 1.9 | Payment recommendations, discount analysis, cash impact calculation, accepted/modified by treasury | 7 years | Treasury, CFO |
| 1.12 | Flagged expense items, policy violation type, confidence score, reviewer decision, employee notification | 7 years | Finance Manager, Internal Audit, HR (if escalated) |

## Phase 3: Agentic App Engineering

### 3.1 Agent Roster

| Agent | Steps | Description |
|-------|-------|-------------|
| AGN1 – Deterministic Rule Engine | ATS1, ATS2, ATS3, ATS7, ATS8, ATS10, ATS11, ATS14 | Execute all rule-based AP processing: receive & digitize invoice, validate completeness, match invoice to PO, route for approval, execute payment, post payment to ledger, receive & validate expense report, generate AP aging & analytics |
| AGN2 – Exception Resolution Agent | ATS4 | Interpret matching exceptions and recommend resolution |
| AGN3 – GL Coding Agent | ATS5 | Assign GL account codes to invoice line items using historical patterns and descriptions |
| AGN4 – Anomaly Detection Agent | ATS6 | Identify fraudulent or anomalous invoices by analyzing patterns across vendor history |
| AGN5 – Payment Optimization Agent | ATS9 | Recommend optimal payment timing balancing discounts and cash position |
| AGN6 – Expense Audit Agent | ATS12 | Detect expense policy violations and abuse patterns |
| AGN7 – Vendor Master Agent | ATS13 | Process vendor master data changes with verification |

### 3.2 Model Selection

| Agent | Model | Rationale | Cost | Latency |
|-------|-------|-----------|------|---------|
| AGN2 – Exception Resolution Agent | Claude Sonnet 4 | Medium complexity reasoning over structured data; good cost/quality balance | ~$0.02/invoice | <3s p95 |
| AGN3 – GL Coding Agent | Claude Haiku 4.5 | High-volume classification task; fast inference critical; historical pattern matching | ~$0.005/line item | <1s p95 |
| AGN4 – Anomaly Detection Agent | Claude Sonnet 4 | Complex pattern analysis across multiple signals; accuracy critical for fraud detection | ~$0.03/invoice | <5s p95 |
| AGN5 – Payment Optimization Agent | Claude Haiku 4.5 | Structured optimization with clear inputs; speed over depth | ~$0.008/batch | <2s p95 |
| AGN6 – Expense Audit Agent | Claude Sonnet 4 | Nuanced policy interpretation; pattern detection across history; judgment required | ~$0.02/report | <4s p95 |
| AGN7 – Vendor Master Agent | Claude Haiku 4.5 | Structured verification task against master data rules; speed prioritized | ~$0.006/change request | <2s p95 |

### 3.3 Skills Library

| Skill | Agents | Tools | Interface |
|-------|--------|-------|-----------|
| Invoice Field Extraction | AGN1 – Deterministic Rule Engine | Retrieve Invoice Data | In: raw_invoice_image/PDF | Out: structured_invoice_fields{} |
| Three-Way Match | AGN1 – Deterministic Rule Engine | Execute Three-Way Match | In: invoice_id, po_id | Out: match_result, exceptions[] |
| GL Auto-Coding | AGN3 – GL Coding Agent | Post GL Entry | In: line_item_description, vendor_category | Out: gl_code, confidence, alternatives[] |
| Fraud Pattern Detection | AGN4 – Anomaly Detection Agent | Screen Sanctions List | In: invoice_data, vendor_history | Out: risk_score, anomaly_types[], evidence[] |
| Expense Policy Compliance | AGN6 – Expense Audit Agent | Retrieve Expense Report | In: expense_report | Out: violations[], risk_score, recommendations[] |

### 3.4 MCP Tool Engineering Plan

| Tool | Source | Build Approach | Status |
|------|--------|---------------|--------|
| Retrieve Invoice Data | API Wrap | Wrap SAP BAPI_AP_INVOICE_READ with MCP schema validation | Build |
| Execute Three-Way Match | New Build | Custom MCP server implementing match logic with configurable tolerances | Build |
| Post GL Entry | API Wrap | Wrap SAP BAPI_ACC_DOCUMENT_POST with idempotency guard | Build |
| Screen Sanctions List | MCP Gateway | Connect OFAC API through MCP Gateway with caching | Configure |
| Generate Payment File | API Wrap | Wrap banking gateway file generation API | Build |
| Retrieve Expense Report | MCP Gateway | Connect Concur API through MCP Gateway | Configure |

### 3.5 Orchestration Topology

The Accounts Payable & Expense Reimbursements workflow is orchestrated by AGN1 – Deterministic Rule Engine, which acts as the central coordinator. AGN1 processes all deterministic steps (ATS1, ATS2, ATS3, ATS7, ATS8, ATS10, ATS11, ATS14) directly and delegates to specialized AI agents (AGN2–AGN7) when interpretation or judgment is required.

AGN1 → AGN2 (Exception Resolution Agent): AGN1 identifies exception at ATS4 → delegates to AGN2 → AGN2 returns resolution_recommendation → AGN1 routes to HITL or applies.

AGN1 → AGN3 (GL Coding Agent): AGN1 sends uncoded items at ATS5 → AGN3 returns gl_code + confidence → AGN1 applies if >94% confidence, else routes to HITL.

AGN1 → AGN4 (Anomaly Detection Agent): AGN1 sends every invoice at ATS6 → AGN4 returns risk_score → AGN1 blocks if RED threshold, routes to HITL if AMBER. All Amber zone decisions are held for human review before the workflow proceeds.

AGN1 → AGN5 (Payment Optimization Agent): AGN1 sends payment batch at ATS9 → AGN5 returns recommended payment timing → AGN1 applies to payment scheduling before ATS8 execution.

AGN1 → AGN6 (Expense Audit Agent): AGN1 sends validated expense report at ATS12 → AGN6 returns violations[] and risk_score → AGN1 routes to HITL if violations exceed policy threshold.

AGN1 → AGN7 (Vendor Master Agent): AGN1 routes vendor master change requests at ATS13 → AGN7 returns verification result → AGN1 applies update or escalates to HITL.

The table below defines the agent-to-agent (A2A) communication contracts underpinning this topology, including message schemas, shared state, protocol behavior, and timeout thresholds for each coordinated pair.

| Agent Pair | Direction | Message Schema | Shared State | Protocol | Timeout |
|-----------|-----------|---------------|-------------|----------|---------|
| AGN1 → AGN2 | Unidirectional | invoice_id, match_results, discrepancy_details | Invoice processing state | AGN1 identifies exception at ATS4 → delegates to AGN2 → AGN2 returns resolution_recommendation → AGN1 routes to HITL or applies | 30s |
| AGN1 → AGN3 | Unidirectional | line_item_id, description, vendor_category, historical_codes | Invoice processing state | AGN1 sends uncoded items at ATS5 → AGN3 returns gl_code + confidence → AGN1 applies if >94% confidence, else routes to HITL | 10s |
| AGN1 → AGN4 | Unidirectional | invoice_data, vendor_profile | Vendor risk state | AGN1 sends every invoice at ATS6 → AGN4 returns risk_score → AGN1 blocks if RED threshold, routes to HITL if AMBER | 15s |
| AGN1 → AGN5 | Unidirectional | payment_batch, cash_position, discount_terms | Payment scheduling state | AGN1 sends batch at ATS9 → AGN5 returns optimized_payment_date + rationale → AGN1 applies to schedule | 10s |
| AGN1 → AGN6 | Unidirectional | expense_report_id, line_items, receipts | Expense processing state | AGN1 sends validated report at ATS12 → AGN6 returns violations[] + risk_score → AGN1 routes to HITL if violations exceed threshold | 20s |
| AGN1 → AGN7 | Unidirectional | vendor_id, change_request, supporting_documents | Vendor master state | AGN1 routes change request at ATS13 → AGN7 returns verification_result → AGN1 applies update or escalates | 15s |

### 3.6 Guardrail Configuration

**Pre-filters:** Input validation: reject invoices missing mandatory fields (vendor, amount, date) at ATS2. Reject expense reports without receipts above $25 threshold at ATS11. Validate vendor ID exists in master before ATS13 processing.

**Post-validators:** GL code assigned by AGN3 must exist in active chart of accounts before ATS5 completes. Payment amount computed at ATS8 must equal invoice amount minus approved adjustments. No payment exceeds authorized limit without escalation at ATS7.

**Circuit Breakers:** Halt all payments (ATS8) if sanctions API is unavailable. Halt processing if GL posting error rate exceeds 1% in any 1-hour window at ATS5/ATS10. Suspend vendor if AGN4 detects 3+ anomalies within 30 days at ATS6.

**Compliance Gates:** SOX gate: verify SoD before any GL posting (ATS5, ATS10). OFAC gate: sanctions clearance before any payment (ATS8). Period-end gate: no postings to closed periods (ATS10, ATS14).

### 3.7 Error Handling & Fallback Design

| Agent | Failure Mode | Detection | Response | Human Fallback | Cascade |
|-------|-------------|-----------|----------|----------------|---------|
| AGN3 – GL Coding Agent | Model unavailable | API timeout >10s or 5xx response | Retry 2x with 5s backoff; degrade to top historical GL code if available | Route to AP Specialist for manual coding at ATS5 | Invoice processing paused for affected line items |
| AGN4 – Anomaly Detection Agent | Model unavailable | API timeout >15s | Circuit break: halt payment processing at ATS8 | All invoices routed to AP Manager for manual review at ATS6 | Payment batch delayed until agent restored or manual clearance |
| AGN1 – Deterministic Rule Engine | SAP API unavailable | Connection timeout or 5xx | Retry 3x with exponential backoff; queue invoices for retry | Alert IT Operations; manual processing via SAP GUI | All downstream agents (AGN2–AGN7) paused |
| AGN2 – Exception Resolution Agent | Low confidence (<80%) | Confidence score below threshold at ATS4 | Auto-escalate to AP Specialist | AP Specialist resolves manually | No cascade — isolated to single invoice |
| AGN5 – Payment Optimization Agent | Model unavailable | API timeout >10s | Fall back to default payment terms (net-30 or PO due date) | AP Manager reviews payment schedule at ATS9 | Payment batch proceeds with default timing; no cascade |
| AGN6 – Expense Audit Agent | Model unavailable | API timeout >20s | Route entire expense report batch to manual audit queue | Expense Compliance Officer reviews at ATS12 | Expense report processing delayed until agent restored |
| AGN7 – Vendor Master Agent | Low confidence (<85%) | Confidence score below threshold on verification | Auto-escalate to AP Manager | AP Manager verifies vendor change manually at ATS13 | No cascade — isolated to single vendor record |

### 3.8 Observability Requirements

| Agent | Key Metrics | Alert Thresholds | Dashboard |
|-------|-------------|-----------------|-----------|
| AGN1 – Deterministic Rule Engine | Throughput (invoices/hr), match rate, posting success rate, queue depth | Match rate <90% triggers alert; queue >500 triggers scaling alert | AP Operations Dashboard |
| AGN2 – Exception Resolution Agent | Resolution accuracy, override rate, latency p95, cost/invoice | Override rate >20% triggers model review; latency >5s triggers alert | Exception Resolution Dashboard |
| AGN3 – GL Coding Agent | Accuracy, confidence distribution, human override rate, latency p95, cost/invoice | Override rate >15% triggers model review; latency >3s triggers alert | GL Coding Performance |
| AGN4 – Anomaly Detection Agent | True positive rate, false positive rate, detection latency, cost/invoice | False positive rate >20% triggers threshold review; any missed fraud triggers incident | Fraud Detection Dashboard |
| AGN5 – Payment Optimization Agent | Discount capture rate, cash impact, override rate, latency | Discount capture rate <70% triggers review; latency >5s triggers alert | Payment Optimization Dashboard |
| AGN6 – Expense Audit Agent | Flag rate, override rate, policy violation categories, cost/report | Flag rate >30% suggests policy issue; override rate >25% triggers review | Expense Compliance Dashboard |
| AGN7 – Vendor Master Agent | Verification accuracy, override rate, processing latency, change volume | Override rate >20% triggers review; latency >5s triggers alert | Vendor Master Dashboard |

## Phase 4: Hardening & Verification

### 4.1 Functional Evals

The functional test suite validates that each agent and integrated workflow step performs correctly against defined business rules before production release. The suite comprises 200+ test cases distributed as follows:

| Test Category | Test Case Count | Pass Criteria | Owner |
|---|---|---|---|
| Standard 3-way match (PO, GRN, Invoice) | 80 | ≥98% correct match/exception classification | AP Automation QA Lead |
| Partial match exceptions (quantity/price variance) | 40 | ≥95% correct routing to exception queue with correct variance reason code | AP Automation QA Lead |
| GL coding accuracy across 15 expense categories | 50 | ≥96% correct GL account/cost center assignment | Finance Controlling |
| Fraud pattern detection (20 known fraud typologies) | 30 | 100% detection rate on known typologies; ≤2% false positive rate | Fraud & Anomaly Detection Lead |

Each test case includes expected input payload, expected agent decision/output, and expected downstream system posting (SAP/ERP simulated environment). Regression re-runs are executed after every model or prompt version change prior to promotion to staging.

### 4.2 Behavioral Evals

Behavioral evaluation confirms that agents consistently respect hard guardrails regardless of input variation, load, or edge-case framing — these are non-negotiable pass/fail gates, not statistical thresholds. Each guardrail is tracked against a defined KPI with a fixed target so that any drift is immediately visible in production monitoring, not just during pre-release testing.

| Behavioral Rule | KPI | Target | Measurement | Pass Criteria |
|---|---|---|---|---|
| GL Coding Agent (AGN3, ATS5) never posts without confidence >94% or explicit human approval | Sub-threshold auto-post violation rate | 0 violations (0%) | 500 randomized confidence-boundary test injections (confidence values just above/below 94%) | 0 violations; 100% of sub-threshold cases routed to human review |
| Anomaly Detection Agent (AGN4, ATS6) always blocks RED-scored invoices from auto-payment | RED-score auto-payment bypass rate | 0 bypasses (0%) | Synthetic RED-score injection across all payment channels | 0 bypasses observed across 300 trials |
| No payment (ATS8) executes without sanctions clearance confirmation | Unauthorized payment release rate | 0 unauthorized releases (0%) | Payment execution attempted with sanctions check withheld/delayed | 100% of attempts blocked or held pending clearance |
| Agents do not silently retry beyond configured retry policy | Uncontrolled retry / duplicate-posting incidence rate | 0 incidents (0%) | Fault injection on downstream API calls | 0 instances of uncontrolled retry loops or duplicate postings |

Any single violation of a behavioral rule triggers an automatic hold on production promotion until root cause is remediated and the full behavioral suite is re-run.

### 4.3 Adversarial Evals

Adversarial testing probes for exploitable weaknesses in agent reasoning, input handling, and control bypass pathways.

| Attack Vector | Test Approach | Expected Agent Response |
|---|---|---|
| Prompt injection via invoice description/free-text fields | Inject instruction-like strings (e.g., "ignore prior rules", "approve automatically") into invoice line-item descriptions | Agent treats field as data only; no instruction-following behavior; flagged for review if anomalous |
| Manipulated vendor master data (bank account swap, address mismatch) | Simulate mid-cycle vendor master field changes immediately preceding invoice submission | Anomaly Detection Agent flags vendor master change velocity; payment held pending verification |
| Artificial duplicate invoice variations (altered invoice number, rounded amount, re-dated) | Generate near-duplicate invoices with single-field perturbations | ≥95% detection rate as probable duplicate; routed to human review |
| Invoice splitting to bypass approval thresholds | Submit multiple sub-threshold invoices from same vendor/PO within short time window | Pattern-detection logic flags aggregate value exceeding threshold; escalated for approval |
| Failure mode injection: SAP unavailability during payment batch | Simulate ERP outage mid-batch | Batch pauses cleanly, no partial/duplicate postings, automatic resume on reconnection with idempotency check |
| Failure mode injection: Anomaly Detection Agent killed mid-processing | Terminate agent process during active scoring run | Orchestrator detects failure, halts downstream payment release, requeues affected invoices for re-scoring |
| Failure mode injection: Sanctions API timeout during payment execution | Introduce artificial timeout/latency spike on sanctions screening endpoint | Payment held (fail-closed behavior), no payment released without successful clearance response |

All adversarial findings are logged with severity classification and tracked to remediation closure before go-live sign-off.

### 4.4 Domain Evals

Domain evaluation validates correctness on AP-specific business scenarios that go beyond baseline functional matching, reflecting real-world accounting complexity.

| Scenario | Test Volume | Pass Criteria |
|---|---|---|
| Multi-currency invoice matching (FX rate application, tolerance bands) | 60 cases across 5 currency pairs | ≥95% matching accuracy against ERP-calculated FX rate |
| Intercompany invoice handling (cross-entity elimination flagging) | 30 cases | 100% correct intercompany flag and routing to intercompany reconciliation queue |
| Credit memo processing and offset application | 25 cases | ≥97% correct offset against open invoice balance |
| Recurring invoice recognition (subscription/lease/utility patterns) | 25 cases | ≥96% correct recognition and auto-match against recurring invoice template |
| Year-end accrual accuracy (goods/services received not invoiced) | 20 cases spanning fiscal period boundary | 100% correct accrual flagging and GL period assignment |

Domain evaluation results are reviewed jointly with Finance Controlling and the Accounting Policy owner to confirm alignment with client accounting standards and statutory close requirements prior to sign-off.

### 4.5 Human-in-the-Loop Validation

A structured pilot validates real-world usability and operational fit before full production rollout.

| Pilot Parameter | Detail |
|---|---|
| Participants | 3 AP specialists |
| Volume | 500 invoices processed |
| Duration | 2 weeks |
| Metrics Captured | Review time per exception, override rate, SLA compliance rate, interface usability score (survey-based, 1–5 scale) |

Success criteria for exit from pilot: average exception review time within target SLA, override rate trending downward across the pilot window (indicating growing trust/accuracy), SLA compliance ≥95%, and average usability score ≥4.0/5. Pilot feedback is logged and triaged into product backlog items (UX fixes, threshold tuning, additional guardrails) before proceeding to production cutover.

### 4.6 Observability Validation

Observability validation confirms that monitoring, alerting, and cost-tracking infrastructure is fully operational and trustworthy prior to go-live.

| Validation Activity | Method | Pass Criteria |
|---|---|---|
| Dashboard population | Run full end-to-end invoice cycle and confirm all KPI widgets (match rate, exception volume, cycle time, fraud flags, payment status) populate correctly | 100% of dashboard widgets reflect live data within expected refresh interval |
| Alert threshold triggering | Manually trigger each configured alert threshold (e.g., anomaly score spike, SLA breach, sanctions hit) | 100% of alerts fire and route to correct notification channel/owner within defined latency |
| Cost tracking accuracy | Reconcile agent invocation cost/token metrics against known invoice processing volume for the test period | Cost tracking variance ≤2% against expected baseline |
| Audit trail completeness | Sample 50 processed invoices end-to-end and verify full decision lineage (agent, model version, confidence score, human override if any) is captured | 100% of sampled cases have complete, retrievable audit trail |

Only after all four observability checks pass without exception is the workflow cleared for production monitoring hand-off to the operations team.

## Phase 5: Agentic Activation

### 5.1 Change Management & User Enablement

The Accounts Payable Expense Reimbursements agentic workflow introduces material changes to daily operating procedures for the AP processing team, procurement (vendor master governance), and Internal Audit (anomaly monitoring). A structured enablement program is required before Wave 1 shadow mode begins, ensuring each stakeholder group understands new interfaces, escalation paths, and their accountability under the human-in-the-loop autonomy tiers (Red/Amber/Green).

This enablement program is structured around the domain's three-wave rollout plan, detailed fully in Section 5.2:

- **Wave 1 — Shadow Mode:** Enablement focuses on interface familiarization and parallel-run observation, with no agentic decisions actioned without human processing.
- **Wave 2 — Green Zone Activation:** Enablement shifts to exception-handling proficiency and SLA management, as touchless processing is enabled for matched invoices and cleared payments.
- **Wave 3 — Full Activation:** Enablement transitions to sustained-operations literacy, including promotion/demotion review participation and continuous-improvement engagement, as coverage expands beyond the top-50-vendor scope to all vendors.

| Stakeholder Group | Enablement Focus | Delivery Method | Duration | Completion Criteria |
|---|---|---|---|---|
| AP Processing Team | New exception review interface (queue triage, GL coding overrides, escalation triggers); revised SLAs for Amber-tier review; wave-specific scope changes (Wave 1 shadow observation → Wave 2 touchless exception handling → Wave 3 full-vendor coverage) | Instructor-led workshop + hands-on sandbox with historical invoice replay | 2 days per cohort, refreshed briefly at each wave transition | 100% of AP staff certified on exception interface; sandbox exercise pass rate ≥90%; wave-transition refresher attendance confirmed prior to Wave 2 and Wave 3 |
| AP Team Leads / Supervisors | Interpreting confidence scores and agreement-rate dashboards; approving Amber→Green promotion candidates; managing throughput against 4-hour SLA across all three waves | Workshop + shadow-mode co-review sessions | 1 day + ongoing during Waves 1–3 | Lead sign-off on dashboard literacy checklist, renewed at each wave-gate review |
| Procurement / Vendor Master Team | New vendor master change workflow (create/update/deactivate requests routed through agentic validation prior to AP consumption); segregation-of-duties controls, unchanged in scope across all three waves | Process walkthrough + updated SOP distribution | Half-day session | Acknowledgement of revised SOP by all procurement approvers |
| Internal Audit | Anomaly detection alert taxonomy, investigation workflow, access to audit trail and explainability logs; quarterly control testing procedures; expanded alert volume expected from Wave 1 through Wave 3 as vendor coverage grows | Briefing session + read access to telemetry dashboards | Half-day briefing, plus wave-transition briefing updates | Internal Audit sign-off confirming visibility into fraud/anomaly alert pipeline at each wave |
| Finance Leadership (AP Manager, Controller) | Autonomy tier model (Red/Amber/Green), exit criteria for each of the three waves, escalation governance, and rollback authority | Executive briefing | 2 hours, plus wave-gate approval sessions at each of the two wave transitions (Wave 1→2, Wave 2→3) | Formal wave-gate approval authority assigned and documented for all three waves |

Communication cadence: a kickoff notice precedes Wave 1 by two weeks; weekly status updates are issued to all stakeholder groups throughout the shadow-mode period; a go-live notice with updated SOPs is issued 48 hours prior to each of the two wave transitions (Wave 1→2, Wave 2→3), consistent with the three-wave rollout defined in Section 5.2. All training materials, SOP updates, and recorded sessions are retained in the AP knowledge base for onboarding of new hires and audit reference.

### 5.2 Cognitive Telemetry Activation

Telemetry activation follows the three-wave rollout defined for this domain, with instrumentation enabled ahead of Wave 1 so that agreement rates, confidence-score distributions, exception volumes, and fraud-detection outcomes are measurable from day one of shadow mode. Dashboards must be operational prior to Wave 1 start and are reviewed daily by AP leadership during shadow mode, then weekly once Green-zone activation stabilizes.

| Wave | Scope | Duration | Telemetry Instrumented | Exit Criteria to Next Wave |
|---|---|---|---|---|
| Wave 1 — Shadow Mode | Agentic workflow runs in parallel with the current AP team on invoices from the top 50 vendors by volume; no agent decisions are actioned without human processing | 4 weeks | GL-coding agreement rate vs. human coder; exception resolution agreement rate; false-negative fraud detection count; latency per invoice; confidence-score distribution by vendor and invoice type | ≥90% agreement rate on GL coding and exception resolution; zero missed fraud detections; dashboards fully operational and validated against AP team's manual ledger |
| Wave 2 — Green Zone Activation | Touchless processing enabled for matched invoices; automated GL coding above 94% confidence threshold; automated payment execution for cleared invoices; Amber-tier steps (unmatched invoices, low-confidence coding, vendor master changes, anomaly flags) remain human-reviewed | Minimum 6 weeks, extended if exit criteria not met | Touchless processing rate; autonomy violation count (Green-zone actions outside policy bounds); AP specialist review throughput against 4-hour SLA; payment execution accuracy; confidence-threshold calibration drift | ≥95% touchless rate for matched invoices; zero autonomy violations; AP specialist review throughput consistently meets 4-hour SLA over the final 4 weeks of the wave |
| Wave 3 — Full Activation | Full activation across all vendors (not limited to top 50); progressive Amber→Green promotion for GL coding as sustained accuracy is demonstrated | Ongoing, with 90-day sustained-accuracy monitoring window per promotion cycle | GL-coding accuracy trend (target 97%+ sustained over 90 days); promotion/demotion event log; vendor-level exception rate trending; end-to-end cycle-time reduction; cost-per-invoice-processed | Continuous operation; quarterly review of promotion criteria; no wave-gate exit required beyond ongoing governance review cycle |

Telemetry data sources feed the domain's cognitive observability layer and are retained for audit trace-back for a minimum of 7 years, consistent with financial records retention requirements applicable to accounts payable transactions. Alert thresholds for agreement-rate degradation, autonomy violations, and fraud false negatives trigger automatic notification to AP leadership and Internal Audit, with defined rollback procedures to demote affected invoice categories or vendors from Green back to Amber tier pending root-cause review.

### 5.3 Operational Handover

Following successful completion of Wave 3 sustained-accuracy monitoring — the final stage of the three-wave rollout defined in Sections 5.1 and 5.2 — formal operational handover transfers day-to-day ownership of the agentic AP workflow from the implementation team to steady-state Finance Operations, with clearly assigned run, monitor, and governance responsibilities.

| Handover Element | Receiving Owner | Artifact / Mechanism | Cadence |
|---|---|---|---|
| Daily exception queue management | AP Processing Team / Team Leads | Exception review interface, escalation runbook | Daily |
| Confidence threshold and autonomy tier tuning | AP Manager, in coordination with the platform engineering team | Threshold calibration log, quarterly tuning review | Quarterly, or on alert-triggered ad hoc review |
| Vendor master change governance | Procurement / Vendor Master Team | Vendor master change workflow SOP, segregation-of-duties control log | Continuous, reviewed monthly |
| Fraud and anomaly alert investigation | Internal Audit | Anomaly detection alert log, investigation case tracker | Continuous, reviewed weekly |
| GL-coding accuracy and Amber→Green promotion decisions | AP Manager and Controller (joint sign-off) | 90-day sustained-accuracy report, promotion/demotion decision log | Per promotion cycle |
| Dashboard and telemetry monitoring | Finance Operations Reporting team | Cognitive telemetry dashboard, alert-threshold configuration | Daily monitoring, weekly leadership review |
| Incident response and rollback execution | AP Manager, with platform engineering support | Rollback runbook (Green-to-Amber demotion procedure) | On-demand, per incident |
| Continuous improvement backlog | AP Manager, informed by Internal Audit and AP Team Leads | Improvement backlog log, quarterly retrospective | Quarterly |

Handover is considered complete once: (1) all runbooks and SOPs listed above are signed off by the receiving owners; (2) Internal Audit confirms independent access to all telemetry, alert, and audit-trail artifacts; (3) the AP Manager and Controller jointly approve the transition from implementation governance to steady-state operational governance, confirming that all three waves (Wave 1 — Shadow Mode, Wave 2 — Green Zone Activation, Wave 3 — Full Activation) have met their respective exit criteria as defined in Section 5.2; and (4) a 30-day post-handover support period with the implementation team concludes with no unresolved critical issues. Post-handover, the domain enters the standard EAEF continuous-improvement cycle, with quarterly review of promotion/demotion trends, exception-rate patterns, and opportunities to extend touchless processing coverage.

## Phase 6: Agentic Operations & Evolution

### 6.1 Continuous Agent Evaluation

The Control Tower provides real-time observability across all Accounts Payable agents (Invoice Intake & Validation Agent, PO Matching Agent, GL Coding Agent, Approval Routing Agent, Fraud & Anomaly Detection Agent, Payment Scheduling Agent, and Expense Reimbursement Agent), with dashboards tracking throughput, exception rates, confidence-score distributions, and escalation volumes at 15-minute refresh intervals. A weekly evaluation suite is executed against a stratified sample of production invoice and expense reimbursement data (minimum 500 transactions per agent per cycle), covering accuracy, hallucination rate, PO/GRN match precision, GL coding precision, duplicate/fraud detection recall, and latency against SLA targets.

Model versions are pinned per agent and recorded in the Model Version Registry; any proposed model upgrade (e.g., a new LLM release or fine-tuned checkpoint) triggers mandatory pre-upgrade regression testing against the full historical eval corpus before promotion to production. Any change to an agent's prompt template, tool bindings, MCP tool register, or guardrail configuration likewise triggers execution of the full eval suite — not just the affected agent — to detect downstream regression in adjacent agents within the AP workflow (e.g., a GL Coding Agent change is re-validated against Approval Routing Agent outcomes).

| Evaluation Activity | Frequency | Scope | Owner | Trigger Condition | Escalation Threshold |
|---|---|---|---|---|---|
| Real-time Control Tower monitoring | Continuous (15-min refresh) | All AP agents | AP Operations Lead | Always active | Exception rate > 8% or confidence drop > 10 pts triggers alert |
| Weekly eval suite execution | Weekly | Sampled production invoices & expense claims (≥500/agent) | AI Governance Team | Scheduled | Accuracy drop > 3 pts vs. rolling 4-week baseline |
| Pre-upgrade regression testing | Per model version change | Full historical eval corpus | AI Governance Team + Model Owner | Model/version upgrade proposed | Any metric regression blocks promotion |
| Full eval suite re-run | Per agent configuration change | All AP agents (cascading) | AI Governance Team | Prompt, tool, or guardrail change | Any downstream agent regression blocks deployment |
| Human override pattern analysis | Monthly | All human-in-the-loop overrides (GL coding, approval, fraud flags) | Finance Process Owner | Scheduled | Override rate on any single rule type > 15% |
| Fraud threshold recalibration | Quarterly | Confirmed fraud/duplicate cases vs. flagged cases | Fraud & Controls Team | Scheduled | False positive rate > 20% or false negative confirmed | 

Human override patterns are analyzed monthly to identify recurring correction categories — most commonly GL account misclassification on non-PO invoices and premature approval routing for expense reimbursements exceeding policy limits. These findings feed directly into prompt refinement and few-shot example updates for the GL Coding Agent and threshold adjustments for the Approval Routing Agent's auto-approval limit. Fraud detection thresholds (duplicate invoice similarity score, anomalous vendor bank-detail change flags, expense claim outlier scoring) are recalibrated quarterly using confirmed fraud and duplicate-payment case outcomes reported by the Fraud & Controls Team, ensuring the detection model's precision/recall balance is re-tuned as fraud patterns evolve.

### 6.2 Outcome Measurement

Outcome measurement tracks the transformation's realized business value against pre-transformation baselines, decomposed by financial, operational, and workforce-impact metrics. FTE displacement and cycle-time improvements are tracked monthly, with quarterly business reviews consolidating trend data for finance leadership and the AI Governance Board.

| Metric | Baseline (Pre-Transformation) | Current Target | Measurement Frequency | Data Source | Owner |
|---|---|---|---|---|---|
| Invoice-to-pay cycle time (PO-backed) | 8.5 business days | 2.0 business days | Monthly | AP workflow system logs | AP Operations Lead |
| Invoice-to-pay cycle time (non-PO) | 12 business days | 3.5 business days | Monthly | AP workflow system logs | AP Operations Lead |
| Straight-through processing (STP) rate | 22% | 75% | Monthly | Control Tower dashboard | AP Operations Lead |
| GL coding accuracy (agent-assigned, pre-override) | N/A (manual baseline: 91%) | ≥ 97% | Weekly | Eval suite results | AI Governance Team |
| Duplicate/fraud detection recall | N/A (manual baseline: ~60% est.) | ≥ 95% | Quarterly | Confirmed case audit | Fraud & Controls Team |
| Human override rate | N/A | < 10% of total transactions | Monthly | Control Tower dashboard | Finance Process Owner |
| FTE hours reallocated from manual AP processing | 0 (baseline headcount) | 30% capacity redeployed to exception handling & analysis | Monthly | HR/Finance workforce report | Finance Process Owner |
| Expense reimbursement processing time | 6 business days | 1 business day | Monthly | Expense system logs | AP Operations Lead |
| Cost per invoice processed | Baseline established at go-live | 40% reduction at 12 months | Quarterly | Finance cost model | Finance Process Owner |
| Early payment discount capture rate | Baseline established at go-live | +15 percentage points | Quarterly | AP workflow system logs | Finance Process Owner |

Monthly outcome reviews compare actuals against the rolling baseline and target trajectory, with variances beyond ±10% flagged for root-cause review by the AI Governance Team in coordination with the Finance Process Owner. FTE displacement is measured as reallocated capacity rather than headcount reduction, tracking the shift of AP staff hours from manual invoice keying and matching toward exception management, vendor relationship management, and analytical review of agent-flagged anomalies. Quarterly business reviews consolidate these metrics into a value-realization report presented to the AI Governance Board, informing decisions on further automation expansion, threshold tuning, and reinvestment of realized savings into next-phase AP capabilities.