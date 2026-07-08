---
ticket: OME-358
stack: repo
status: in_progress
started: 2026-07-08
finished:
---

# OME-358 — Adopt the Linear AI SDLC (skills, cards, agents, scripts, CI)

## Intent

Replace the Asana/SF-N workflow with the Linear-based AI SDLC: Linear (MCP-only) as the
system of record for work items under the 😱 ScreamingFace V1 project, mandatory repo
artifacts (tasks mirrors, work ledgers, spec/plan gates, diagrams), rigid per-stack SDLC
skills, and supporting agents/scripts/CI — so agentic and human work runs one disciplined
loop.

## Planned changes

- `.claude/task-board.local.md`, `.claude/sdlc.local.md` (cards)
- `docs/tasks/`, `docs/work/` (+ `TEMPLATE.md`), this mirror + ledger; `docs/README.md`
- `CLAUDE.md` — AI SDLC rules 0–7 replace the Asana git workflow
- `.claude/skills/asana-product/`, `.claude/skills/task-management/`,
  `.claude/skills/sdlc-python/`, `.claude/skills/sdlc-electron/`
- `.claude/agents/sdlc-unit-executor.md`, `.claude/agents/ticket-filer.md`
- `.claude/scripts/run_gates.py`, `.claude/scripts/check_loop_parity.py`
- `.github/workflows/repo-checks.yml`
- `.claude/skills/working-in-this-repo/SKILL.md` (Linear routing)

## Test plan

- `check_loop_parity.py` → LOOP PARITY OK (sdlc-python ↔ sdlc-electron SHARED-LOOP regions)
- `run_gates.py aigateway` and `run_gates.py scoreboard` → ALL GATES GREEN
- Stale-reference grep (legacy Asana-workflow strings, old paths) → zero hits outside spec/plan
- Linear round-trip already exercised live: labels, epic OME-358 + sub-issues, state moves

## Acceptance

- All planned files exist and are internally consistent (cards ↔ skills ↔ CLAUDE.md)
- Gates + parity green; PR open referencing OME-358; sub-issues closable with the card's
  close template

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus: CONTRIBUTING.md git-workflow section (Linear flow —
  found by the sweep), docs/README.md, docs/spec + docs/plan updates (taxonomy lock,
  sdlc-electron rename, MCP-only transport).
- **Commits:** 75f5254 (taxonomy lock), 51c62af (cards), faf315e (docs tree),
  2313367 (CLAUDE.md rules), 6ccbd19 (skill set), 132f79c (agents/scripts/CI/routing),
  + this verification commit.
- **Gates:** run_gates.py aigateway → ALL GATES GREEN (ruff, format, pyright,
  no-enterprise guard, pytest-cov≥80); run_gates.py scoreboard → ALL GATES GREEN;
  check_loop_parity.py → LOOP PARITY OK.
- **Deviations:** work-ledger TEMPLATE adapted from the sdlc plugin (Linear ticket field +
  D8 frontmatter instead of repo#N); sdlc-react transformed to sdlc-electron (owner
  decision mid-implementation); STOPs use existing `blocked ⛔` label instead of a new
  `blocked` label; taxonomy aligned with the pre-existing Epic-group workstreams instead
  of a `com/*` axis.
