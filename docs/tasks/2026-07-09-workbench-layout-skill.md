---
id: OME-370
linear_url: https://linear.app/openmined/issue/OME-370/arch-electron-layout-skill-workbench-layout-doctrine-shell-regions
status: done
type: task
priority: P2
labels: [repo, Desktop App, agentic, autonomous]
created: 2026-07-09
closed: 2026-07-09
---

Binding workbench layout doctrine (`.claude/skills/arch-electron-layout/`): core-owned
shell regions (title/activity bar, sidebar, main area, panel, status bar), views in
containers docked into slots, manifest placement = hint / user override wins and persists,
no focus stealing, core-owned per-window layout tree, document-centric main area (L7 veto
flag), no cross-window docking in v1 (L8 veto flag). Companion layer between arch-electron
and screamingface-design. Fast-track (rule 3 waived, same pattern as OME-368); stacked PR
on the OME-368 branch. Initial layout (v1) based on the Ensemble Studio design
(irinambejan.github.io/model-ensemble-studio): single rich sidebar, no activity bar,
five main-area view archetypes, ensemble document with Compose|Runs tabs, panel/status
bar hidden in v1.
