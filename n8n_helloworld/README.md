# K9-AIF × n8n — Hello World

Minimal end-to-end example showing n8n triggering a K9-AIF governed agent pipeline via REST API.

## What this demonstrates

```
n8n → HTTP POST → Orchestrator → Squad → Agent → Response
```

The K9-AIF framework is installed automatically via `pip install k9-aif` during the container build. No framework source code needed.

## Prerequisites

- Podman installed on your machine
- n8n running (included in the pod via `run_pod.sh`)

## Quick Start

```bash
# 1. Build the K9-AIF container image
bash build.sh

# 2. Start n8n + K9-AIF in a shared pod
bash run_pod.sh
```

- n8n UI: `http://<your-ip>:5678`
- K9-AIF API: `http://<your-ip>:8001`

## n8n Workflow Setup

1. Open n8n at `http://<your-ip>:5678`
2. Create a new workflow
3. Add a **Manual Trigger** node
4. Add an **HTTP Request** node:
   - Method: `POST`
   - URL: `http://192.168.1.98:8001/run`
   - Body Content Type: `JSON`
   - Body: `{ "caller": "n8n" }`
5. Execute the workflow

## Expected Response

```json
{
  "status": "success",
  "result": {
    "squad_id": "HelloWorldSquad",
    "hello": {
      "message": "Hello World from K9-AIF Agent! 👋 Triggered by: n8n",
      "caller": "n8n",
      "agent": "HelloWorldAgent",
      "status": "success",
      "pipeline": "Router → Orchestrator → Squad → Agent"
    }
  }
}
```

## Test directly

```bash
curl -X POST http://<your-ip>:8001/run \
  -H "Content-Type: application/json" \
  -d '{"caller":"test"}'
```

## Structure

```
n8n_helloworld/
├── agents/
│   ├── src/hello_world_agent.py      # The K9-AIF agent (SBB)
│   └── yaml/hello_world_agent.yaml   # Agent configuration
├── orchestrators/
│   └── hello_world_orchestrator.py   # Coordinates the squad
├── config/
│   ├── config.yaml                   # Framework config (LLM, inference)
│   └── squads.yaml                   # Squad and flow definition
├── api/
│   └── app.py                        # FastAPI entry point
├── Containerfile                     # pip install k9-aif + COPY SBBs
├── build.sh                          # Build the container image
└── run_pod.sh                        # Start n8n + K9-AIF in n8n_pod
```

## Learn More

- Framework: [github.com/k9aif/k9-aif-framework](https://github.com/k9aif/k9-aif-framework)
- Documentation: [pydocs.k9x.ai](https://pydocs.k9x.ai)
- Main site: [k9x.ai](https://k9x.ai)
