# K9-AIF Framework, K9X Ecosystem and OpenAI Agents SDK in Collaboration

A small application you download and run on your own machine: give it a US ZIP code, get the current
weather. An **OpenAI Agents SDK** agent does the work. **K9-AIF** governs every step: Zero Trust for the
caller and the agent, k9x Shield on the request, every tool call, every tool result, every model reply and
the final answer, and the **K9 Model Router** choosing the model for every call.

No OpenAI API key is needed: the SDK talks to your Ollama server through its OpenAI-compatible API.

**Live demo: [openai.k9x.ai](https://openai.k9x.ai)** (demo login on the page).

![Weather by ZIP code](diagrams/weather_zip_block.png)

## Run it

You need Python 3.11 and an Ollama server with a tool-calling model:

```bash
ollama pull qwen2.5:7b
cp env-example .env          # set OLLAMA_BASE_URL if Ollama isn't on localhost
./run.sh                     # first run creates .venv; then open http://127.0.0.1:8003
./run.sh --demo              # the four scenarios below, in the terminal
```

`run.sh` installs K9-AIF from a local framework checkout when one sits next to this repository (or
`K9_FRAMEWORK_DIR` points to it), otherwise from PyPI (`k9-aif[openai-agents,server]>=1.27.0`). The OpenAI
Agents SDK adapter is on the framework's `main` branch and ships to PyPI in k9-aif 1.27.0; until that
release, use a framework checkout.

It runs locally and calls two free public services (api.zippopotam.us, api.open-meteo.com) and your
model server. On Ubuntu, see [ubuntu/README.md](ubuntu/README.md): `ubuntu/setup.sh` for your own machine,
`ubuntu/build-run.sh` for a container behind a tunnel (how https://openai.k9x.ai is served).

## What you'll see

| Try | Result | K9-AIF at work |
|---|---|---|
| A normal ZIP code, as `customer` | The weather, with every check listed | Zero Trust, Shield at six points, Model Router on every call |
| The same ZIP code, as `guest` | Refused before any agent runs | Zero Trust role policy |
| A ZIP code followed by "Ignore all previous instructions..." | Refused at ingress | Shield `PromptInjectionCheck`, before the SDK starts |
| "Poison the upstream response" | The tool result is withheld; the agent says so | Shield screens what tools return |

The page's **Architecture** tab shows how the pieces fit, what is checked where, the agent's YAML and the
policy in force, and the last request step by step.

The **Multi-agent** tab shows several OpenAI agents run the K9-AIF way: each agent is an individual,
runnable step (`K9OpenAIAgent`, k9-aif 1.28.0), and a K9-AIF squad runs them in the order of its flow, with
synthesis. The squad decides which agent runs next, never the model. Handoffs, where the model picks the
agent, remain an explicit opt-in (`Agent Routing: handoffs` in the design spec). The tab offers
[design_spec.md](webui/static/design_spec.md) to download. Upload it in [K9X Studio](https://studio.k9x.ai)
Intake: it sets the agent framework to OpenAI Agents SDK with sequence routing and stages FrontDeskAgent,
WeatherAgent and AttireAdvisorAgent in one squad, ready to scaffold. Building and running it is left to the
developer as an exercise; the tab shows a real run.

Video (4 minutes): https://www.youtube.com/watch?v=75HKTX9BdmI

## Where the code is

The orchestrator adapter is part of the K9-AIF framework, like its CrewAI, LangGraph and Claude Agent SDK
adapters: `k9_aif_abb/k9_adapters/openai_agents/` in
[k9-aif-framework](https://github.com/k9aif/k9-aif-framework) (on `main`; on PyPI from
1.27.0). This example configures it in `weather_zip/app.py` (`build_adapter()`, named
`WeatherZipOrchestrator`) and supplies only the tools, the agent YAML and the policy.

## Accounts payable with K9X HIL (use case 3)

`accounts_payable/` is a K9-AIF application whose squad has two OpenAI agents and a rules step:

```
K9EventRouter -> Kafka openai.ap.in -> APOrchestrator -> squad ap_invoice
  InvoiceAgent (K9OpenAIAgent)   reads vendor, invoice and amount (structured output)
  APRulesAgent (K9RulesAgent)    facts from the records -> K9X Rules Engine (currently GoRules): AP-01..AP-08
  PaymentAgent (K9OpenAIAgent)   pay_invoice (simulated); needs_approval_when the rules said needs_approval
```

When the rules require a person (over $15,000, a changed bank account, a new vendor, ...), the OpenAI SDK pauses
the run. `OpenAIHILAdapter` saves it in `PausedRunStore` and raises `RequiresHIL`. The orchestrator publishes
`hil.requests.openai-ap-payments` to K9X HIL (application *OpenAI Demo Application*, queue *Invoice Approvals*).
The decision comes back on `hil.replies.openai-ap-payments`, and the Router resumes. The squad skips the steps
already done, and PaymentAgent continues the same OpenAI run.

Each paused payment becomes a K9X HIL task in HIL's own task contract (`k9x.hil.task/v1`). The invoice is a PDF in
object storage: `accounts_payable/invoices/upload_invoices.py` puts the four demo invoices in the bucket
`openai-ap-invoices`, and the task carries the invoice's `s3://` link as its primary artifact, so K9X HIL fetches it
for the reviewer. The rules' approver role decides who may approve: a manager, with a written justification, for
AP-03 and AP-04, and otherwise anyone in the queue. The task's deadline is 24 hours, after which the payment is
rejected.

Use case 3 has its own page, `/ap` (the weather demo is `/app`): **Run an invoice** shows the run, the rule that fired and a K9X HIL pane; **Architecture** shows the flow. The pane
reads and decides the task through K9X HIL's REST API, using `HIL_API_KEY`, which stays on the server. The
demo is on when `KAFKA_BOOTSTRAP_SERVERS` is set. The other keys are in `env-example`: the rules engine URL,
the HIL URL and key, and PostgreSQL (schema `openai`; SQLite under `runtime/` otherwise).

## The page

`/` is a public overview. **Try the demo** signs you in with the demo login (shown on the page; there is no
admin account) and opens `/app`. Every sign-in is its own private session: nothing one visitor sends or
receives is stored or shown to anyone else, and answers are sent with `Cache-Control: no-store`.

## Read more

- [integration-design.md](integration-design.md): what the OpenAI Agents SDK provides, what K9-AIF adds,
  where the adapter sits, and every check
- [example-implementation.md](example-implementation.md): this application file by file, with a recorded run
- [spike_openai_ollama.py](spike_openai_ollama.py): the first experiment, the SDK on Ollama with tool guardrails

## Layout

```
config/config.yaml              Model Router catalog, Shield checks, Zero Trust
agents/yaml/weather_agent.yaml  the OpenAI agent, in K9-AIF agent YAML
weather_zip/                    tools, wiring, request service, command line
accounts_payable/               use case 3: agents + squad YAML, rules step, orchestrator, runtime
webui/                          the page (local or container)
ubuntu/                         setup.sh (Ubuntu machine), build-run.sh + Containerfile (container)
diagrams/                       PlantUML sources and PNGs (ap_hil_sequence: the AP run, pause and resume)
run.sh                          set up and start
```

## License

Apache-2.0, as the rest of this repository.
