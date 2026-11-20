# Reusable assets for OpenAI Agents SDK developers

A catalog of what an OpenAI Agents SDK developer can take from K9-AIF and the K9X apps and reuse in their own
applications. Each asset says what the developer gets, how they use it, what it is built from, and what they
supply. The live demos are at [openai.k9x.ai](https://openai.k9x.ai).

K9-AIF is open source (Apache-2.0) and installed from PyPI. An application **uses** these assets; it does not
copy or rebuild them:

```bash
pip install "k9-aif[openai-agents,server,kafka,postgres]>=1.32.0"
```

Versions checked against the framework source on 2026-11-20: k9-aif 1.32.0, openai-agents 0.24.x.

## The catalog at a glance

| # | Asset | Kind | An OpenAI developer uses it to |
|---|---|---|---|
| 1 | Governed OpenAI agent | Library class + YAML template | Run an SDK agent with checks on every tool call, tool result and reply |
| 2 | Squad of OpenAI agents | YAML template | Run several SDK agents in a fixed, reviewable order |
| 3 | Approval with same-run resume | Library + configuration | Pause a risky tool call for a person and continue the same run after the decision |
| 4 | Rules step | Library + decision-table template | Take approve/reject/needs-approval decisions out of the prompt |
| 5 | Tool and tool-result screening | Library (built into 1 and 7) | Block bad tool arguments and poisoned tool results before the model reads them |
| 6 | K9 Model Router as the SDK's model provider | Library + model catalog template | Choose the model per call by capability, sensitivity, cost and latency, failing closed |
| 7 | Handoff group, governed | Library + YAML | Let the model delegate among two or three specialists, with every agent governed |
| 8 | Caller identity and Zero Trust | Library + policy template | Refuse a caller before any agent or model runs |
| 9 | Input filters | Library + configuration | Strip hidden Unicode and quarantine untrusted text before the agent reads it |
| 10 | Local trace and monitoring | Library + configuration | Keep SDK traces in house and send governance events to your monitoring |
| 11 | Shared services: K9X HIL and K9X Rules Engine | Deployable services | Give every team one approval inbox and one rules service |
| 12 | Reference application: accounts payable approval | Runnable example | Start a new approval-gated application from a working one |

Assets 1 to 10 are in the `k9-aif` package. Asset 11 is two services a platform team deploys once. Asset 12 is
source code in this repository.

---

## 1. Governed OpenAI agent

**What the developer gets.** An OpenAI Agents SDK agent defined in YAML, with no Python agent class to write.
Every turn is checked: k9x Shield on the step's input and output, on each tool call and on each tool result, and
the K9 Model Router on every model call.

**How they use it.**

```python
# my_app/agents/weather_agent.py
from k9_aif_abb.k9_adapters.openai_agents import K9OpenAIAgent

class WeatherAgent(K9OpenAIAgent):
    pass
```

```yaml
# agents/yaml/weather_agent.yaml
class: WeatherAgent
module: my_app.agents.weather_agent
name: WeatherAgent
model: tools                    # a K9 model catalog task; the router picks the model
role: You report the current weather.
instructions: [Use the tools; never guess a temperature]
tools: [current_weather]        # registered ToolCapability names
structured_output:              # optional: a typed result (string, number, integer, boolean)
  place: string
  temperature_f: number
```

**Built from.** `K9OpenAIAgent` (k9-aif 1.29.0 on PyPI), `BaseAgent` (governance by construction),
`ToolCapability`.

**The developer supplies.** The agent YAML and the tool functions.

**Limits.** Hosted OpenAI tools (web search, file search, code interpreter, hosted MCP) run on OpenAI's servers
outside any tool check, so the adapter does not accept them. `Runner.run_streamed` is not wrapped yet.

## 2. Squad of OpenAI agents

**What the developer gets.** Several OpenAI agents run as named steps in an order the YAML sets. The squad
chooses the next agent, never the model. A step can be skipped on a condition, and a failure stops at a named
step. The SDK's own guide calls this "orchestrating via code".

**How they use it.**

```yaml
# squads.yaml
squads:
  ap_invoice:
    agents: [InvoiceAgent, APRulesAgent, PaymentAgent]
    flow:
      - {agent: InvoiceAgent, result_key: invoice_agent}
      - {agent: APRulesAgent, result_key: rules_check}
      - agent: PaymentAgent
        result_key: payment
        when: {key: rules_check.output.decision, ne: reject}   # a rejected invoice is never paid
```

**Built from.** `BaseSquad`, `SquadLoader.from_agents()`, `K9OpenAIAgent`. A squad can mix OpenAI agents with
any other K9-AIF agent (the rules step in asset 4 is one).

**The developer supplies.** The squad YAML: the process steps and their conditions.

## 3. Approval with same-run resume

**What the developer gets.** The SDK's own `needs_approval`, connected to an enterprise approval inbox. When a
tool needs a person, the run pauses and its state is saved. A review task goes to K9X HIL. When the person
decides, the saved run is restored, the decision is recorded with `approve()` or `reject()`, and `Runner.run`
continues the same OpenAI run where it stopped.

**How they use it.** In the agent YAML of the step that acts:

```yaml
tools: [pay_invoice]
needs_approval_when:            # pause only when an earlier step said so
  pay_invoice: {key: rules_check.output.decision, eq: needs_approval}
hil_queue: openai-ap-payments   # review tasks go to hil.requests.openai-ap-payments
hil_priority: high
```

**Built from.** `OpenAIHILAdapter` (`BaseHILAdapter`), `PausedRunStore` (table `k9_paused_runs`, PostgreSQL in
production, SQLite otherwise), `RequiresHIL`, the orchestrator's HIL publishing, and `K9EventRouter`, which
listens on `hil.replies.*` and resumes the flow. Review requests follow K9X HIL's task contract
(`k9x.hil.task/v1`).

**How it flows.** Only a key to the saved state travels with the review, never the state itself: through
Kafka, K9X HIL and back. Steps already done are not run again.

**The developer supplies.** Which tools need approval and when, the queue name, and the task's deadline and
approver role. A platform team supplies Kafka, PostgreSQL and K9X HIL (asset 11).

## 4. Rules step

**What the developer gets.** Business decisions made by a rules engine, not by the model. The rules step reads
facts from the system of record, never from the model, and returns `decision`, `approver_role`, `rule` and
`reason`. Later steps branch on the decision.

**How they use it.**

```yaml
# config.yaml
rules_agent:
  adapter: gorules              # or rest_rules (ODM, Drools, any decision service) or k9_rules (YAML)
  engine_url: "${K9X_RULES_ENGINE_URL}"
  project: accounts-payable
  ruleset: invoice-approval.json
  facts: invoice_agent.output
```

**Decision-table template.** The accounts payable table, first match wins:

| Rule | When | Decision | Approver |
|---|---|---|---|
| AP-01 | Vendor is blocked | reject | |
| AP-02 | Duplicate invoice | reject | |
| AP-03 | Amount over $100,000 | needs_approval | manager |
| AP-04 | Vendor's bank account changed recently | needs_approval | manager |
| AP-05 | First invoice from a new vendor | needs_approval | worker |
| AP-06 | No matching purchase order | needs_approval | worker |
| AP-07 | Amount over $15,000 | needs_approval | worker |
| AP-08 | Otherwise | auto_pay | |

**Built from.** `K9RulesAgent`, `BaseRulesAdapter` with `GoRulesAdapter`, `RestRulesAdapter` and
`K9RulesAdapter`.

**The developer supplies.** The decision table (owned by the business, versioned and tested) and the function
that looks up facts from the system of record.

## 5. Tool and tool-result screening

**What the developer gets.** Every tool is a registered `ToolCapability`. The adapter builds the SDK's
`FunctionTool` from it, so no tool can be added around the checks. Shield checks a tool's arguments before it
runs and its result before the model reads it. A poisoned result is withheld, and the agent is told it was
withheld.

**Built from.** `ToolCapability`, `build_function_tool`, Shield's `ToolArgumentCheck`, `ExecutionGuardCheck`
and `PromptInjectionCheck`, `@govern_tool_call` and `@govern_tool_result`.

**Optional: the tool gate** (`security.tool_gate.enabled`, k9-aif 1.25.0). It adds per-tool policy (for example
`irreversible: true`), facts verified against the record before the call, a review for held calls, and an audit
log of every call (`SQLiteToolCallAuditLog`).

**The developer supplies.** The tool functions. A bad input is returned as an ordinary answer the model can
report; a failure raises and stops the run.

## 6. K9 Model Router as the SDK's model provider

**What the developer gets.** The router is the SDK's `ModelProvider`, so every model call in every agent goes
through it. It first keeps only the models that qualify: tool calling when the agent has tools, and
confidential-capable models for a confidential request. Then it scores them on latency and cost tiers and on
learned outcomes. When no model qualifies, the call fails closed (`NoEligibleModelError`) and no other model is
tried.

**How they use it.** A model catalog in `config.yaml`, with capabilities such as `tool_calling` and
`confidential` and the `latency_tier` and `cost_tier` of each model. The agent YAML names a task (`model:
tools`), not a model.

**Built from.** `K9ModelProvider`, `K9GovernedModel`, `K9ModelRouter`. The SDK can call `openai` and `ollama`
backends. An `openai` backend needs `OPENAI_API_KEY`.

**The developer supplies.** The approved model catalog.

## 7. Handoff group, governed

**What the developer gets.** The SDK's handoffs, where the model picks the next agent, with every agent in the
group governed. The SDK's own input and output guardrails run only on the first and last agent in a chain.
Handoffs are capped by `max_handoffs` (default 3). An unknown tool or handoff name fails at start-up.

**When to use it.** A small delegation inside one step, such as triage among two or three specialists. A known
business process belongs in a squad (asset 2).

**Built from.** `OpenAIAgentsOrchestratorAdapter` and `K9OpenAIAgentsAdapter`, which extend `BaseOrchestrator`
and `BaseAdapter`, so the Router sends an `event_type` to it like any orchestrator.

**Limit.** On this path, a call held by the tool gate is resumed by running the stored call; the agent loop
does not continue. Same-run resume (asset 3) is the squad path.

## 8. Caller identity and Zero Trust

**What the developer gets.** The caller is authenticated and checked against a role policy before any agent
runs. A refused caller costs no model call. In a squad (asset 2) the check is on the orchestrator that runs
the squad; in a handoff group (asset 7) each agent turn is checked as well.

**How they use it.**

```python
ROLE_POLICY = {
    "weather.lookup": ["customer", "staff"],              # the run
    "openai_agent:WeatherAgent": ["customer", "staff"],   # each agent turn (handoff group)
}
guard = DefaultZeroTrustGuard(authorization_guard=RoleBasedAuthorizationGuard(ROLE_POLICY))
```

**Built from.** `DefaultZeroTrustGuard`, `RoleBasedAuthorizationGuard`, `BaseRouter.admit()`, and
authenticators: `ApiKeyAuthenticator` and OIDC (`KeycloakAuthenticator`, `EntraIDAuthenticator`,
`OktaAuthenticator`). `security.identity.mode` selects `PayloadIdentityResolver` (the 1.x default: roles in
the request, as in the demos) or `SignedIdentityResolver` (production: signed identity).

**The developer supplies.** The role policy and the identity provider settings.

## 9. Input filters

**What the developer gets.** Text is cleaned before Shield and the agent see it. `K9TextNormalizeFilter`
removes invisible and Unicode tag characters (hidden instructions). `K9AttentionFilter` quarantines untrusted
text, de-duplicates it and trims it to a budget. `K9JsonOutputFilter` turns a reply into validated JSON or a
clear failure. `K9ProvenanceFilter` attaches the sources of facts.

**How they use it.**

```yaml
filters:
  enabled: true
  chain: [text_normalize, attention, json_output, provenance]
```

Per-agent settings go under `agent_filters` in the agent YAML.

**Built from.** `BaseFilter`, `FilterFactory` (k9-aif 1.32.0). Every agent gets them by construction.

## 10. Local trace and monitoring

**What the developer gets.** SDK trace export to OpenAI is off unless `openai_agents.export_traces: true`.
Agent turns, handoffs, model routes and calls, tool calls and results, and every check are emitted as K9-AIF
trace events, the same events as every other K9-AIF component.

**Built from.** `BaseMonitor` with `OTelMonitor`, `PrometheusMonitor`, `CloudWatchMonitor` and
`ConsoleMonitor`.

**The developer supplies.** Which monitor to use and where it sends events.

## 11. Shared services: K9X HIL and K9X Rules Engine

Deployed once by a platform team and used by every application.

| Service | What it does | Applications reach it through |
|---|---|---|
| K9X HIL | Review inbox: queues, approver roles, deadlines, the artifact (for example the invoice PDF from object storage) shown to the reviewer | Kafka `hil.requests.<queue>` and `hil.replies.<queue>`; REST API with an API key |
| K9X Rules Engine | Decision tables per project, run by GoRules | `GoRulesAdapter` (`engine_url`) |

Also needed: Kafka (or Redpanda), PostgreSQL for `PausedRunStore`, and S3-compatible object storage for
artifacts (`S3ObjectStorageAdapter` or `LocalObjectStorageAdapter`).

## 12. Reference application: accounts payable approval

A working application that combines assets 1 to 6, 8, 10 and 11. It is the starting point for any
approval-gated flow: refunds, claims exceptions, access requests, contract approvals.

```
K9EventRouter -> Kafka openai.ap.in -> APOrchestrator -> squad ap_invoice
  InvoiceAgent  (K9OpenAIAgent)  reads vendor, invoice number and amount (structured output)
  APRulesAgent  (K9RulesAgent)   facts from the records -> K9X Rules Engine: AP-01..AP-08
  PaymentAgent  (K9OpenAIAgent)  pay_invoice; pauses for K9X HIL when the rules said needs_approval
```

On a pause, the task goes to K9X HIL with the invoice PDF as its artifact. A manager approves AP-03 and AP-04
with a written justification; anyone in the queue approves the rest. The task expires after 24 hours and the
payment is rejected. After the decision, the Router resumes the squad and PaymentAgent continues the same
OpenAI run.

**Where it is.** `k9x_openai_bedrock/openai/accounts_payable/` in
[k9aif/examples](https://github.com/k9aif/examples). Live at [openai.k9x.ai/ap](https://openai.k9x.ai) (demo
login on the page).

**To adapt it.** Replace the three agent YAML files, the decision table, `record_facts()` (the system-of-record
lookup) and the action tool. The squad, the pause and resume, and the HIL wiring stay as they are.

---

## What ships, and what each adopter supplies

| Ships in k9-aif or K9X | Each adopter supplies |
|---|---|
| The OpenAI adapters, squad runner, HIL bridge, paused-run store | Agent and squad YAML for their process |
| Shield checks, Zero Trust, authenticators, filters | Role policy and identity provider settings |
| Rules adapters (GoRules, REST, YAML) | The decision tables, owned by the business |
| Model Router and provider | The approved model catalog |
| Monitors, trace events | Where events go |
| K9X HIL and K9X Rules Engine (deployable) | Hosting, queues, reviewer roles |
| The accounts payable reference application | Tool functions for their systems of record |

## Read more

- [integration-design.md](integration-design.md): what the SDK provides, what K9-AIF adds, every check
- [example-implementation.md](example-implementation.md): the weather application file by file, with a recorded run
- [README.md](README.md): the three use cases and how to run them
- Framework: [github.com/k9aif/k9-aif-framework](https://github.com/k9aif/k9-aif-framework), PyPI
  [k9-aif](https://pypi.org/project/k9-aif/)
