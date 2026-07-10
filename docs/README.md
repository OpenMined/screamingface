# docs/ — AI-agentic decision records & SDLC artifacts

This directory is the committed home for decisions and process artifacts produced
by/with AI agents:

- `docs/spec/`     — designs/specs (required before planning)
- `docs/plan/`     — implementation plans (required before implementation)
- `docs/diagrams/` — diagram assets (SVG source + PNG)
- `docs/tasks/`    — work-item mirrors (`YYYY-MM-DD-<name>.md`, frontmatter; Linear is authority)
- `docs/work/`     — work ledgers (`YYYY-MM-DD-<ticket-id>-<desc>.md`, created at work start; copy `TEMPLATE.md`)

Process: the `task-management` + `sdlc-*` skills, the cards in `.claude/`, and CLAUDE.md "AI SDLC".
Local scratch drafts that shouldn't be committed go to `.docs/` (gitignored).

The previous `docs/` tree (architecture, setup, glossary, superpowers plans)
was removed in the July 2026 re-foundation — it described the deprecated
desktop app and plugin server. It remains readable at the git tag
`legacy-monorepo-2026-07-08`.
