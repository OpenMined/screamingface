# Contributing to ScreamingFace

This guide is for **running ScreamingFace from source and developing it**. If you
just want to *install and use* the packaged app, or connect your model
subscriptions, read [`docs/SETUP.md`](docs/SETUP.md) instead — that's the
end-user setup guide.

ScreamingFace is three cooperating pieces, all in this monorepo:

- **Desktop app** (`apps/desktop/`) — Electron control plane (React + Vite +
  Tailwind). Owns the UI and **manages the local server for you** (creates the
  venv, syncs deps, starts/stops the process).
- **Local server** (`apps/server/`) — FastAPI, plugin-based. Runs the URL4
  engine, the per-provider frontends, and the Python runner. Reads
  `apps/server/sf.json`.
- **AI Gateway** (`apps/aigateway/`) — LiteLLM-based service that holds provider
  credentials and brokers OAuth/refresh. The server starts it automatically
  (the `aigw-runner` plugin) on port `9105`.

There is also a static marketing site under `web/` and a public scoreboard
service under `apps/scoreboard/`.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | ≥ 3.12 | `uv` installs and pins this for you; no system Python needed. |
| uv | latest | Python toolchain/installer. `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | ≥ 18 | Only for the desktop app. |
| mkcert | optional | Only if you run the server with SSL on (default dev config is plain HTTP). |

## Get the code

```bash
git clone https://github.com/OpenMined/screamingface.git
cd screamingface
git config core.hooksPath .githooks   # enables the pre-commit guards (see Git workflow)
make sync                             # uv-syncs apps/server + apps/aigateway
```

## Run from source

There are two ways. Pick one.

### Option A — via the desktop app (recommended)

```bash
cd apps/desktop
npm install
npm run dev      # launches Electron; auto-creates the venv, uv-syncs, starts the server
```

The desktop app owns the server lifecycle — you do **not** start the server or
the gateway by hand. On first launch it creates a venv in `apps/server/.venv`,
runs `uv sync`, and spawns `sf run` as a subprocess. The AI Gateway is started
automatically by the server's `aigw-runner` plugin.

Build/package the app locally:

```bash
npm run build      # compile main/preload/renderer
npm run package    # electron-builder → dist/<platform>/
```

### Option B — headless server (no desktop)

```bash
make run-server                  # = uv run sf run in apps/server (reads ./sf.json)
# or, equivalently:
cd apps/server && uv run sf run
```

The dev default (from `apps/server/sf.json`) binds **`http://127.0.0.1:8000`**
with SSL **off**. Useful flags:

```bash
uv run sf --help                  # full CLI reference
uv run sf run --port 9000         # change the port
uv run sf run --no-ssl            # explicitly disable SSL (already off by default)
uv run sf plugin list --json      # list discovered plugins + status
uv run sf run --disable aigw-runner   # don't auto-start the gateway
```

Run the gateway on its own (the server normally does this for you):

```bash
make run-aigateway                       # uvicorn aigateway.main:app --port 9105 --reload
curl -sf http://localhost:9105/healthz   # liveness check
```

### Ports

| Service | Port | Source |
|---------|------|--------|
| Local server | `8000` | `sf.json` → `server.port` |
| AI Gateway (`aigw-runner`) | `9105` | `sf.json` → `aigw-runner.port` |
| claude-frontend | `9101` | `sf.json` |
| codex-frontend | `9102` | `sf.json` |
| ollama-frontend | `9103` | `sf.json` |
| Ollama (upstream) | `11434` | local Ollama install |

If a port is busy the server increments to the next free one.

## Connect AI backends

Connecting model subscriptions (Claude, Codex, Gemini, Antigravity, Ollama) is
the same from source as for the packaged app — browser OAuth on the **Settings**
screen, brokered and stored by the AI Gateway (encrypted `credential_blobs`, no
OS keychain). See
[`docs/SETUP.md` §4](docs/SETUP.md#4-connect-the-ai-backends-the-one-step-everyone-does),
including the Antigravity activation gotcha.

## Tests, lint, typecheck

All targets are in the `Makefile` (`make help` lists them). The Python suites run
through `uv`; the desktop suite runs through Vitest.

```bash
# Python (server + aigateway)
make test            # full unit suite (no live)
make test-fast       # skip the slow e2e marker
make test-server     # apps/server only
make test-aigateway  # apps/aigateway only (skips live)
make test-e2e        # apps/server parallel CLI e2e (claude/codex/gemini/multi)
make lint            # ruff lint every subproject
make fmt             # ruff format
make typecheck       # pyright

# Desktop (Vitest — note: no `test` npm script, call vitest directly)
cd apps/desktop
npx vitest run       # unit/component tests (jsdom)
npm run lint         # eslint
```

`make test-aigateway-live` exercises real provider OAuth and is skipped in CI;
run it locally (with backends actually connected) before asking to merge changes
that touch the gateway request/refresh path.

## Git workflow

- **Branch naming:** `SF-{n}-{description}` (e.g. `SF-344-contributing-guide`),
  where `{n}` is the ticket's `SF` number.
- **Never commit directly to `main`.** The `.githooks/pre-commit` hook (enabled
  by `git config core.hooksPath .githooks` above) blocks it.
- **Conventional commits.** Use `feat:`, `fix:`, `docs:`, `chore:` etc. —
  release-please derives version bumps and changelogs from them (`feat:` → minor,
  `fix:` → patch; `docs:`/`chore:` don't bump). See "Cut a build" below.
- **Architecture is enforced.** Core must not import from plugins/adapters;
  plugins implement core's ports. DRY/SOLID/hexagonal are mandatory — see the
  "Architecture Principles" section of [`CLAUDE.md`](CLAUDE.md) before adding a
  backend or transport.

## Cut a build / release

Releases are automated with release-please and produce the installable app. The
full flow (release PR → tag → installer build → publish/mirror) is documented in
[`docs/SETUP.md` §6](docs/SETUP.md#6-cut-a-new-build--release).

## Reference

- **Make targets:** `make help`
- **Server config & plugins:** `apps/server/sf.json`, `apps/server/README.md`
- **Gateway internals:** `apps/aigateway/README.md` (credential store, secret key,
  migrations)
- **Desktop internals:** `apps/desktop/ARCHITECTURE.md` (venv bootstrap, bundled
  Python, packaging)
- **Glossary:** `docs/GLOSSARY.md` (url4, Enclave, Ensemble, SOTA, …)
