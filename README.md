# ScreamingFace

An AI ensemble system that routes coding CLI prompts through multiple models (Claude, Gemini, Codex, Ollama) to beat SOTA benchmarks. Built by OpenMined.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | >= 3.12 | [python.org](https://www.python.org/downloads/) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | >= 18 | [nodejs.org](https://nodejs.org/) |
| mkcert | latest | `brew install mkcert` (macOS) |

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
  server/    Python FastAPI server with plugin architecture (uv)
  desktop/   Electron control-plane app (electron-vite, React, Tailwind)
  web/       Marketing website (Next.js)
packages/    Shared packages
```

## Quick Start

### 1. Server

```bash
cd apps/server
uv python install 3.13
uv venv --python 3.13
uv sync --extra tracing          # install dependencies
uv run sf run                    # start server (reads sf.json)
```

The server auto-generates SSL certs via mkcert on first run. It binds to `https://0.0.0.0:8000` by default (auto-increments port if busy).

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
  "version": "0.1.0",
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "reload": true,
    "ssl": true
  },
  "plugins": ["claude-frontend", "claude-env-intercept", "tracing", "url-executor"],
  "url4config": null,
  "plugin_config": {
    "claude-frontend": {
      "upstream_url": "https://api.anthropic.com",
      "api_key_env": "ANTHROPIC_API_KEY"
    }
  }
}
```

Set your Anthropic key so the proxy can forward requests:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

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

```bash
cd apps/web
npm install
npm run dev                      # Next.js dev server
```

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | Claude API key for the proxy plugin | For claude-frontend |
| `SF_CONFIG` | Inline JSON config (overrides sf.json) | No |

## Running Tests

```bash
# Server (Python)
cd apps/server
uv run pytest -v

# Desktop (lint only, no test suite yet)
cd apps/desktop
npm run lint
```

## Plugin System

The server uses a plugin architecture inspired by Odoo. Plugins are discovered via entry points and activated in `sf.json`.

Built-in plugins:
- **claude-frontend** -- forwards Claude API requests to Anthropic (with optional url4 context enrichment)
- **claude-env-intercept** -- writes proxy env vars to shell profile so Claude Code uses the local server
- **claude-cli** -- runs Claude CLI commands from the server
- **tracing** -- OpenTelemetry instrumentation (requires `uv sync --extra tracing`)
- **claude-intercept** -- DNS/hosts interception to transparently redirect Claude API traffic
- **url-executor** -- executes url4 protocol URLs

## Pointing Claude Code at the Proxy

Once the server is running with `claude-frontend` and `claude-env-intercept` plugins:

```bash
# The claude-env-intercept plugin writes these to your shell profile automatically.
# If you need to set them manually:
export ANTHROPIC_BASE_URL="https://localhost:8000"
export NODE_EXTRA_CA_CERTS="$(mkcert -CAROOT)/rootCA.pem"
```

Then start Claude Code normally -- all API requests route through the local proxy.
