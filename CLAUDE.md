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

## AI SDLC — MANDATORY

Full process: `task-management` skill (work items) + `sdlc-*` skills (per-stack loop) +
cards `.claude/task-board.local.md` / `.claude/sdlc.local.md`. These rules always hold:

0. **95% confidence gate — TOP RULE.** Never write, assert, or implement anything you are
   not ≥95% confident is both correct AND wanted. Below 95% → STOP and ask first. Applies
   to every rule below and every artifact: code, work items, docs, diagrams.
1. **Work item first.** All work starts as a Linear issue (`OME-N`) in the Engineering
   team, attached to the **😱 ScreamingFace V1** project, carrying its labels (workstream
   from the `Epic` group when it belongs to one; `app/*`/`pkg/*` or `repo` for landing;
   one `who-acts`; one `actor` — agentic|human, mandatory) plus a mirror
   `docs/tasks/YYYY-MM-DD-<name>.md`. At finish, close status in BOTH Linear and the mirror.
2. **Work ledger.** Every finished unit has `docs/work/YYYY-MM-DD-<ticket-id>-<desc>.md`
   (created at work start from `docs/work/TEMPLATE.md`, outcome filled at finish — see the
   sdlc skills).
3. **Spec before plan, plan before code.** A `docs/spec/` artifact is required before
   planning; a `docs/plan/` artifact before implementation. Produce them via
   `superpowers:brainstorming` → `superpowers:writing-plans` (or equivalent); local scratch
   drafts go to gitignored `.docs/`. Reach ≥95% confidence before proposing a plan/spec,
   and never start implementation until the user explicitly approves it in plain words.
4. **Diagrams.** Propose the diagramming plugin
   (https://github.com/sergio-bershadsky/ai/tree/main/plugins/diagramming) when it's
   absent; assets live in `docs/diagrams/` (SVG source + PNG).
5. **Branches/commits.** Branch `OME-N-<desc>` (e.g. `OME-12-fix-refresh`). Conventional
   commits; body carries `Refs: OME-N`; never `Co-Authored-By`; never commit directly to
   `main` — enforced by branch protection plus the local pre-commit guard
   (`.githooks/pre-commit`).
6. **Asana boundary.** Asana is READ-ONLY product/marketing input (`asana-product` skill).
   Technical work items never go to Asana.
7. **Cross-cutting work.** Touching ≥2 apps/packages → epic with its workstream (`Epic`
   group) label + all affected `app/*`/`pkg/*` labels, one sub-issue per affected
   app/package. Never a single-app filing, never one mega-ticket.
8. **Linear via MCP only.** All Linear operations go through the Linear MCP plugin
   (activate via `/mcp`). API tokens and raw GraphQL are forbidden; operations the MCP
   cannot perform are owner actions in the Linear UI.

### Setup (one-time)

After cloning, activate the shared git hooks:

```sh
git config core.hooksPath .githooks
```

This enables the pre-commit hook that blocks direct commits to `main`.
