# ScreamingFace

An AI ensemble system that routes coding CLI prompts through multiple models (Claude, Gemini, Codex, Ollama) to beat SOTA benchmarks. Built by OpenMined.

> **📖 Setting up?**
> - **Installing / using the app** → [`docs/SETUP.md`](docs/SETUP.md): the
>   definitive end-to-end guide (system requirements, packaged-app install,
>   **connecting the AI backends** incl. the Antigravity gotcha, cutting a build).
> - **Developing / running from source** → [`CONTRIBUTING.md`](CONTRIBUTING.md):
>   the canonical dev guide (clone, run, ports, tests, git workflow).
>
> The quickstart below is a condensed dev path; if it disagrees with those, they win.

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

## Running it

Full instructions live in the two canonical guides — this avoids a third copy
drifting out of sync:

- **Run from source / develop** → [`CONTRIBUTING.md`](CONTRIBUTING.md): clone,
  run via the desktop app or the headless server, ports, `sf.json` config,
  tests, and the git workflow.
- **Install the packaged app + connect the AI backends** →
  [`docs/SETUP.md`](docs/SETUP.md).

Thirty-second from-source path:

```bash
git clone https://github.com/OpenMined/screamingface.git
cd screamingface
git config core.hooksPath .githooks      # pre-commit guards
make sync                                # uv-sync server + aigateway
cd apps/desktop && npm install && npm run dev   # desktop app auto-starts the server
```

The marketing site under `web/` is static (no build step) — serve the directory
with any static file server to preview it.

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
