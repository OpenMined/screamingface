---
ticket: OME-378
stack: repo
status: in_progress   # planned | in_progress | done | blocked
started: 2026-07-10
finished:
---

# OME-378 — SDLC-gate UserPromptSubmit hook (enforce work-item-first)

## Intent

CLAUDE.md already mandates work-item-first, but as long-context advisory text it lost to the
immediate task framing on OME-377 (artifacts produced before a work item existed). Advisory
rules don't self-enforce; the harness runs hooks. Add a repo-wide `UserPromptSubmit` hook
that re-injects a compact SDLC gate every prompt so the rule stays salient.

## Planned changes

- `.claude/hooks/sdlc-gate.py` — prints the gate as JSON `hookSpecificOutput.additionalContext`
  (non-blocking): file OME-N + docs/work ledger BEFORE writing tracked paths
  (`docs/`, `.claude/`, `apps/`, `packages/`, `web/`); invoke working-in-this-repo +
  task-management (+ sdlc-* for code); order spec→plan→code; never commit to main; scratchpad
  + plan file exempt.
- `.claude/settings.json` — add `hooks.UserPromptSubmit` → runs that script (merged with the
  existing `permissions` block, not replacing it).

## Test plan (config unit — verification, not TDD)

- `echo '{}' | python3 .claude/hooks/sdlc-gate.py | jq -e .hookSpecificOutput.additionalContext` → valid JSON. ✅
- `jq -e . .claude/settings.json` → parses. ✅
- `jq -e '.hooks.UserPromptSubmit[].hooks[] | select(.type=="command") | .command'` → wired. ✅
- `.permissions.allow` still 11 entries (merge, not overwrite). ✅
- Live-fire: UserPromptSubmit fires outside this turn — confirm on the next prompt; `/hooks`
  reload if the settings watcher didn't pick up the new hook.

## Acceptance

- Hook fires on prompt submit; gate text appears; nothing blocks.
- `permissions` preserved.
- Committed with `Refs: OME-378`.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `.claude/hooks/sdlc-gate.py`, `.claude/settings.json` (+ this ledger +
  docs/tasks mirror). Static checks 1–4 passed; live-fire pending next prompt.
- **Commits:** _pending — not yet committed._
- **Gates:** config unit — no run_gates; jq/pipe-test validation passed.
- **Deviations:** PreToolUse write-guard considered and deferred (reminder-only, per owner).
