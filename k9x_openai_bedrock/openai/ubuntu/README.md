# Running the example on Ubuntu

`setup.sh` was run end to end on clean Ubuntu 22.04 and 24.04 images (2026-11-15).

Two ways to run it on Ubuntu: on your own machine (`setup.sh`), or as a container behind a tunnel
(`build-run.sh`, how openai.k9x.ai is served).

## On your machine

```bash
cd k9x_openai_bedrock/openai
./ubuntu/setup.sh            # first time: checks Python and Ollama, creates .env, starts the page
./run.sh                     # afterwards
```

What `setup.sh` does:

| Step | Ubuntu 24.04 | Ubuntu 22.04 |
|---|---|---|
| Python | Uses the system Python 3.12; installs `python3.12-venv` if missing | Python 3.10 is too old for K9-AIF (needs 3.11+): installs `python3.11` and `python3.11-venv` from the deadsnakes PPA |
| `.env` | Copies `env-example` to `.env` if there is none | same |
| Ollama | Checks `OLLAMA_BASE_URL` answers and has the model; prints what to do if not | same |
| Start | Runs `../run.sh` (creates `.venv` on first run, then serves http://127.0.0.1:8003) | same |

It asks for `sudo` only to install Ubuntu packages. It does not install Ollama: install it from
https://ollama.com/download/linux on this machine, or point `OLLAMA_BASE_URL` at a server you already run.

`./ubuntu/setup.sh --demo` runs the four terminal scenarios instead of the page.

To reach the page from another machine on your network, start it with `HOST=0.0.0.0 ./run.sh`
only on a network you trust: the page has no login.

## As a container (hosting)

`build-run.sh` follows the same pattern as `k9chat/ubuntu/build-run.sh`: one Podman container, built
from `ai/` (the parent of `k9-aif-framework/` and `k9-aif-examples/`), with the framework source copied
into the image.

```bash
cp env-example .env                      # set OLLAMA_BASE_URL to the Ollama server
./ubuntu/build-run.sh all                # build + start on 127.0.0.1:8121
./ubuntu/build-run.sh logs
```

| Command | Does |
|---|---|
| `build` | Builds `k9x-openai-weather:latest` (needs the framework with the OpenAI adapter: 1.27.0, or branch `feature/openai-agents-adapter`) |
| `start` | Runs it on `127.0.0.1:${HOST_PORT:-8121}` with `--env-file .env`, `K9_ENV=production`, `--restart=always` |
| `stop`, `logs`, `all` | As named |

The container listens on localhost only. Publish it with a tunnel or reverse proxy on the same host;
openai.k9x.ai is a Cloudflare tunnel to `localhost:8121`.

Public use is bounded in the app: six requests a minute per visitor (`WEATHER_RATE_PER_MIN` in `.env`),
one request at a time against the model server, at most 500 characters per request.
