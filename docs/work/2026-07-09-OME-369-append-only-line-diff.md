---
ticket: OME-369
stack: repo
status: in_progress
started: 2026-07-09
finished:
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

## Round 2 (2026-07-17) — PR #383 review feedback

`HupBaHa` requested changes on the PR: verified with temp git repos that adding a
separate test passes and a root-level rewrite is rejected, but the check still lets
prior tests be changed undetected in the *configured nested stacks*, and asked for a
permanent temp-repo test matrix (nested roots, additive-inside-old-test, decorators/
fixtures, dash-prefixed hunk content) instead of relying on manual scratch-repo
verification.

Dug in and confirmed three distinct, real bugs (verified each empirically with a
throwaway repo before touching the fix):

1. **Nested stack roots (the reviewer's main point).** `_old_test_ranges()` calls
   `git show f"{base}:{path}"` with `cwd=root` (the stack root, e.g.
   `apps/scoreboard`). `path` comes from `git diff --relative` and is already
   relative to `cwd` — but `git show rev:path` resolves `path` relative to the
   **repo root**, not `cwd`, unless prefixed with `./`. For any stack whose root
   isn't `.` (i.e. every real stack in `.claude/sdlc.local.md` — `aigateway`,
   `scoreboard`, `url4`), the `git show` call fails to find the file, hits the
   `proc.returncode != 0` branch, and returns `[]` — meaning the check currently
   protects **zero** test ranges for any real stack. Confirmed with a scratch repo:
   `git show base:tests/x.py` from inside a nested cwd fails; `git show
   base:./tests/x.py` succeeds.
2. **Decorators/fixtures.** `ast.FunctionDef.lineno` points to the `def` line, not
   the decorator above it (confirmed via `ast.parse` — decorator at line 3, function
   range recorded starts at line 4). Editing a decorator/`parametrize(...)` list
   above an existing test body isn't "inside" the recorded range, so it escapes
   detection.
3. **Dash-prefixed hunk content.** A removed line whose content starts at column 0
   with `--` (e.g. a bare `---` separator) produces a diff line `----`, which
   false-matches the `line.startswith(("---", "+++", "\\"))` header-skip check.
   That both drops the line from `removed` *and* desyncs `old_line` for every
   subsequent line in the same hunk (confirmed with a scratch repo: `git diff
   --unified=0` on a `---` → `CHANGED` edit produces literal `----`/`+CHANGED`).

## Planned changes (round 2)

- `.claude/scripts/run_gates.py`:
  - `_old_test_ranges`: prefix the `git show` path with `./` so it resolves
    relative to `cwd` regardless of stack root depth.
  - `_old_test_ranges`: extend a test's protected range to start at its first
    decorator's line when it has decorators, not just `node.lineno`.
  - `_removed_old_lines`: replace the `startswith(("---", "+++", "\\"))`
    content-based header skip with hunk-boundary tracking (`in_hunk` flag flipped by
    the first `@@` line) — file-level header lines only ever appear before the
    first hunk, so this can't collide with real content regardless of what
    characters that content starts with.
- New `.claude/scripts/tests/test_run_gates.py` — the permanent temp-repo matrix the
  reviewer asked for (stdlib `unittest`, no new toolchain/dependency), replacing the
  round-1 manual-only verification. Covers: pure addition, real rewrite, new import,
  existing-import-line-changed (the original 4 manual scenarios), plus the 3
  confirmed bugs above (nested stack root, decorator edit, dash-prefixed content),
  plus whole-file delete.

## Test plan (round 2)

- Every scenario above as its own `unittest` test building a throwaway git repo
  under a `tempfile.TemporaryDirectory()`, calling `append_only_check`/
  `_old_test_ranges`/`_removed_old_lines` directly (imported via
  `importlib.util.spec_from_file_location`, since the script isn't an installed
  package) — asserting the boolean/return value, not just "it ran".
- Each of the 3 new tests must fail on the pre-fix code and pass on the post-fix
  code (verified manually by running against git stash of the old version before
  finalizing).

## Acceptance (round 2)

- All three confirmed bugs fixed; the new permanent test file covers all 8
  scenarios and passes.
- No regression on the round-1 scenarios (still covered, now as permanent tests
  instead of manual scratch-repo checks).

## Outcome (round 2, fill at the end — required before COMMIT)

- **Actual files:**
  - `.claude/scripts/run_gates.py` — `_old_test_ranges`: `./`-prefixed `git show`
    path (nested-root fix) + decorator-inclusive range start. `_removed_old_lines`:
    `in_hunk`-boundary header skip replacing the content-prefix check.
  - `.claude/scripts/tests/test_run_gates.py` — new, 8 tests (the 4 round-1 manual
    scenarios made permanent + 4 more: nested stack root, decorator edit,
    dash-prefixed content, whole-file delete).
- **Commits:** pending — not yet committed, holding for the user's go-ahead before
  pushing to the open PR (#383).
- **Gates:** no dedicated stack/tests wired for `.claude/scripts/` in
  `.claude/sdlc.local.md` (unchanged from round 1). Verified instead:
  - `uv run .claude/scripts/tests/test_run_gates.py -v` → 8/8 pass on the fixed code.
  - Confirmed each of the 3 new regression tests (`test_nested_stack_root_...`,
    `test_decorator_edit_...`, `test_dash_prefixed_content_...`) **fails** against
    the pre-fix code via `git stash` of `run_gates.py` alone, then passes again
    once restored — proves they're real regressions, not tautological assertions.
  - `python3 -m py_compile` on both files clean; `uvx ruff check` on both files
    clean (not a wired gate for this directory, done as hygiene).
- **Deviations:** none from the round-2 plan.

## Round 3 (2026-07-17) — two more review concerns, both confirmed valid

Same review thread raised two further P2 concerns after round 2. Both verified
empirically (not just reasoned about) before touching code:

1. **Insertions inside existing tests bypass the gate.** `_removed_old_lines` only
   ever populates from `-` lines — a pure insertion (zero removed lines) that
   neuters a prior assertion (e.g. forcing a variable's value directly above the
   check) produces a diff of only `+` lines and is invisible to it. Proved with a
   throwaway repo: inserted `result = 42` directly above `assert result == 42`
   (`compute()` actually returns 41) — `append_only_check` returned `True` (green)
   against the round-2 code.
2. **Fixtures/helpers aren't protected.** `_old_test_ranges` only walked
   `test_*`-named functions. Confirmed this isn't hypothetical in this repo:
   `apps/scoreboard/tests/conftest.py` and `apps/aigateway/tests/conftest.py` both
   have real `@pytest.fixture` functions matched by the `tests/**` glob — editing
   one today passes the append-only gate silently, where the pre-OME-369 blanket
   file-status check would have caught it.

## Planned changes (round 3)

- `.claude/scripts/run_gates.py`:
  - `_old_test_ranges` → renamed `_old_protected_ranges`, drops the `test_*` name
    filter — protects every function (tests, fixtures, helpers alike).
  - `_removed_old_lines` → renamed `_diff_positions`, now returns
    `(removed, inserted_after)`. `inserted_after` records, for each contiguous run
    of `+` lines, the old-file line number immediately preceding the insertion.
  - `append_only_check`: violation is now `removed` INCLUSIVE-both-ends
    (`lo <= ln <= hi`, unchanged) OR `inserted_after` EXCLUSIVE-at-`hi`
    (`lo <= n < hi`). The exclusive upper bound is the crux of this round: it's
    what keeps "append a new test directly after an existing one, zero blank
    lines" (anchored at `n == hi` of the preceding function) legitimate, while
    still catching "insert as the new first/middle statement of an existing
    function" (`lo <= n < hi`).
- `.claude/scripts/tests/test_run_gates.py`: 4 new tests —
  `test_insertion_neuters_existing_test_fails`, `test_fixture_edit_detected`
  (the two confirmed-bug regressions), plus
  `test_append_new_function_immediately_after_existing_passes` and
  `test_insert_new_function_immediately_before_existing_passes` (the boundary
  cases that prove the exclusive bound doesn't reopen OME-369's original
  false-positive).

## Test plan (round 3)

- Same discipline as round 2: each new "must fail" test proven to fail against the
  round-2-only code (via a temp backup of `run_gates.py`, not git stash this time
  since nothing is committed yet) and pass against round-3 code.
- The two boundary "must still pass" tests are the regression guard for THIS
  round's own change (round-2 code never inspected `+` lines at all, so they'd
  trivially pass there too — the meaningful check is that they pass under the new
  `inserted_after` logic, confirmed).

## Acceptance (round 3)

- Both confirmed bugs fixed; full matrix (12 tests: 8 from rounds 1–2 + 4 new) passes.
- No regression: the two adjacent-append boundary cases still pass under the new
  insertion-detection logic.

## Outcome (round 3, fill at the end — required before COMMIT)

- **Actual files:**
  - `.claude/scripts/run_gates.py` — `_old_protected_ranges` (renamed, filter
    dropped), `_diff_positions` (renamed, now returns removed + inserted_after),
    `append_only_check` updated to check both with their respective bounds.
  - `.claude/scripts/tests/test_run_gates.py` — 4 new tests, 12 total.
- **Commits:** pending — holding for the user's go-ahead before pushing to PR #383.
- **Gates:** same as round 2 (no wired stack for this directory). Verified:
  - `uv run .claude/scripts/tests/test_run_gates.py -v` → 12/12 pass on round-3 code.
  - `test_insertion_neuters_existing_test_fails` and `test_fixture_edit_detected`
    confirmed to **fail** against a snapshot of the round-2-only code, then pass
    once round-3 changes are restored.
  - `python3 -m py_compile` and `uvx ruff check` clean on both files.
- **Deviations:** none from the round-3 plan.
