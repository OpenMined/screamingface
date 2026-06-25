# ScreamingFace

An AI ensemble system that routes coding CLI prompts through multiple models (Claude, Gemini, Codex, Ollama) to beat SOTA benchmarks. Built by OpenMined.

> **📖 Setting up? Read [`docs/SETUP.md`](docs/SETUP.md).** It is the definitive,
> end-to-end guide — system requirements, installing the packaged app, running
> from source, **connecting the AI backends** (incl. the Antigravity activation
> gotcha), and cutting a build. The quickstart below is a condensed dev path; if
> the two disagree, `docs/SETUP.md` wins.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | >= 3.12 | [python.org](https://www.python.org/downloads/) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | >= 18 | [nodejs.org](https://nodejs.org/) |
| mkcert | optional | `brew install mkcert` (macOS) — only needed if you turn SSL on |

Verify:
```bash
python3 --version   # 3.12+
uv --version
node --version      # 18+
mkcert -version
```

## Monorepo Layout

```
apps/
  server/      Python FastAPI plugin server — URL4 engine, frontends, python runner (uv)
  desktop/     Electron control-plane app (electron-vite, React, Tailwind)
  aigateway/   LiteLLM-based AI Gateway — provider OAuth + encrypted credentials (uv)
  scoreboard/  Public benchmark scoreboard service
web/           Static marketing site
```

## Quick Start

### 1. Server

```bash
cd apps/server
uv sync                          # install dependencies (uv manages Python 3.12+)
uv run sf run                    # start server (reads sf.json)
```

> Add `--extra tracing` to `uv sync` if you want the OpenTelemetry tracing plugin.

It binds to `http://127.0.0.1:8000` by default (SSL is **off** in the shipped `sf.json`; the port auto-increments if busy). To enable SSL, set `"ssl": true` in `sf.json` and install mkcert.

Useful commands:
```bash
uv run sf --help                 # CLI reference
uv run sf run --no-ssl           # skip SSL if mkcert not installed
uv run sf run --port 9000        # custom port
uv run sf run --enable claude-frontend  # run only specific plugins
uv run sf plugin list --json     # list discovered plugins
uv run pytest                    # run tests
uv run ruff check src tests      # lint
```

#### Server Configuration

All config lives in `apps/server/sf.json`:

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8000,
    "reload": true,
    "ssl": false
  },
  "plugins": ["tracing", "url4-executor", "claude-frontend", "aigw-base", "aigw-runner", "..."],
  "plugin_config": {
    "claude-frontend": { "upstream_url": "https://api.anthropic.com", "listen_port": 9101 },
    "aigw-runner": { "port": 9105 }
  }
}
```

The shipped `sf.json` activates ~21 plugins (the URL4 engine, the per-provider
frontends, and the AI Gateway stack). Run `uv run sf plugin list` to see the
live set.

Provider credentials (Claude, Codex, Gemini, Antigravity) are connected through
the **AI Gateway** via browser OAuth on the app's **Settings** screen — you
don't paste API keys or set env vars. See
[`docs/SETUP.md` §4](docs/SETUP.md#4-connect-the-ai-backends-the-one-step-everyone-does).

### 2. Desktop App

```bash
cd apps/desktop
npm install                      # install dependencies
npm run dev                      # launch Electron in dev mode
```

The desktop app manages the Python server lifecycle automatically (venv creation, dependency sync, start/stop). On first launch it will:
1. Detect or create a Python venv in `apps/server/.venv`
2. Sync dependencies via `uv sync`
3. Start the server as a subprocess

Build for distribution:
```bash
npm run build                    # compile main/preload/renderer
npm run package                  # create platform installer (DMG/AppImage/NSIS)
```

### 3. Web (Marketing Site)

The marketing site is a **static** site under `web/` (no framework / build step).
Serve the directory with any static file server to preview it.

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `SF_CONFIG` | Inline JSON config (overrides sf.json) | No |

## Running Tests

```bash
# Server (Python)
cd apps/server
uv run pytest -v

# Desktop (Vitest)
cd apps/desktop
npx vitest run                   # unit/component tests (jsdom)
npm run lint                     # eslint

# AI Gateway (Python)
cd apps/aigateway
uv run pytest -m "not live"
```

## Plugin System

The server uses a plugin architecture inspired by Odoo. Plugins are discovered via entry points and activated in `sf.json`.

Key active plugins (run `uv run sf plugin list` for the full, live set):
- **url4-executor / url4-specs** -- the URL4 protocol engine and spec library
- **claude-frontend / codex-frontend / gemini-frontend / ollama-frontend** -- per-provider request frontends
- **aigw-base / aigw-runner / aigw-\*-backend** -- AI Gateway integration: provider OAuth and routing through the gateway on `:9105`
- **python-runner** -- sandboxed Python execution used for eval scoring (`check_correct`, `calculate_accuracy`)
- **data-store / private-storage / state / eval-runs** -- persistence and evaluation-run tracking
- **tracing** -- OpenTelemetry instrumentation (`uv sync --extra tracing`)

> The legacy `claude-env-intercept`, `claude-intercept`, and `mitmproxy-intercept`
> plugins are **deprecated and unmaintained** — they are not part of the active
> pipeline. Don't use them as a reference for how the gateway works.

## Using ScreamingFace

Connect your model subscriptions on the app's **Settings** screen, then drive
the ensemble from **Eval Studio** / **Sessions**, or via the `sf` CLI overlay.
The full flow is in [`docs/SETUP.md`](docs/SETUP.md).
