---
ticket: OME-861
stack: screamingface
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-861 — Stop warning when the Engine reports a total with no cost breakdown

## Intent

`_engine/contract.py:350` warns whenever the Engine's `total_usd` disagrees with the sum of its five
per-class components. `OME-850` made a total with no breakdown legal and `OME-851` publishes exactly
that (OpenRouter authors one amount, no split), so the condition now fires on **every priced run** —
confirmed live during the `OME-849` verification: three real runs, three warnings. Harmless, since the
SDK uses `total_usd` regardless, but it is user-visible log noise on the happy path in a library people
run in notebooks.

Parent: `OME-849`. Discovered by the live end-to-end test, not by any gate.

## Planned changes

- `src/screamingface/_engine/contract.py` — guard the warning on a breakdown having actually been
  supplied (`if parts and total != parts`), with a `WHY:`/`INVARIANT:` anchor naming the contract
  change that made the old condition wrong.
- `tests/test_engine_cost_breakdown_warning.py` (new) — the total-only case must be silent.

No wire/schema change. No new dependency.

## Test plan

RED first, in a new file — no prior test touched.

1. A cost frame carrying `total_usd` and NO components emits no warning, and `cost_usd` still equals
   the total. (This is the OME-851 shape; it is the bug.)
2. A frame whose supplied components disagree with the total still warns and still uses `total_usd`
   — the behaviour `test_priced_usage_keeps_the_engine_total_when_parts_differ` already pins, asserted
   again here from the new file's angle so the guard cannot be widened away silently.
3. An all-zero cost with `total_usd: "0"` is silent (the unpriced shape url4-cloud publishes).
4. An `unpriced` frame still yields `cost_usd=None` and null cache/reasoning token fields.

## Acceptance

- No warning for a total-only breakdown; warning preserved for a supplied-but-disagreeing one.
- `test_priced_usage_keeps_the_engine_total_when_parts_differ` passes unchanged.
- `uv run .claude/scripts/run_gates.py screamingface` green (ruff · format · pyright · pytest
  cov ≥95 · notebook check · `uv build` · distribution check).

## Outcome

Status: done.

- **Actual files:** as planned —
  - `src/screamingface/_engine/contract.py` — the warning is guarded on `parts` being non-zero, with
    `WHY:`/`INVARIANT:`/`AIDEV-NOTE:` anchors naming the contract change that made the old condition
    wrong and the residual it deliberately keeps.
  - `tests/test_engine_cost_breakdown_warning.py` (new, 5 cases).

- **RED evidence:** `2 failed, 3 passed`. The two failures were exactly the total-only cases, each
  reporting the real log line
  `SF Engine cost total_usd does not equal its parts; using total_usd (total=0.001, parts=0)`. The
  three that passed are guards — the supplied-but-disagreeing warning, the all-zero unpriced shape,
  and the unpriced token-nulling — and they hold on both sides of the change.

- **Design choice, and the alternative rejected.** Under the relaxed contract the only *incoherent*
  case is `parts > total`, so that was the first candidate rule. It was rejected: it would have
  stopped `test_priced_usage_keeps_the_engine_total_when_parts_differ` (a prior test) from seeing its
  warning, since there `parts=0.03 < total=0.030001`. Guarding on `if parts and total != parts`
  fixes the reported problem with **no prior-test change at all**, which is why this stack's
  append-only gate passes unskipped.

- **Accepted residual:** a producer supplying a genuinely PARTIAL breakdown (some classes known,
  summing below the total) still warns. No producer sends one — url4-cloud publishes total-only — so
  handling it now would be speculative. Recorded at the code with the condition to revisit.

- **Gates:** `uv run .claude/scripts/run_gates.py screamingface --base origin/main` →
  **ALL GATES GREEN**, append-only check included and **unskipped** (ruff · format · pyright · pytest
  `--cov=screamingface --cov-fail-under=95` · notebook determinism check · `uv build` · distribution
  check).

- **Rebase during this unit.** The gate first failed its append-only check listing files this unit
  never touched (a deleted `test_check_disclosure_display.py`, modifications across five others).
  Cause: `append_only_check` uses a **direct** `git diff <base>`, not a merge-base diff
  (`run_gates.py:366`), so once `origin/main` moved ahead — ten commits, several in
  `packages/screamingface` — main's own newer commits read as removals from this branch. Resolved by
  rebasing onto `origin/main` (`3ef7a70f` → `7c036d90`), which is required by `CLAUDE.md` rule 6
  regardless. No conflicts. All three stacks re-verified green after the rebase.
  **AIDEV-NOTE for the next agent:** the append-only gate is only meaningful on a branch current with
  its base. A stale branch produces a wall of false offenders — rebase before believing it.

- **Deviations:** none.

- **S1 (migrations):** not applicable — no ORM or schema in this package.
