# Project Context

## The Project
An AI ensemble system combining Claude Code, Gemini CLI, Codex, and Ollama to beat SOTA benchmarks. Users install it locally, it routes coding CLI prompts through the best available models, and they can share AI credits with friends. Built by OpenMined.

## Monorepo Structure

Polyglot monorepo: each component is self-contained (own toolchain, lockfile, CI lane, release lane) and may be any stack (Python / Go / JS / TS).

- `apps/` — independently deployable services & apps:
  - `apps/server` — FastAPI localhost server + plugin system (Python, uv). CLI: `sf`.
  - `apps/aigateway` — LiteLLM-based unified AI gateway (Python, uv).
  - `apps/scoreboard` — benchmark scoreboard service (Python, uv).
  - `apps/desktop` — Electron desktop app / control plane (TypeScript, npm).
- `packages/` — shared libraries consumed by ≥2 components, **not** independently deployed (any stack; none exist yet — convention reserved to avoid cross-app coupling).
- `web/` — static marketing site (`web/public/` → GitHub Pages) + leaderboard portal (`web/portal/`); no build toolchain.
- `docs/` — architecture, setup, glossary, process docs, and superpowers plans/specs.
- `infra/` — k3s / Kubernetes manifests. `scripts/`, `eval_scripts/` — repo-level tooling. `personas/` — audience & design personas.

**Working across components** — which app to touch, which CI runs, who reviews, the branch/PR/release lane, and how to add a new component in any stack: see the **`working-in-this-repo`** skill (`.claude/skills/working-in-this-repo/`) and the canonical process doc `docs/team-development.md`.

## The Four App Screens
- **Settings** — configure which AI models are in the ensemble
- **Spend** — view/manage token usage and cost across all models
- **Eval Studio** — run benchmark evals against available models, view results
- **Cache/Log** — browse, search, filter cached AI queries; delete entries; view stats

## Team
- **Bennett** — design lead
- **Sergey** — Electron packaging, local microservices (localhost backends)
- **Kevin** — app backend, url4 protocol
- **Trask** — product owner

## Tech Stack
- React + Vite
- Tailwind CSS
- Electron (desktop app)
- shadcn/ui (component library)
- Recharts / Chart.js / D3 (data visualization)
- TypeScript (possibly)
- Next.js (possibly, for cloud webapp)

## Key Concepts
- **url4** — custom protocol; encodes AI task chains as human-readable URLs (DAG-based)
- **Enclave** — secure cloud server running model runners and cache
- **Ensemble** — combining multiple AI models for better results than any single model
- **SOTA** — State of the Art benchmark accuracy scores we're trying to beat
- **Localhost microservices** — small FastAPI backends running on the user's machine

## Architecture Principles

These are **mandatory** for all code in this repo. PRs that violate them must be fixed before merge.

- **DRY** — Don't Repeat Yourself. Extract shared logic; never copy-paste implementations across modules.
- **SOLID** — all five principles apply, but most load-bearing here:
  - **S**ingle Responsibility — one reason to change per module/class.
  - **O**pen/Closed — extend via new plugins, not by editing core.
  - **L**iskov Substitution — plugin implementations must be interchangeable behind their interface.
  - **I**nterface Segregation — many small interfaces beat one fat one.
  - **D**ependency Inversion — high-level (core) depends on abstractions; low-level (plugins) implement them.
- **Dependency direction (Clean Architecture / Hexagonal / Ports & Adapters):**
  - **Core MUST NOT import from plugins/adapters.** Plugins import from core, never the reverse.
  - Core defines interfaces ("ports"); plugins/adapters implement them.
  - Model runners (Claude, Gemini, Codex, Ollama), transports (HTTP, IPC), storage, and UI are **adapters** — they sit outside the core.
  - Discovery/wiring of plugins happens via a registry, not via direct imports in core.
- **AIGateway credential storage:** `apps/aigateway` uses ORMStore through Tortoise (`credential_blobs`): SQLite locally, Postgres in hosted/prod. No OS keychain/libsecret/Credential Manager usage in AIGateway.

## Deprecated / Unmaintained Plugins

The three legacy **claude-CLI traffic-intercept** plugins below are **no longer maintained** and are **not part of the pipeline we are building**. None of them is in the active `apps/server/sf.json` plugins list.

- `apps/server/src/screamingface/plugins/claude_env_intercept` (`claude-env-intercept`)
- `apps/server/src/screamingface/plugins/mitmproxy_intercept` (`mitmproxy-intercept`)
- `apps/server/src/screamingface/plugins/claude_intercept` (`claude-intercept`)

**Rules (mandatory):**

- **Never add new features to these plugins.** Do not extend them, do not route new functionality through them. New gateway behavior belongs in the active pipeline — the frontend plugins (e.g. `claude_frontend` / `frontend_base`) that serve `/v1/messages`, not in an intercept shim.
- **Do not treat them as a reference for "how the gateway works."** They are legacy CLI-redirection strategies, separate from the live request/response path.
- **Touch them only to deprecate, delete, or keep them compiling** (e.g. shared-helper signature changes). Bug-fix-only otherwise.
- If a task seems to require one of these, stop and confirm with the user first — it almost certainly belongs elsewhere.

## Personas

This project uses a persona system to guide copy, design, positioning, and feature decisions. **Before doing any work that involves messaging, tone, design choices, or audience targeting**, consult the persona weighting guide.

- **Weighting guide:** `personas/weighting-guide.md` — start here. Maps every work context (homepage, /why page, app screens, etc.) to the right audience personas.
- **Audience personas:** `personas/persona-audience-1.md` (developers, P0), `personas/persona-audience-2.md` (thought leaders/policy, P1), `personas/openmined-core-team.md` (internal, pre-launch)
- **Research cohorts:** `personas/abc-citations/` (thesis citation network — peers & validators) and `personas/time100-ai/` (influential AI figures — Audience 2 adjacent)

If a task involves copy, design, or positioning and you're unsure which audience applies, ask before proceeding.

## Git Workflow

### Commit Rules

- **Before every commit**, ask the user for the associated Asana ticket.
- If no ticket exists, create one via the `/asana` command (default project `1213628819033917`). The `SF` custom field (GID `1213703035415126`) is **auto-assigned** by an Asana rule — do **not** set it manually. Read the assigned `SF-N` back from the created task (poll its `custom_fields`) and use it for the branch name.
- **Branch naming:** `SF-{n}-{description}` (e.g. `SF-22-fix-auth-bug`). Derive from the ticket's SF field value.
- If on the wrong branch, ask to create/switch to the correct one before committing.
- **Never commit directly to `main`** — enforced by branch protection (authoritative) plus a local pre-commit guard (`.githooks/pre-commit`, or the husky hook once desktop deps are installed).
- Include the Asana task permalink in the commit message body.

## Planning Tickets

When the user asks to **plan a ticket** (or any non-trivial task):

- **Always use the agentic superpowers team for planning.** Use `superpowers:brainstorming` first, then `superpowers:writing-plans` (or the equivalent `write-plan` / `brainstorm` skills). Dispatch parallel agents (`superpowers:dispatching-parallel-agents`) for independent research as needed.
- **Write output to disk** in this project:
  - **Plans** → `/Users/sergey/work/openmind/screamingface/docs/superpowers/plans/`
  - **Specs** → `/Users/sergey/work/openmind/screamingface/docs/superpowers/specs/`
- **Reach ≥95% confidence before proposing the plan/spec for review.** Iterate — re-read source files, dispatch more research agents, ask the user targeted questions — until you can honestly claim ≥95% confidence in the plan's correctness, completeness, and feasibility. State the confidence level explicitly when presenting.
- **Never switch to implementation until the user explicitly approves the plan.** Writing the plan to disk and presenting it is the end of the planning phase. Do not start editing code, creating branches, or executing the plan until the user says so in plain words. Implicit cues ("looks good", "thanks") are not approval — wait for an explicit go-ahead.

### Setup (one-time)

After cloning, activate the shared git hooks:

```sh
git config core.hooksPath .githooks
```

This enables the pre-commit hook that blocks direct commits to `main`. Note: if you develop the desktop app, `npm install` in `apps/desktop` makes husky take over `core.hooksPath` for the whole repo — the husky hook carries the same `main` guard plus the lint/format/type gates.
