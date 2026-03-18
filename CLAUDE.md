# Project Context

## The Project
An AI ensemble system combining Claude Code, Gemini CLI, Codex, and Ollama to beat SOTA benchmarks. Users install it locally, it routes coding CLI prompts through the best available models, and they can share AI credits with friends. Built by OpenMined.

## Monorepo Structure
- `web/` — static marketing website (leaderboard chart, install flow)
- `app/` — local Electron desktop app
- `cloud/` — cloud webapp (Gates/token sharing UI, leaderboards)
- `personas/` — audience personas, research cohorts, and weighting guide
- `brand/` — brand research (competitive landscape, design, SEO)
- `docs/` — development plan, design guidance, internal docs
  - **`docs/😱 Development Plan.docx`** — the original product development plan. Key reference for scope, phasing, and product decisions. A plain-text version is at `docs/devplan.txt`.

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

## Personas

This project uses a persona system to guide copy, design, positioning, and feature decisions. **Before doing any work that involves messaging, tone, design choices, or audience targeting**, consult the persona weighting guide.

- **Weighting guide:** `personas/weighting-guide.md` — start here. Maps every work context (homepage, /why page, app screens, etc.) to the right audience personas.
- **Audience personas:** `personas/persona-audience-1.md` (developers, P0), `personas/persona-audience-2.md` (thought leaders/policy, P1), `personas/openmined-core-team.md` (internal, pre-launch)
- **Research cohorts:** `personas/abc-citations/` (thesis citation network — peers & validators) and `personas/time100-ai/` (influential AI figures — Audience 2 adjacent)

If a task involves copy, design, or positioning and you're unsure which audience applies, ask before proceeding.

## Git Workflow

### Commit Rules

- **Before every commit**, ask the user for the associated Asana ticket.
- If no ticket exists, create one via the `/asana` command (default project `1213628819033917`), and set its `SF` custom field (GID `1213702745960748`) to the next sequential number.
  - To find the next SF number: query project tasks with `opt_fields=custom_fields.display_value`, find the highest existing `SF-N` value, and use `N+1`.
- **Branch naming:** `SF-{n}-{description}` (e.g. `SF-22-fix-auth-bug`). Derive from the ticket's SF field value.
- If on the wrong branch, ask to create/switch to the correct one before committing.
- **Never commit directly to `main`** — the `.githooks/pre-commit` hook enforces this.
- Include the Asana task permalink in the commit message body.

### Setup (one-time)

After cloning, activate the shared git hooks:

```sh
git config core.hooksPath .githooks
```

This enables the pre-commit hook that blocks direct commits to `main`.
