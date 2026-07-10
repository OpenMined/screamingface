---
id: OME-378
linear_url: https://linear.app/openmined/issue/OME-378/chorerepo-sdlc-gate-userpromptsubmit-hook-enforce-work-item-first
status: in_progress
type: task
priority: P2
labels: [repo, autonomous, agentic]
created: 2026-07-10
closed:
---

Repo-wide, checked-in `UserPromptSubmit` hook that re-injects a compact SDLC gate every
prompt, so work-item-first stops depending on long-context recall. Change:
`.claude/settings.json` (add `hooks.UserPromptSubmit`, merged with existing `permissions`)
+ `.claude/hooks/sdlc-gate.py` (prints the gate as `additionalContext`; non-blocking).
Motivated by the OME-377 process gap (artifacts produced before a work item existed).
Scope/strength owner-approved: repo-wide + reminder-only (a PreToolUse write-guard was
deferred). Ledger: `docs/work/2026-07-10-OME-378-sdlc-gate-hook.md`.
