# FinancialAnalysisAi

| | |
|---|---|
| **Studio** | [studio.k9x.ai](https://studio.k9x.ai) |
| **Framework** | [k9x.ai](https://k9x.ai) — K9-AIF Architecture-First |
| **Generated** | 2026-09-10 23:47:14 |
| **Author** | — |
| **LLM** | — |
| **Generation** | rule-based |

---

**Domain:** finance
**Description:** A financial analysis platform that ingests market data and portfolio positions, generates risk assessments, validates regulatory compliance, and produces investment recommendations.

## Quick start

```bash
unzip financial_analysis_ai.zip
cd financial_analysis_ai

./setup.sh                      # one-time: venv, framework path, deps, .env
source .venv/bin/activate       # if setup.sh created .venv/ for you
./run.sh
```

`setup.sh` walks you through:

- creating (or using) a Python virtual environment
- pointing at — or cloning — a `k9-aif-framework` checkout
- installing this project's and the framework's dependencies
- writing `K9_ENV` and `K9_FRAMEWORK_PATH` into `.env`

Run `./setup.sh --verify` at any time to re-check the environment.

## Recommended workspace layout

```
workspace/
├── financial_analysis_ai/        <- this project (unzipped here)
└── k9-aif-framework/      <- sibling clone (setup.sh option 2)
```

If you already have a `k9-aif-framework` checkout elsewhere, point `setup.sh`
at it instead (option 1) — it sets `K9_FRAMEWORK_PATH` in `.env` accordingly.

This scaffold is self-contained: `setup.sh` and `run.sh` work directly from
this folder, with no dependency on the canonical generator's project-nesting
layout.

## Prerequisites

- Python 3.11 or 3.12 (avoid 3.14 — `venv`/`ensurepip` issues)
- A `k9-aif-framework` checkout (existing, or let `setup.sh` clone one)
- Ollama running at http://localhost:11434, with these models pulled:

  ```bash
  ollama pull llama3.2:1b        # "general" model — used by BaseAgent steps
  ollama pull granite3-dense:2b  # "reasoning" model — used by K9ValidationLoopAgent
                                  # and K9CriticActorAgent steps
  ```

  If a model isn't pulled, Ollama returns an error that gets passed through
  as the agent's "response" text (e.g. `[WARN] Ollama HTTP 404 | model=...`)
  instead of a clear failure — agents will run but produce garbage output.
  Run `ollama list` to check what's already available.

## Structure

```
financial_analysis_ai/
├── agents/src/       # Agent Python classes
├── agents/yaml/      # Agent configuration
├── orchestrators/    # Orchestrator classes
├── config/           # config.yaml + squads.yaml
├── utils/            # agent_loader.py
├── main.py           # Entry point
├── setup.sh          # One-time environment setup (venv, framework, deps, .env)
├── run.sh            # Launch script
├── requirements.txt  # Project-level Python dependencies
├── .env              # K9_ENV, K9_FRAMEWORK_PATH (written by setup.sh)
└── CLAUDE.md         # Claude Code context
```

## Troubleshooting

**`ModuleNotFoundError: No module named 'k9_aif_abb'`**
`K9_FRAMEWORK_PATH` in `.env` doesn't point at a valid `k9-aif-framework`
checkout, or its `requirements.txt` isn't installed. Run `./setup.sh --verify`
to check, or `./setup.sh` to fix it.

**`ModuleNotFoundError: No module named 'orchestrators'`** (or `agents`, `utils`)
`run.sh`/`setup.sh` add this project's folder to `PYTHONPATH` automatically.
If you're running `python3 main.py` directly, `cd` into this folder first so
its `PYTHONPATH` entry resolves, or use `./run.sh`.

**Wrong `K9_FRAMEWORK_PATH`**
Edit `.env` directly, or re-run `./setup.sh` and choose the correct option
(existing folder vs. clone). Paths may be absolute or relative to this
project's folder (e.g. `../k9-aif-framework`).

**Python 3.14 `venv`/`ensurepip` errors**
`setup.sh` prefers `python3.12`/`python3.11` when creating `.venv/`. If only
Python 3.14+ is available, install 3.12 or 3.11 and re-run `./setup.sh`.

**No virtual environment active**
`./setup.sh` offers to create `.venv/` for you, or lets you activate your own.
After creating one, run `source .venv/bin/activate && ./setup.sh --continue`.

**`requirements.txt` install failed**
Re-run `./setup.sh` after fixing the underlying issue (network access,
compiler toolchain for native deps, etc.) — `pip install --upgrade pip
setuptools wheel` runs first to reduce build issues.
