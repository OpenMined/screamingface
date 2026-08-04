---
ticket: UNFILED
stack: repo
status: in_progress
started: 2026-08-04
finished:
---

# UNFILED — make worktree-per-unit a mandatory CLAUDE.md rule

## PROCESS DEVIATION

**No Linear issue backs this unit.** The Linear MCP plugin is installed but unauthenticated in
this session; `.claude/task-board.local.md` names it the ONLY permitted transport (API tokens and
raw GraphQL forbidden). This is the third occurrence in this session; the owner previously chose
"proceed and record the deviation" for the identical situation (`OME-743`, since reconciled).

Dangling fields to back-fill once MCP is up:

| field | current |
|---|---|
| ledger `ticket:` / filename | `UNFILED` |
| branch | `claudemd-worktree-branch-rule` (should be `OME-N-<desc>`) |
| `docs/tasks/` mirror | absent |
| commit `Refs:` | absent |

## Intent

Owner instruction: **always use worktrees, branch from `main`, then PR** — as a mandatory rule in
`CLAUDE.md`.

This is not theoretical hygiene. It has already cost this repo real time:

- **2026-08-04, mid-unit collision.** While `OME-743`'s edits sat uncommitted in the shared
  checkout, a concurrent session switched the branch to `OME-738-public-docs-ci-lane`. Git carried
  the uncommitted edits across because they did not conflict, so `OME-743`'s work was briefly
  sitting on an unrelated unit's branch. Nothing was lost, but only because it was noticed.
  Recorded as deviation 4 in `docs/work/2026-08-04-OME-743-aigateway-ui-stack-card-repair.md`.

**Uncommitted work is the only thing a branch switch silently relocates.** A worktree per unit
removes the shared mutable checkout that makes this possible — two sessions cannot switch each
other's branch when each holds its own working directory.

Two existing worktrees (`OME-737`, `OME-744`) already follow the `.claude/worktrees/<branch>`
convention, so the rule codifies established practice rather than inventing it.

## Planned changes

- `CLAUDE.md` — new mandatory rule 5 (worktree per unit, branch from `origin/main`, land via PR);
  existing rules 5→6, 6→7, 7→8, 8→9 renumber.
- `.gitignore` — add `.claude/worktrees/`.

## Why the `.gitignore` change is required, not incidental

`.claude/worktrees/` is currently excluded **only** in `.git/info/exclude`. That file is local to
one clone and is **never cloned or pushed**. So the moment worktrees become mandatory, every fresh
clone would show `.claude/worktrees/` as untracked — and a careless `git add -A` could commit an
entire nested worktree. Mandating the practice without committing the ignore rule would ship a
footgun with the rule that creates it.

## Test plan

No code, so verification is behavioural:

- `git check-ignore -v .claude/worktrees/` resolves to the committed `.gitignore`, not
  `.git/info/exclude`
- `git status --short` in a worktree-containing checkout shows no worktree noise
- this unit is itself performed in a worktree branched from `origin/main` — the rule demonstrates
  itself, and a failure to follow it here would be self-refuting

## Acceptance

- `CLAUDE.md` carries the worktree rule under "AI SDLC — MANDATORY", numbering contiguous
- `.gitignore` ignores `.claude/worktrees/` from a fresh clone
- change landed via PR from a worktree branched off `origin/main`

## Outcome

- **Actual files:** as planned — `CLAUDE.md` (new rule 5, renumber 5→6…8→9) and `.gitignore`.

- **Acceptance, verified:**

  ```
  $ git check-ignore -v .claude/worktrees/
  .gitignore:50:.claude/worktrees/        .claude/worktrees/     ← was .git/info/exclude:11
  ```

  Rule numbering contiguous 0–9. `git status --short` in this worktree-containing checkout shows
  no worktree noise.

- **Gates:** none apply — `.claude/sdlc.local.md` defines no `repo` stack (only `aigateway`,
  `scoreboard`, `url4`, `url4-cloud`, `aigateway-ui`), and this unit touches no stack root.
  `.githooks/pre-commit` ran on commit.

- **Self-demonstrating:** performed in `.claude/worktrees/claudemd-worktree-branch-rule`, branched
  from `origin/main` after `git fetch`, landed via PR. The rule was followed while being written.

## Deviations

1. **Process deviation** — see top. No Linear issue; MCP unauthenticated for the third time this
   session. Branch is descriptive rather than `OME-N-<desc>`, no `docs/tasks/` mirror, and the
   commit carries no `Refs:` line.

2. **`.gitignore` was not in the owner's literal request** ("put into CLAUDE.md"). Included
   because mandating worktrees while the ignore rule lives only in `.git/info/exclude` ships a
   footgun with the rule that creates it — a fresh clone would show worktrees as untracked and
   `git add -A` could vendor an entire nested checkout. Flagged rather than assumed.

## Follow-up this rule implies

`working-in-this-repo` §6 documents the branch/commit/PR flow and still says only "Branch:
`OME-N-<description>` … Never commit to `main`". It should point at the worktree rule so the
routing skill and `CLAUDE.md` do not drift — the same drift that left that skill still naming OMDS
as brand law two units after `OME-716` replaced it. Not in this unit.
