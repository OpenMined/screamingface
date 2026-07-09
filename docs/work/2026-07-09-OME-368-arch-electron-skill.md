---
ticket: OME-368
stack: repo
status: done
started: 2026-07-09
finished: 2026-07-09
---

# OME-368 — arch-electron skill: Electron architecture doctrine

## Intent

Capture the Electron architecture doctrine — VS Code-style dynamic extension platform,
core-owned process supervision of third-party binaries, DEBUG-gated all-process log view —
as a binding repo skill, so the new desktop app (and any future Electron surface) is
designed against locked invariants instead of re-derived knowledge. Companion to
`sdlc-electron`, which keeps the per-iteration loop and the build-time security checklist.

## Planned changes

- `.claude/skills/arch-electron/SKILL.md` (new — the doctrine)
- `.claude/skills/sdlc-electron/SKILL.md` — one cross-reference line, OUTSIDE the
  SHARED-LOOP regions (parity must stay green)
- `.claude/README.md` — skills table row
- `docs/tasks/2026-07-09-arch-electron-skill.md` (mirror)
- this ledger

## Test plan

Doc-only unit (owner waived rule 3 — fast-track locked in-session 2026-07-09). Verification:

- `uv run .claude/scripts/check_loop_parity.py` → LOOP PARITY OK after the sdlc-electron edit
- ASCII topology diagram alignment verified programmatically (border-column assertion)
- Consistency read-through vs `sdlc-electron` + CLAUDE.md hexagonal mandate (no
  contradictions, no duplicated security checklist)

## Acceptance

- Skill exists and is normative (MUST-level invariants, each with a rationale)
- Owner brainstorm decisions encoded: ProcessSupervisor is core (not an extension);
  process-log view is core, registered only in DEBUG mode
- README row present; parity green; PR referencing `OME-368`

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `docs/diagrams/electron-extension-architecture.{svg,png}`
  and `docs/diagrams/electron-extension-load-sequence.{svg,png}` (owner requested diagrams
  mid-unit) and the skill's pointer to them.
- **Commits:** single commit on the OME-368 PR (squash sha recorded in the Linear close
  comment at merge).
- **Gates:** `check_loop_parity.py` → LOOP PARITY OK (sdlc-electron edited outside the
  SHARED-LOOP regions only); diagram alignment/collisions verified programmatically + PNG
  visual pass (one fix round: arrows moved clear of cluster title chips); no app code
  touched → app gate runners not applicable.
- **Deviations:** diagrams added mid-unit by owner request; diagramming skill's
  HTML-output contract overridden by the repo SVG+PNG rule (standing owner feedback);
  ProcessSupervisor-is-core and DEBUG-gated log view baked from in-session owner brainstorm
  — flagged in the PR for veto; mirror/ledger marked done at PR time (Linear closes at
  merge) to avoid a post-merge close-out commit like OME-358's; owner scoped mid-review:
  the concrete extension-API surface is a SEPARATE future skill — X4 binds mechanism only
  (scope-boundary note added to the skill); critical-review round (owner-approved): X10
  host-supervision rule, X1 manifest forward-compat, T1 webview-network nuance, topology
  diagram protocol label aligned (JSON-RPC → RPC).
