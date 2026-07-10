---
ticket: OME-370
stack: repo
status: done
started: 2026-07-09
finished: 2026-07-09
---

# OME-370 — arch-electron-layout skill: workbench layout doctrine

## Intent

Bind the workbench layout architecture for the ScreamingFace desktop app — the structural
layer between `arch-electron` (where extension code runs) and `screamingface-design`
(visual brand law): core-owned shell regions, view containers/slots, user-override
persistence, focus discipline. Requested by owner immediately after the arch-electron
critical review ("and after layout skill … corresponding branch and PR for review").

## Planned changes

- `.claude/skills/arch-electron-layout/SKILL.md` (new — the doctrine)
- `.claude/skills/arch-electron/SKILL.md` — one cross-reference line
- `.claude/README.md` — skills table row
- `docs/diagrams/electron-workbench-layout.{svg,png}` (regions + view landing path)
- `docs/tasks/2026-07-09-workbench-layout-skill.md` (mirror)
- this ledger

## Test plan

Doc-only unit (rule 3 waived — same fast-track pattern as OME-368). Verification: ASCII
diagram alignment asserted programmatically; SVG diagram rendered to PNG (rsvg-convert)
and visually checked; consistency read-through vs arch-electron (T/X/D/S rule references
resolve) and screamingface-design boundary; loop-parity CI unaffected (no sdlc-* files
touched — lane may not even trigger).

## Acceptance

- Skill exists and is normative (MUST-level L-rules with rationales)
- Veto flags recorded: L7 (document-centric main area), L8 (no cross-window docking v1)
- Diagram, README row, arch-electron cross-ref present; PR (stacked on
  `OME-368-arch-electron-skill`, retargets to main after #378) references `OME-370`

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned.
- **Commits:** single commit on the OME-370 PR (squash sha recorded in the Linear close
  comment at merge).
- **Gates:** ASCII alignment assertion OK; SVG→PNG rendered and visually verified; no app
  code touched → app gate runners not applicable.
- **Deviations:** stacked branch (base = OME-368 branch) because the skill cross-references
  arch-electron content not yet on main; PR must be retargeted/rebased if #378 squash-merges
  first — noted in the PR body. Mid-review owner request: initial layout re-based on the
  **Ensemble Studio** design (irinambejan.github.io/model-ensemble-studio), researched live
  via Playwright (screenshots → `.docs/ensemble-studio-research/`); consequences: activity
  bar deferred out of v1 (L1 amended), single rich sidebar (brand/nav/MY ENSEMBLES/compute
  card/user), five main-area view archetypes, ensemble document = the L7 document type,
  panel + status bar hidden in v1; ASCII + SVG diagrams reworked.
