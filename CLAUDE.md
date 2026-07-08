# Project Context

## The Project
An AI ensemble system combining Claude Code, Gemini CLI, Codex, and Ollama to beat SOTA benchmarks. Users install it locally, it routes coding CLI prompts through the best available models, and they can share AI credits with friends. Built by OpenMined.

## Repo Re-foundation (July 2026)

The legacy `apps/desktop` (Electron control plane) and `apps/server` (FastAPI plugin server, `sf` CLI) were **deprecated and removed**. The full pre-teardown tree — including the url4 engine, marketing site, infra manifests, and personas — is preserved at the git tag **`legacy-monorepo-2026-07-08`**. Do not resurrect code from those trees into the live repo; treat the tag as read-only reference.

Being built next, as **separate packages with separate lifecycles and CI lanes** (names pending team lock-down, prefix `screamingface-*` or `sf-*`):

- **Desktop app** — pure Electron (no bundled Python); detects and launches the server CLI if installed; brew-distributed, signed macOS/Windows/Linux builds.
- **Server CLI** — Python (Typer), installable from PyPI.
- **`packages/url4-python-sdk`** — url4 SDK, published as `url4` on PyPI (extraction source: the url4 executor under the legacy tag).

## Monorepo Structure

Polyglot monorepo: each component is self-contained (own toolchain, lockfile, CI lane, release lane).

- `apps/aigateway` — LiteLLM-based unified AI gateway (Python, uv). Provider OAuth, encrypted credential store.
- `apps/scoreboard` — benchmark scoreboard service + demo portal (Python, uv). Portal assets and public eval artifacts live inside the app (`portal/`, `artifacts/`).
- `packages/` — shared libraries consumed by ≥2 components, **not** independently deployed (none exist yet; `url4-python-sdk` lands here first).
- `docs/` — AI-agentic decision records: plans, specs, and future decision docs (being extended). Local scratch drafts go to gitignored `.docs/`.

**Working across components** — which app to touch, which CI runs, who reviews, the branch/PR/release lane, and how to add a new component in any stack: see the **`working-in-this-repo`** skill (`.claude/skills/working-in-this-repo/`).

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

## Key Concepts
- **url4** — custom protocol; encodes AI task chains as human-readable URLs (DAG-based)
- **Enclave** — secure cloud server running model runners and cache
- **Ensemble** — combining multiple AI models for better results than any single model
- **SOTA** — State of the Art benchmark accuracy scores we're trying to beat

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
  - Discovery/wiring of plugins happens via a registry, not via direct imports in core.
- **AIGateway credential storage:** `apps/aigateway` uses ORMStore through Tortoise (`credential_blobs`): SQLite locally, Postgres in hosted/prod. No OS keychain/libsecret/Credential Manager usage in AIGateway.

## Git Workflow

### Commit Rules

- **Before every commit**, ask the user for the associated Asana ticket.
- If no ticket exists, create one via the `/asana` command (default project `1213628819033917`). The `SF` custom field (GID `1213703035415126`) is **auto-assigned** by an Asana rule — do **not** set it manually. Read the assigned `SF-N` back from the created task (poll its `custom_fields`) and use it for the branch name.
- **Branch naming:** `SF-{n}-{description}` (e.g. `SF-22-fix-auth-bug`). Derive from the ticket's SF field value.
- If on the wrong branch, ask to create/switch to the correct one before committing.
- **Never commit directly to `main`** — enforced by branch protection (authoritative) plus the local pre-commit guard (`.githooks/pre-commit`).
- Include the Asana task permalink in the commit message body.

## Planning Tickets

When the user asks to **plan a ticket** (or any non-trivial task):

- **Always use the agentic superpowers team for planning.** Use `superpowers:brainstorming` first, then `superpowers:writing-plans` (or the equivalent `write-plan` / `brainstorm` skills). Dispatch parallel agents (`superpowers:dispatching-parallel-agents`) for independent research as needed.
- **Write output to disk** in this project:
  - **Plans** → `docs/plan/`
  - **Specs** → `docs/spec/`
  - Local scratch drafts (not for commit) → `.docs/` (gitignored)
- **Reach ≥95% confidence before proposing the plan/spec for review.** Iterate — re-read source files, dispatch more research agents, ask the user targeted questions — until you can honestly claim ≥95% confidence in the plan's correctness, completeness, and feasibility. State the confidence level explicitly when presenting.
- **Never switch to implementation until the user explicitly approves the plan.** Writing the plan to disk and presenting it is the end of the planning phase. Do not start editing code, creating branches, or executing the plan until the user says so in plain words. Implicit cues ("looks good", "thanks") are not approval — wait for an explicit go-ahead.

### Setup (one-time)

After cloning, activate the shared git hooks:

```sh
git config core.hooksPath .githooks
```

This enables the pre-commit hook that blocks direct commits to `main`.
