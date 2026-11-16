# K9-AIF with the OpenAI Agents SDK and AWS Bedrock AgentCore — Project Plan

Status: draft for review, 2026-11-15. Nothing is built yet; this plan says what
to build, where, and in what order.

## 1. Goal

Show, with working code, how K9-AIF complements the OpenAI Agents SDK and AWS
Bedrock AgentCore: what each platform already does well, what K9-AIF adds on
top, and why one governance configuration across every agent runtime matters
to an enterprise.

Outputs, in order:

1. Two OOB adapter packages in the framework, same shape as the Claude Agent
   SDK and LangGraph adapters.
2. Working examples in this folder (`openai/`, `bedrock/`), one shared scenario.
3. Diagrams: a block diagram above a class diagram, per platform.
4. A blog post and a LinkedIn draft (Ravi posts it; Claude drafts only).
5. Evidence to turn the paper's Table 5 "D" (documented) entries for these two
   platforms into "E" (executed), after live runs only.

## 2. What was verified, and how

Read from the installed packages on 2026-11-15, not from memory or docs:
`openai-agents 0.24.0`, `bedrock-agentcore 1.26.0`, `boto3 1.44.3` service
models, and `k9-aif 1.26.1` source. Re-verify after any version bump. Items
marked **unverified** need a live run before anything public relies on them.

### 2.1 OpenAI Agents SDK 0.24.0

| Fact | Where |
|---|---|
| `Agent.model` accepts a `Model` instance; `RunConfig.model_provider` accepts any `ModelProvider`. `Model` has two abstract methods, `get_response()` and `stream_response()`. | `agents/agent.py`, `agents/run_config.py`, `agents/models/interface.py` |
| `OpenAIChatCompletionsModel(model, openai_client=AsyncOpenAI(...))` works with any OpenAI-compatible endpoint (OpenAI, Azure OpenAI, Ollama, vLLM). | `agents/models/openai_chatcompletions.py` |
| `FunctionTool` carries `tool_input_guardrails`, `tool_output_guardrails` and `needs_approval`. A tool guardrail returns `allow`, `reject_content` (the model sees a message, the run continues) or `raise_exception` (the run halts). | `agents/tool.py`, `agents/tool_guardrails.py` |
| Tool guardrails run only for function tools (`_execute_tool_input_guardrails(func_tool, ...)`). Hosted tools (`WebSearchTool`, `FileSearchTool`, `CodeInterpreterTool`, `HostedMCPTool`, `ImageGenerationTool`) run on OpenAI's servers and never pass a local check. | `agents/run_internal/tool_execution.py` |
| MCP servers can carry tool guardrails that are copied onto each MCP tool. | `agents/mcp/util.py` |
| Approval pauses a run: `RunResult.interruptions`, `RunState.approve()` / `reject()`, and `RunState.to_json()` / `from_json()` to persist and resume. | `agents/run_state.py`, `agents/result.py` |
| Tracing is pluggable: `add_trace_processor()`, `set_trace_processors()`; a `TracingProcessor` sees every trace and span start and end. | `agents/tracing/__init__.py` |
| Agent-level `input_guardrails` default to `run_in_parallel=True`, so the model may start before the check finishes. | `agents/guardrail.py` |

### 2.2 AWS Bedrock AgentCore (SDK 1.26.0, boto3 1.44.3)

AgentCore is a hosting and services platform, not an agent loop. The agent
inside it is written in any framework.

| Fact | Where |
|---|---|
| `BedrockAgentCoreApp` is a Starlette app with `POST /invocations` and `GET /ping` on port 8080; `@app.entrypoint` marks the handler. | `bedrock_agentcore/runtime/app.py` |
| A deployed agent is called with `bedrock-agentcore:InvokeAgentRuntime(agentRuntimeArn, payload, runtimeSessionId, runtimeUserId, ...)`. | boto3 service model |
| `InvokeHarness` is a managed agent loop: `messages`, `model` (Bedrock, OpenAI, Gemini or LiteLLM config), `tools`, `allowedTools`, `maxIterations`. Tool types: `remote_mcp`, `agentcore_gateway`, `inline_function`, `agentcore_browser`, `agentcore_code_interpreter`. The stream's `stopReason` includes `tool_use`. | boto3 service model |
| **Unverified:** an `inline_function` tool is executed by the caller, which sends the result back in the next `InvokeHarness` call. The `tool_use` stop reason suggests this; the API documentation does not say it. | needs a live run |
| Gateway targets: MCP (`mcpServer`, `lambda`, `openApiSchema`, `smithyModel`, `apiGateway`, `connector`), HTTP (`agentcoreRuntime`, `passthrough`), and `inference`. | `CreateGatewayTarget` |
| A Gateway takes `interceptorConfigurations`: a Lambda called at `REQUEST` and/or `RESPONSE`. | `CreateGateway` |
| A Gateway takes a `policyEngineConfiguration`: Cedar policies, mode `LOG_ONLY` or `ENFORCE`. The SDK's `PolicyEngineClient` only creates and edits policies; enforcement is server-side, in the Gateway. | `CreateGateway`, `bedrock_agentcore/policy/client.py` |
| Identity: `@requires_access_token`, `@requires_iam_access_token`, `@requires_api_key` fetch outbound credentials for the agent. | `bedrock_agentcore/identity/auth.py` |
| Memory: `MemoryClient` / `MemorySession` (`create_event`, `get_last_k_turns`, `retrieve_memories`, long-term strategies). | `bedrock_agentcore/memory/` |
| Bedrock models: `bedrock-runtime:Converse` / `ConverseStream`, with tool use. | boto3 service model |

### 2.3 K9-AIF 1.26.1: what the adapters build on

| Fact | Where |
|---|---|
| Adapter shape: `<X>OrchestratorAdapter(BaseOrchestrator, BaseAdapter)` + `<X>PayloadMapper` + `K9<X>Adapter` facade. | `k9_adapters/claude_agent_sdk/`, `k9_adapters/langgraph/` |
| The Claude adapter is the sole broker of tools: it never accepts a pre-built options object; every tool call goes through `apply_post_governance()`; tool results pass `screen_tool_result()`. | `claude_agent_sdk_orchestrator_adapter.py` |
| `llm_invoke()` is text in, text out. `InferenceRequest` has no `tools` field, so an agent loop that needs native tool calling cannot run through it. | `k9_utils/llm_invoke.py`, `k9_inference/models/inference_request.py` |
| `BaseModelRouter.route(request)` returns a `RouteDecision` (catalog alias, provider, rationale) without calling the model. Eligibility (`required_capabilities`, `sensitivity`) is decided before scoring. | `k9_inference/routers/` |
| No Bedrock `BaseLLM` exists. OOB providers: Ollama, OpenAI, Azure OpenAI, watsonx, Mock. | `CAPABILITIES.md` |
| Tool gate (1.25.0, opt-in): `BaseToolDispatcher.propose()` screens, checks records, applies the solution's rules, and raises `ToolCallPendingReview` for a person. The existing adapters' tool handlers have no gate session, so they are refused in production when the gate is on. Adapter gating is the planned 1.25.1 work. | `k9_core/tools/base_tool_dispatcher.py` |

## 3. Complements, not competes

The message for the blog. Each platform is strong where K9-AIF is not, and the
reverse.

| Concern | OpenAI Agents SDK | Bedrock AgentCore | What K9-AIF adds |
|---|---|---|---|
| Agent loop | Yes: Runner, handoffs, structured output | Managed harness, or any framework hosted in Runtime | Uses theirs; does not replace it |
| Hosting, scale, session isolation | No (library) | Yes: managed Runtime | Uses AgentCore's |
| Guardrails | Per agent and per tool, written by each application | Cedar policy on Gateway tool calls (who may call what) | One Shield configuration, applied by construction to every agent on every runtime: injection, PII, tool arguments, output sanitisation |
| Tool-call authority | `needs_approval` per tool | Cedar `permit`/`forbid` | Tool gate: record checks through Origin, irreversible-by-default registry, rules as SBB content, at-most-once execution, audit log |
| Human review | Approval inside one run | Not specified in cited sources | `RequiresHIL` → HIL Orchestrator → k9x HIL case management, durable across processes |
| Model choice | Any OpenAI-compatible model | Bedrock models | Learned routing with hard eligibility (for example `on_prem` for confidential data), the same catalog for every runtime |
| Tracing | Built-in, OpenAI dashboard by default | AgentCore Observability (OpenTelemetry) | One audit trail across runtimes: `publish_status`, trace events, `OTelMonitor` |
| Attack testing, static checks | No | No | SATAN attacks against Shield checks; `k9aif inspect` rules |

The point to make: an enterprise rarely runs one agent runtime. K9-AIF is the
layer that holds governance, model policy and human review constant while the
runtime underneath changes.

## 4. Design: OpenAI Agents SDK adapter

Framework package `k9_adapters/openai_agents/`, OOB. Optional dependency
`openai-agents` (extra `k9-aif[openai-agents]`).

### 4.0 Where the adapter sits

The adapter is an orchestrator: it extends `BaseOrchestrator`, and
`k9aif inspect` gives it the orchestrator role. The Router dispatches an
`event_type` to it exactly as it would to a native orchestrator:

```
Router --event_type A--> Orchestrator -> Squad -> Agents          (native)
Router --event_type B--> OpenAIAgentsOrchestratorAdapter -> Runner -> OpenAI agents
```

On the OpenAI path, the Runner and its agents take the place of Squad and
Agent. Shield, the tool gate, HIL and the Model Router are shared by both
paths and read the same configuration.

The framework's own LangGraph example puts an application orchestrator in
front of the adapter facade. That is worth doing only when that orchestrator
does real work, such as choosing between several wrapped runtimes. Otherwise
it adds a layer that does nothing. The examples here register the adapter
with the Router directly.

### 4.1 Classes

| Class | Role |
|---|---|
| `OpenAIAgentsOrchestratorAdapter(BaseOrchestrator, BaseAdapter)` | Sole broker. Builds the `Agent` (and any handoff agents) itself from `ToolCapability` definitions; never accepts a pre-built `Agent`. Runs `Runner.run()`. |
| `K9ToolGuardrail` (internal) | A `ToolInputGuardrail` calling `apply_post_governance()` and, with the gate on, `BaseToolDispatcher.propose()`; a `ToolOutputGuardrail` calling `screen_tool_result()`. A `PermissionError` becomes `reject_content`; `ToolCallPendingReview` halts the run. |
| `K9ModelProvider(ModelProvider)` | Picks the model through `BaseModelRouter.route()` (eligibility, sensitivity, learned scores), resolves the catalog entry to an OpenAI-compatible endpoint and key (`BaseSecretManager`), returns a `K9GovernedModel`. |
| `K9GovernedModel(Model)` | Wraps the SDK's own model for the chosen endpoint. Each call runs inside `governed_call()`, applies per-call governance when `governance.scope: per_call`, emits the `LLMCall` trace event, records router feedback. |
| `K9TraceProcessor(TracingProcessor)` | Forwards SDK spans to K9 trace events. SDK export to OpenAI is off unless the configuration turns it on. |
| `OpenAIAgentsPayloadMapper` | K9 payload to SDK input; `RunResult` to `{status, result, output_text}`. Called once, at the facade. |
| `K9OpenAIAgentsAdapter` | Facade: `execute()` / `execute_async()`. |
| `ToolCapability` | Moved from the Claude package to a shared module so both adapters use one type; the Claude package re-exports it (no break). |

### 4.2 Governed path

1. Zero Trust (`apply_zero_trust`, when enabled), then ingress (`apply_pre_governance`) on the prompt. Done before `Runner.run()`, so the parallel default of agent-level guardrails does not matter.
2. Every function tool call: Shield egress check, then the tool gate when enabled. Handoff agents get the same guardrails because the adapter builds them.
3. Every tool result: `screen_tool_result()` before the model reads it.
4. Every model call: `K9ModelProvider` and `K9GovernedModel`.
5. Final output: egress check, then `publish_status`.

### 4.3 Conformance tier

**Action and inference governed.** This is stronger than the Claude adapter,
which is action-governed only, because the OpenAI SDK has a model seam and the
Claude Agent SDK does not. Limits to state plainly:

- Models must be OpenAI-compatible and support tool calling. Catalog entries
  declare a `tool_calling` capability and the provider requests it as a hard
  requirement.
- Hosted tools are refused at construction (`ValueError`), because nothing local
  sees them. An explicit `allow_hosted_tools=True` lets them through and is
  logged as ungoverned.
- Agent-level SDK guardrails supplied by the caller are not accepted; Shield is
  the guardrail.

### 4.4 Human review: decision needed

Two pause mechanisms exist: the SDK's `needs_approval` (resumes inside the same
run state) and the K9 tool gate (durable, across processes, through k9x HIL).
Recommended: the K9 gate decides. On `hil` the adapter saves `RunState.to_json()`
with the correlation id, and the Orchestrator publishes the review. On approval,
the dispatcher runs the stored call once, and the adapter restores the run
state and supplies that stored result, so the call is never proposed twice.
**Unverified:** that a restored `RunState` accepts an externally produced tool
result. Phase 1 checks this first; if it does not, the fallback is to end the
run on review and start a new run with the approved result in context.

## 5. Design: Bedrock AgentCore

AgentCore has no single loop to wrap, so there are three integration points.
All three are planned; the order is in section 8.

### 5.1 Path A: a K9-AIF application hosted in AgentCore Runtime

The entrypoint hands each invocation to an ordinary K9 Router and Orchestrator.
Everything K9-AIF does in-process keeps working; AgentCore supplies hosting,
scale and identity.

| AgentCore service | K9-AIF ABB it maps to | Work |
|---|---|---|
| Runtime (`BedrockAgentCoreApp`) | Router entry (`BaseRouter.admit()`) | Example code only |
| Inbound JWT authorizer | `OIDCAuthenticator` principal | Configuration; the claims reach K9 through request headers |
| Memory | `BaseSessionStore` | New `AgentCoreMemorySessionStore` |
| Bedrock models | `BaseLLM` / `BaseProviderAdapter` | New `BedrockLLM` (Converse API) and provider adapter; also closes the GovCloud gap noted in the paper's supplementary S19 |
| Observability (OpenTelemetry) | `OTelMonitor` | Configuration |
| Identity outbound credentials | `BaseSecretManager` | Optional `AgentCoreIdentitySecretAdapter`, later |

### 5.2 Path B: `BedrockAgentCoreOrchestratorAdapter`

Framework package `k9_adapters/bedrock_agentcore/`, same shape as section 4.1.
Two modes, and their tiers differ:

| Mode | Wraps | Tool calls | Tier |
|---|---|---|---|
| `harness` | `InvokeHarness`, with tools the adapter declares as `inline_function` | Each `tool_use` stop comes back to the adapter: Shield check, gate, handler, result screening, then the next call. Same chokepoint as the Claude adapter's `can_use_tool`. | Action-governed for inline tools. Gateway, MCP, browser and code-interpreter tools run server-side: refused unless `allow_server_side_tools=True`, which requires Path C on that Gateway. Inference: governed only when the model config points at a K9-routed endpoint (to be verified). |
| `runtime` | `InvokeAgentRuntime`, an agent someone else built | Not visible to the adapter | Boundary-governed: Zero Trust, ingress, egress, audit. Tool-level only through Path C. |

`harness` mode depends on the unverified inline-function round trip in 2.2.
If the live run shows tools execute elsewhere, `harness` mode drops to
boundary-governed and the plan says so.

### 5.3 Path C: Shield as a Gateway interceptor

A Lambda registered at `REQUEST` and `RESPONSE` on an AgentCore Gateway runs
Shield's tool-call and tool-result checks (and the gate, when its state store
is reachable). Every agent that uses the Gateway is covered, in any framework,
including a Strands or LangGraph agent K9-AIF never hosted.

Cedar and Shield do different jobs and should both run. Cedar decides who may
call which tool. Shield checks what the call carries: injection, PII, arguments
against records. The blog should say this.

## 6. Shared example scenario

One scenario on both platforms, so the blog can compare like with like. It
continues the 1.25.0 tool-gate post: a support agent that looks up an order and
issues refunds.

| Tool | Registry | Demonstrates |
|---|---|---|
| `lookup_order(order_id)` | reversible | Allowed; its result carries an injected instruction, caught by tool-result screening |
| `issue_refund(order_id, amount, account)` | irreversible; `account` must match the order's record | Mismatch goes to a person; a clean call needs a named rule to skip review |

Runs to show, each a script with recorded output:

1. Clean request, allowed end to end.
2. Prompt injection in the request, blocked at ingress.
3. Injection inside a tool result, withheld before the model reads it.
4. Refund to an account that is not on record, sent to human review, approved, executed once.
5. Confidential request routed to an on-prem model (OpenAI path, Ollama through its OpenAI-compatible API).
6. Bedrock only: the same refund call through a Gateway, stopped by the interceptor.

### Folder layout

```
k9x_openai_bedrock/
  project_plan.md          this file
  README.md                what the examples show, how to run them
  diagrams/                PlantUML sources and PNGs (section 7)
  shared/                  scenario: tools, records, rules, config.yaml
  openai/                  run_*.py, config, live test
  bedrock/
    runtime_app/           Path A entrypoint
    harness/               Path B examples
    gateway_interceptor/   Path C Lambda
```

The examples import `k9_aif_abb`, so "built on K9-AIF" is accurate for them.

## 7. Diagrams

Default PlantUML style, no custom skinparams. Drafts are in `diagrams/`:

| File | Content |
|---|---|
| `openai_block.puml` | Caller, adapter, SDK Runner, model provider, tools, Shield, tool gate, HIL |
| `openai_class.puml` | Classes in section 4.1 and the SDK types they use |
| `bedrock_block.puml` | Paths A, B and C on one page |
| `bedrock_class.puml` | Classes in sections 5.1 to 5.3 and the AWS types they use |

The framework packages get their own copies under `docs/`, as the Claude
adapter does.

## 8. Phases

Each phase ends with something that runs. Framework changes go in 1.27.0,
since they add behaviour (minor version).

| Phase | Work | Exit criterion |
|---|---|---|
| 0 | Review this plan; settle section 10 | Ravi's go |
| 1 | Spikes, no framework code: RunState resume with an external result; Harness inline-function round trip (needs AWS) | Both answered from live runs, written into section 2 |
| 2 | Framework: shared `ToolCapability`; `openai_agents` package; mocked tests | Unit tests pass; `test_capability_index` updated |
| 3 | OpenAI examples 1 to 5; live test with OpenAI and with Ollama | One governance event per tool call seen in a live run, asserted in the test |
| 4 | Framework: `BedrockLLM` + provider adapter; `AgentCoreMemorySessionStore`; `bedrock_agentcore` package | Unit tests pass; live Converse call |
| 5 | Bedrock examples: Path A deployed to Runtime, Path B, Path C interceptor | Examples 1 to 4 and 6 run on AWS with recorded output |
| 6 | Diagrams final; package docs; `CAPABILITIES.md` rows; 1.27.0 release notes | Release tagged; Ravi publishes PyPI and the GitHub release |
| 7 | Blog and LinkedIn drafts | After Ravi supplies a real incident and his opinion |

## 9. Tests

- Mocked tests prove wiring only. Each adapter also gets a live test that
  asserts a per-tool-call governance event, as the Claude adapter's live test
  does. That test caught that `can_use_tool` was never being called.
- Construction tests: hosted or server-side tools refused; handoff and subagent
  tools must be a subset of registered capabilities.
- Exceptions propagate: agent to squad to orchestrator, none swallowed.

## 10. Decisions for Ravi

1. **Location:** adapters in the framework as OOB packages (recommended, matches
   Claude, LangGraph and CrewAI), with examples here.
2. **AWS account:** Phases 1, 4 and 5 need one with Bedrock model access and
   AgentCore in a region that offers it. Which account and region?
3. **OpenAI key:** live runs against OpenAI need an API key and a spending limit.
   The Ollama runs need only PowerAI.
4. **Human review on the OpenAI path:** K9 gate decides (recommended, 4.4), or
   use the SDK's `needs_approval`.
5. **Scope of 1.27.0:** both adapters together, or OpenAI first as 1.27.0 and
   Bedrock as 1.28.0. Recommended: OpenAI first, since it needs no cloud account.
6. **Tool-gate adapter gating (1.25.1):** fold the same gate session into the
   Claude, LangGraph and CrewAI adapters in the same release, so all five
   adapters behave alike when the gate is on.

## 11. Risks and honesty items

- Hosted OpenAI tools and server-side AgentCore tools are outside any local
  check. The adapters refuse them by default and the docs say why.
- `runtime` mode governs only the boundary of an agent K9-AIF did not build.
- Platform facts in section 3 that are not in section 2 come from vendor
  documentation. They stay marked "D" until a live run makes them "E".
- No public numbers (latency, cost, block rates) without a recorded run behind them.

## 12. Found along the way (outside this project)

- `K9XLiteLLMBridgeAdapter.call()` catches `RuntimeError` and returns the string
  `"[K9X ERROR] LLM unavailable: ..."` as model output. That breaks the
  exceptions-propagate rule and lets a CrewAI agent treat an outage as an answer.
  Worth a fix in the 1.27.0 release.
