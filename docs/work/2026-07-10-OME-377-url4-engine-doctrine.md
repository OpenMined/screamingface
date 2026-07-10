---
ticket: OME-377
stack: repo
status: in_progress   # planned | in_progress | done | blocked
started: 2026-07-10
finished:
---

# OME-377 — url4-engine execution & telemetry doctrine (skill + diagrams)

## Intent

Capture the agreed mental model of the url4-engine AI-ensemble **execution & telemetry
protocol** as a reusable, discoverable doctrine skill plus two diagrams, so future design
and review work starts from one shared model. Design-stage only — the engine is
legacy-tag-only and revives as `pkg/url4-python-sdk`; there is no spec yet.

## Planned changes

- `.claude/skills/url4-engine/SKILL.md` — PROPOSED doctrine: invariant groups **N** (node
  model), **T** (transport modes), **O** (observability — logs / OTel `gen_ai.*` spans /
  separate `cost.usage` event), **F** (hybrid forwarding: relay ↑ + Enclave store), a
  Red-flags STOP table, and both diagrams embedded.
- `docs/diagrams/ensemble-node-architecture.{svg,png}` — node tree + telemetry planes.
- `docs/diagrams/ensemble-node-sequence.{svg,png}` — one 4-level nested run.
- `.claude/README.md` — skills-index row for `url4-engine`.
- Generator kept in scratchpad (`gen_diagrams.py`) — decide whether to land it under
  `docs/diagrams/src/` for regeneration.

## Test plan (docs unit — verification, not TDD)

- SVGs render cleanly via `rsvg-convert -w 1700 <name>.svg -o /tmp/out.png` → visual check.
- Paired PNGs rendered `rsvg-convert -z 1.5 <name>.svg -o <name>.png`.
- Skill auto-discovered (appears in the Skill tool's available list).
- Embedded diagram relative paths (`../../../docs/diagrams/…`) resolve to real files.

## Acceptance

- Skill discoverable; both diagrams embed correctly.
- Committed with `Refs: OME-377`.
- Owner confirms the design-stage framing and the **F4** GET-leaf telemetry-return direction.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** skill + 2 diagrams (svg+png) + README row + this ledger + docs/tasks
  mirror. Verified: rsvg render OK, skill discoverable, image paths resolve.
- **Commits:** _pending — not yet committed._
- **Gates:** docs unit — no run_gates; visual render + path-resolution checks passed.
- **Deviations:** filed retroactively (artifacts produced before the work item existed —
  process gap, corrected via a `UserPromptSubmit` SDLC-gate hook). Two open follow-ups:
  generator landing decision; **F4** owner decision (STOP `needs-owner`).
