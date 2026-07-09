---
ticket: OME-369
stack: repo
status: done
started: 2026-07-09
finished: 2026-07-09
---

# OME-369 — Fix append-only check false positive on pure test additions

## Intent

`append_only_check()` in `.claude/scripts/run_gates.py` currently flags any test file
with git status `M` (modified) as a rule-5 violation, even when the change is a pure
addition (new test functions appended, nothing existing touched). This blocked all
downstream gates during OME-322 despite the changes being verifiably additive-only.
Fix it to check line-level diffs instead of file-level git status.

## Planned changes

- `.claude/scripts/run_gates.py` — `append_only_check()`: for each modified test file,
  parse `git diff <base> -- <file>` hunks and fail only if a hunk removes/changes a
  line that was inside a previously-existing `def test_...`/`async def test_...` body
  (i.e. a real `-` line inside old test code), not just because the file shows `M`.

## Test plan

No dedicated test suite exists for `.claude/scripts/` (confirmed — no stack in
`.claude/sdlc.local.md` covers it, no pytest wiring). Per owner decision, verify with a
quick manual check instead of adding permanent test infra:

- Scenario A (pure addition): a synthetic git history where a test file only gains new
  test functions → script must pass.
- Scenario B (real rewrite): a synthetic git history where a test file's existing test
  body is altered/removed → script must still fail.

## Acceptance

- Scenario A passes, Scenario B still correctly fails.
- No regression: running the real OME-322 diff (already merged into this fix's base)
  as a sanity check would have falsely failed before, passes after.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `.claude/scripts/run_gates.py` only (`append_only_check`
  rewritten; new `_old_test_ranges`/`_removed_old_lines` helpers; `ast`/`re` imports added).
- **Commits:** <fill after commit below>
- **Gates:** no dedicated stack/tests for `.claude/scripts/` (confirmed with owner).
  Verified manually with 4 scratch-repo scenarios instead:
  1. Pure addition (new test function) → pass.
  2. Real rewrite inside an existing test body → correctly fails.
  3. New import inserted above existing code → pass.
  4. An *existing* import line literally changed (the exact real OME-322 pattern) to
     support a new test, no test body touched → pass.
  Also ran the fixed check against our actual current branch vs `origin/main` as a
  real-world sanity check → passes cleanly (no test files touched by this ticket).
- **Deviations:** none — matches the plan.
