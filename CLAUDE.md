# CLAUDE.md — mandatory minimum

ScreamingFace: an open-source AI ensemble toolkit (Claude/Gemini/Codex/Ollama) that beats
single-model SOTA, runs locally, publishes to a public leaderboard. By OpenMined.

**The full guide — skills, agents, cards, process, product context, history:
`.claude/README.md`.** Repo routing: the `working-in-this-repo` skill.

## Monorepo

- `apps/aigateway` — LiteLLM-based AI gateway (Python, uv)
- `apps/scoreboard` — benchmark scoreboard + portal (Python, uv)
- `packages/` — shared libs (reserved; `url4-python-sdk` first)
- Public website lives in the separate `screamingface-web` repo; this monorepo does not
  publish GitHub Pages.
- `docs/` — SDLC artifacts: `spec/ plan/ tasks/ work/ diagrams/` (see `docs/README.md`)
- Legacy (desktop, server, url4 engine): tag `legacy-monorepo-2026-07-08` — read-only,
  never resurrect from it.

## AI SDLC — MANDATORY

Process: `task-management` skill + `sdlc-*` skills + cards `.claude/task-board.local.md` /
`.claude/sdlc.local.md`. Always:

0. **95% confidence gate — TOP RULE.** Below 95% confident it's correct AND wanted →
   STOP and ask. Applies to everything: code, work items, docs, diagrams.
1. **Work item first.** Every unit of work is a Linear issue (`OME-N`, Engineering team,
   😱 ScreamingFace V1 project) with its labels (workstream when applicable;
   `app/*`/`pkg/*` or `repo`; one `who-acts`; one `actor` — agentic|human, mandatory) +
   a mirror in `docs/tasks/`. Close status in BOTH at finish.
2. **Work ledger.** Every unit has `docs/work/YYYY-MM-DD-<ticket-id>-<desc>.md` — created
   at work START from `docs/work/TEMPLATE.md`, outcome filled at finish.
3. **Spec before plan, plan before code.** `docs/spec/` then `docs/plan/` artifacts are
   hard prerequisites (superpowers brainstorming → writing-plans; scratch in gitignored
   `.docs/`). Implementation starts only on explicit approval in plain words.
4. **Diagrams** → `docs/diagrams/` (SVG + PNG); propose the diagramming plugin
   (https://github.com/sergio-bershadsky/ai/tree/main/plugins/diagramming) if absent.
5. **Branches/commits.** `OME-N-<desc>`; conventional commits; body `Refs: OME-N`;
   never `Co-Authored-By`; never commit to `main` (`.githooks/pre-commit` + protection).
6. **Asana is READ-ONLY** product/marketing input (`asana-product` skill). Technical work
   never goes to Asana.
7. **Cross-cutting** (≥2 apps/packages) → epic + one sub-issue per affected app/package.
   Never one mega-ticket.
8. **Linear via MCP only** (`/mcp` to activate). API tokens / raw GraphQL are forbidden;
   MCP-uncovered operations are owner actions in the Linear UI.

## Architecture — MANDATORY

- DRY · SOLID · hexagonal: core defines ports; plugins/adapters implement them; **core
  never imports plugins**; wiring via registry, not direct imports.
- AIGateway credentials: ORMStore/Tortoise `credential_blobs` only (AES-256-GCM via
  SecretStoreMixin); no OS keychain; `AIGATEWAY_SECRET_KEY` never stored or logged.

## Setup (one-time)

```sh
git config core.hooksPath .githooks
```
