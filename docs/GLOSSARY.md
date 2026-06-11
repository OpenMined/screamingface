# ScreamingFace — Project Glossary

A reference map of every app/component in the monorepo and every plugin in the `server` and
`aigateway` apps. Reflects the actual on-disk structure (note: the historical `web/app/cloud`
description predates the current `apps/` layout).

---

## 1. Apps & Top-Level Components

| Component | Path | Role | Stack |
|-----------|------|------|-------|
| **Server** | `apps/server` | Plugin-based FastAPI proxy/orchestration core. Routes coding-CLI prompts to the best backend, runs the url4 engine, intercepts CLI traffic, persists eval runs. The heart of the ensemble. | Python 3.12, FastAPI, Uvicorn, mitmproxy, TatSu, Tortoise ORM, uv |
| **AIGateway** | `apps/aigateway` | LiteLLM-based unified gateway. Exposes an OpenAI-shaped `/v1/chat/completions` and dispatches to Anthropic/OpenAI/Gemini/Ollama. Owns provider OAuth, credential storage, profiles, JWT auth. Runs standalone or is spawned by the server. | Python 3.12, FastAPI, LiteLLM, Tortoise ORM, SQLite/Postgres, PyJWT, bcrypt |
| **Desktop** | `apps/desktop` | Electron control plane. Bundles + manages the local Python server lifecycle (bootstrap venv, dep sync, health checks, auto-restart) and hosts the React dashboard UI (Settings, Spend, Eval Studio, Cache/Log). | TypeScript, Electron 41, React 19, Vite, Tailwind, shadcn/ui, electron-builder |
| **Scoreboard** | `apps/scoreboard` | Public benchmark scoreboard service: health endpoint, score persistence, leaderboard read API. | Python 3.12, FastAPI, Uvicorn, Tortoise ORM, SQLite/Postgres |
| **Web Portal** | `web/portal` | Static benchmark/leaderboard website (no build system). | Vanilla HTML/JS/CSS |

**Supporting dirs:** `docs/` (dev plan, design), `personas/` (audience targeting), `brand/`
(competitive research), `infra/k3s/` (Kubernetes manifests), `scripts/`, `eval_scripts/`.

**Single config source:** `apps/server/sf.json` enables/disables plugins and is read by both the
Electron desktop app and the Python server.

### Data flow
Desktop (Electron) → spawns → Server (FastAPI plugins) → either intercepts CLI traffic or dispatches
to Model APIs directly, or routes through → AIGateway (LiteLLM) → upstream providers. Eval results
persist via `eval-runs` + Scoreboard.

---

## 2. Server Plugins (`apps/server/src/screamingface/plugins/`)

**Architecture.** Three extension systems: **HookRegistry** (priority signal/event bus),
**ClassRegistry** (Odoo-style `_inherit` mixins resolved into final classes), **RouteRegistry**
(dynamic FastAPI router add/remove). Every plugin subclasses `screamingface.plugin.Plugin` and
implements `setup()`; declares `depends`, `conflicts`, `backend_call_paths`, `settings_class`.
Plugin families share base classes: `FrontendPluginBase`, `BackendApiPluginBase`,
`AigwBackendApiPluginBase`.

### Infrastructure / base (no product behavior of their own)
- **llm-base** — Shared ABCs/types for LLM providers (CoreMessage, Backend, AuthStrategy, Adapter, CredentialStore); credential mgmt + status routes.
- **frontend-base** — Shared tracing/redaction helpers + `FrontendPluginBase`/`FrontendSettingsBase` for every `*_frontend` proxy.
- **backend-api-base** — Shared wire-format models (RunRequest/Response, BackendProfile, FileInput) + `BackendApiPluginBase` for every `*_backend_api`.
- **aigw-base** — Base classes + config resolution for `aigw_*_backend` plugins; injects gateway auth-profile enums.
- **state** — Tortoise/SQLite lifecycle core; other plugins `register_models()` against it.
- **data-store** — In-memory KV store exposing `/data` URLs for url4 context resolution.
- **tracing** — Local observability (OpenTelemetry + auto-launched Phoenix UI), FastAPI auto-instrumentation.
- **url4-executor** — The url4 protocol engine: parse, resolve, dispatch backend calls.
- **url4-specs** — Named, shareable url4 expression library (settings-only, no routes).
- **plugin-audit** — CLI `sf plugin-audit deps`; verifies cross-plugin imports match declared `depends`.

### Provider plugins
Each provider has a transparent frontend proxy plus a backend; the gateway-routed variant is
mutually exclusive with the direct-API one.

| Provider | Frontend (transparent proxy) | Direct backend | Gateway-routed backend |
|----------|------------------------------|----------------|------------------------|
| **Claude** | `claude-frontend` (:9101 → api.anthropic.com) | `claude-backend-api` (`/claude/*`, OAuth from Claude Code creds) | `aigw-claude-backend` |
| **Codex/OpenAI** | `codex-frontend` (:9102 → api.openai.com) | `codex-backend-api` (`/codex/*`, token from `~/.codex/auth.json`) | `aigw-codex-backend` |
| **Gemini/Google** | `gemini-frontend` (:9103 → generativelanguage.googleapis.com) | `gemini-backend-api` (`/gemini/*`, model fallback + 429 handling) | `aigw-gemini-backend` |
| **Ollama/local** | `ollama-frontend` (:9104 → localhost:11434) | `ollama-backend-api` (`/ollama/*`, `/api/chat`) | — |

### Interception (at most one active — mutually exclusive)
- **claude-intercept** — DNS/SSL redirect via /etc/hosts + pfctl + mkcert (needs root).
- **claude-env-intercept** — Zero-sudo alternative; redirects via `ANTHROPIC_BASE_URL` in shell profiles/launchctl.
- **mitmproxy-intercept** — Transparent capture via mitmproxy `--mode local` (needs sudo); auto-discovers frontend domains.

### Gateway integration / execution / eval
- **aigw-runner** — Spawns the aigateway uvicorn subprocess (:9105), runs migrations, health-checks, graceful shutdown.
- **aigw-callback** — Bridges local OAuth callbacks to a hosted AIGateway when `aigw-base.mode="external"`.
- **python-runner** — Executes Python scripts referenced by url4 (`/python()!intent`), sandboxed via asyncio subprocess; wires into eval-runs.
- **eval-runs** — Persists eval/benchmark runs (EvalRun/EvalQuestion models) via hooks (run.started/finished/failed, question.checked).

### Empty / deprecated
- **claude-backend** — empty; superseded by `claude-backend-api`.
- **session-service** — empty stub.

---

## 3. AIGateway Plugins (`apps/aigateway/src/aigateway/plugins/`)

**Architecture.** Each direct subpackage of `aigateway.plugins` with a `plugin.py` exposing a
module-level `PLUGIN = ProviderPluginBase()` is auto-discovered (`core/loader.py`) and registered in
`ProviderRegistry` keyed by `custom_llm_provider`. Plugins own: model contributions to the LiteLLM
Router, OAuth flows, credential read/refresh (`OAuthStrategy` / `BaseOAuthStrategy` with locking +
60s proactive refresh), request/response shaping, and profile metadata. Credentials persist via
**ORMStore → Tortoise** (`credential_blob` table; SQLite local, Postgres prod — no OS keychain).
Profiles are tracked in a `ProfileIndex` blob; OAuth connections are a first-class resource at
`/v1/oauth/connections`.

| Plugin | Provider ID | OAuth | Stream | Chatless | Notable behavior |
|--------|-------------|-------|--------|----------|------------------|
| **anthropic_provider** | `anthropic` | claude.com | Yes | No | Claude Code billing-header fingerprint; bootstraps profiles from local Claude Code keychain; filters `reasoning_effort` |
| **codex_provider** | `codex` | openai.com | No | Yes | Loopback redirect ports; parses JWT id_token for account/email; maps `reasoning_effort` → `{reasoning:{effort}}` |
| **gemini_provider** | `gemini-cli` (cred svc `gemini`) | accounts.google.com | No | Yes | Per-profile session cache; sanitizes inbound auth headers; userinfo fallback for identity; honors Retry-After |
| **ollama_provider** | `ollama` | none | Yes | Yes | Dynamic model discovery via `/api/tags`; loopback-only unless `AIGW_OLLAMA_ALLOW_REMOTE=1`; no credential storage |

**Core supporting infra:** `profile_index` / `profile_models` (per-account profiles + defaults),
`oauth/` (connections CRUD, PKCE, token service), `routes/chat.py` (resolve plugin → fetch OAuth
header → merge defaults → `prepare_chat_body` → dispatch → 401 invalidate → retry),
`concurrency.py` (per-provider semaphores), `retry.py` (exponential backoff + Retry-After).
