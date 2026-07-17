---
ticket: OME-369
stack: repo
status: done
started: 2026-07-09
finished: 2026-07-17
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
- **Commits:** `ee8addd` — fix(repo): append-only gate checks line-level diffs,
  not file status (Refs: OME-369).
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
- **Commits:** `39f1483` — fix(repo): protect nested stacks, decorators, and
  fixtures in append-only gate (Refs: OME-369) — combined rounds 2+3 in one commit,
  not pushed yet per user instruction.
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
- **Commits:** `39f1483` (same commit as round 2 — both rounds landed together
  before the first push of this fix cycle). Not pushed yet per user instruction.
- **Gates:** same as round 2 (no wired stack for this directory). Verified:
  - `uv run .claude/scripts/tests/test_run_gates.py -v` → 12/12 pass on round-3 code.
  - `test_insertion_neuters_existing_test_fails` and `test_fixture_edit_detected`
    confirmed to **fail** against a snapshot of the round-2-only code, then pass
    once round-3 changes are restored.
  - `python3 -m py_compile` and `uvx ruff check` clean on both files.
- **Deviations:** none from the round-3 plan.

## Round 4 (2026-07-17) — the reviewer's last P2 concern, plus a deeper sweep

Same review thread's second remaining P2: module-level test data (e.g. `_BASE_KW`
in `apps/aigateway/tests/unit/test_request_cache_keys.py`, real and confirmed, not
hypothetical) is invisible to a function-only pass. Confirmed empirically, fixed.

At the user's request I then probed further, beyond what the reviewer asked, and
found two more things — both deliberately **not fixed here**, tracked as separate
follow-ups instead (see below) to avoid scope drift on this PR:

1. **Decorator-stacking** ("concern A", the reviewer's OTHER remaining P2):
   confirmed valid and reproducible, but needs old-vs-new AST identity matching —
   a different, larger mechanism than this PR's line-position diffing. Deferred.
2. **Name-shadowing / monkeypatching** (found via my own probing, not a reviewer
   comment): redefining, reassigning, `del`-ing, or mutating shared state anywhere
   later in a file — even far from what it affects — silently neuters prior
   tests/fixtures/data while looking like an ordinary append. Proved with 4
   variants (class redefinition, plain reassignment, `del`, monkeypatch appended
   at file end unrelated to either test it affects). This is a structural
   limitation of any pure line-diff gate, not a finite list of bugs — closing it
   for real needs semantic/data-flow analysis or execution-based verification.
3. Also found (not a code bug, a process/infra gap): **no independent
   enforcement** of this check exists anywhere — no CI workflow references
   `run_gates.py`, no pre-push hook, and every documented invocation omits
   `--base` (defaults to `HEAD`, i.e. only the uncommitted delta vs the last local
   commit, never the cumulative diff vs `origin/main`). Tracked as its own ticket,
   separate from OME-369, since it's a different kind of unit of work entirely.

## Planned changes (round 4)

- `.claude/scripts/run_gates.py`: `_old_protected_ranges` also walks `tree.body`
  (module-level, non-recursive) for every statement except
  `Import`/`ImportFrom`/`FunctionDef`/`AsyncFunctionDef`/`ClassDef` — imports stay
  exempt (preserves round 1's explicit decision); functions already covered by the
  separate `ast.walk` pass; class-level attributes noted as a related, deliberately
  out-of-scope gap (same shape of problem, would need per-statement treatment
  inside class bodies too, not a whole-class-span shortcut — that would reopen the
  "insert a new method between two existing ones" false positive).
- `.claude/scripts/tests/test_run_gates.py`: 4 new tests —
  `test_module_level_test_data_edit_detected` (the confirmed-bug regression),
  `test_existing_import_line_changed_still_passes_with_data_protection` (guards
  round 1's decision isn't reversed), `test_new_module_level_constant_addition_passes`
  and `test_append_new_constant_immediately_after_existing_passes` (boundary cases
  at data scope, mirroring the function-scope ones from round 3).

## Test plan (round 4)

- Same discipline as rounds 2-3: `test_module_level_test_data_edit_detected`
  confirmed to **fail** against a snapshot of round-3-only code, pass on round-4
  code. The three "must still pass" tests confirmed passing on both (expected,
  since round 3 never inspected module-level statements at all — the meaningful
  check is that they still pass under the NEW data-protection logic).
- Sanity check against the real repo: parsed
  `apps/aigateway/tests/unit/test_request_cache_keys.py` directly —
  `_old_protected_ranges` finds 22 protected ranges including `_BASE_KW`'s own
  span, no crash.

## Acceptance (round 4)

- Confirmed bug fixed; full matrix (16 tests: 12 from rounds 1-3 + 4 new) passes.
- No regression: round 1's "existing import line changed" decision still holds
  under the broadened protection.

## Known limitations (documented, not fixed — see follow-up tickets)

This gate catches accidental/naive test-weakening well after rounds 1-4 (line
rewrites, insertions, decorator edits on existing decorators, fixtures, module
data). It does **not**, and structurally cannot via line-diffing alone, catch
determined bypass via name-shadowing/monkeypatching (tracked as a follow-up
ticket, see Outcome below), or a new outermost decorator stacked onto a
previously-undecorated (or already-decorated) test (concern A, tracked
separately). It also has no independent enforcement — nothing stops it from
simply not being run (also tracked separately, as a distinct infra unit).

## Outcome (round 4, fill at the end — required before COMMIT)

- **Actual files:**
  - `.claude/scripts/run_gates.py` — `_EXEMPT_TOP_LEVEL` tuple + `_old_protected_ranges`'s
    second pass over `tree.body`.
  - `.claude/scripts/tests/test_run_gates.py` — 4 new tests, 16 total.
- **Commits:** `ad9394e` — fix(repo): protect module-level test data in
  append-only gate (Refs: OME-369).
- **Gates:** `uv run .claude/scripts/tests/test_run_gates.py -v` → 16/16 pass.
  `test_module_level_test_data_edit_detected` confirmed to fail on round-3 code,
  pass on round-4 code. `python3 -m py_compile` and `uvx ruff check` clean.
- **Deviations:** none from the round-4 plan.
- **Follow-ups filed:** pending (concern A, shadowing/monkeypatching, and the
  CI-enforcement-gap — filed as separate tickets right after this commit).

## Round 5 (2026-07-17) — structured code-review pass on the already-pushed PR

Per the user's request, ran a multi-angle `code-review` pass (8 finder agents:
3 correctness, 3 cleanup, altitude, conventions) against the full pushed diff
before requesting re-review. Correctness findings were verified by direct
execution against the actual code (not just read), same standard as every prior
round. Two findings meant round 4's fix, as pushed, had its own bugs:

1. **Round 4's `_EXEMPT_TOP_LEVEL` was a denylist — the wrong shape.** Proved
   two concrete false positives it produces: editing a bare module docstring
   (an `ast.Expr`, not in the denylist) and editing the near-universal
   `if __name__ == "__main__":` runner block (an `ast.If`, also not in the
   denylist) both got flagged as rule-5 violations with ZERO test logic
   touched — reopening the exact class of false-positive OME-369 exists to
   eliminate. A third case, an import nested inside a module-level version-guard
   (`if sys.version_info >= (3, 10): ... else: ...`), was also swept into the
   `If` block's coarse protected range, contradicting round 1's own "editing an
   import stays legitimate" invariant.
2. **A separate bug in `_diff_positions`'s insertion-anchor tracking.**
   Replacing the blank separator line between two functions with a comment
   (touching neither function's body) got flagged, because the paired `+`
   line's anchor was computed AFTER `old_line` advanced past the removed line,
   landing exactly on the next function's range start. Verified: `removed={3}`
   (correctly outside any range), but `inserted_after={4}` (the next function's
   `lo`) — a false positive from anchor drift on replace pairs specifically.

Fixed both at the root rather than patching each symptom:

- Inverted `_EXEMPT_TOP_LEVEL` (denylist) to `_MODULE_LEVEL_DATA = (ast.Assign,
  ast.AnnAssign)` (allowlist) — only the node types that actually hold shared
  test data get a protected range. This single change resolves all three
  denylist-shaped false positives (docstring, `if __main__`, nested import) at
  once, since none of those node types are `Assign`/`AnnAssign`.
- Changed `inserted_after` tracking to key off the diff hunk header's declared
  OLD-LINE-COUNT (`old_count == 0` ⇒ unambiguously a pure-insertion hunk),
  instead of inferring "pure insert" from `-`/`+` line pairing. Removes the
  ambiguity entirely rather than trying to special-case replace-pair adjacency.
- Also fixed, from the same review pass's conventions angle: several
  `AIDEV-NOTE`/`INVARIANT` anchors were written as bare docstring prose instead
  of `#`-prefixed comments (`.claude/skills/sdlc-python/SKILL.md`'s "Anchor
  syntax: `#`" rule) — moved all of them to proper inline `#` comments.

Deliberately NOT acted on from the same review pass (reported, not fixed, to
avoid re-drifting): Reuse's test-boilerplate-duplication and
FunctionDef-tuple-naming suggestions, Simplification's docstring-length and
duplicate-comprehension suggestions, Efficiency's git-subprocess-batching
suggestions, and Altitude's "this is a reactive patch stack" observations (all
of which restate concern A / the class-attribute gap already tracked
separately, not new scope).

## Planned changes (round 5)

- `.claude/scripts/run_gates.py`: `_EXEMPT_TOP_LEVEL` → `_MODULE_LEVEL_DATA`
  allowlist; `_HUNK_HEADER` regex now captures the old-line count;
  `_diff_positions` computes `pure_insert_hunk` from that count per-hunk;
  anchor comments moved from docstring prose to `#`-prefixed inline comments.
- `.claude/scripts/tests/test_run_gates.py`: 4 new tests —
  `test_module_docstring_edit_passes`, `test_if_main_block_edit_passes`,
  `test_import_nested_in_conditional_edit_passes`,
  `test_replace_blank_separator_line_passes`.

## Test plan (round 5)

- Same discipline as every prior round: all 4 new tests confirmed to **fail**
  against a snapshot of the round-4 (already-pushed) code, then pass once the
  round-5 fix is restored.
- Full 20-test matrix (16 from rounds 1-4 + 4 new) passes on the fixed code.
- Real-file sanity check unchanged: `_old_protected_ranges` against
  `apps/aigateway/tests/unit/test_request_cache_keys.py` still finds 22
  protected ranges including `_BASE_KW`'s own span.

## Acceptance (round 5)

- Both code-review-discovered bugs fixed; 20/20 tests pass.
- No regression: all 16 prior tests (rounds 1-4) still pass unmodified.
- Anchor-syntax convention violation fixed (all `WHY:`/`INVARIANT:`/`AIDEV-NOTE:`
  now `#`-prefixed).

## Outcome (round 5, fill at the end — required before COMMIT)

- **Actual files:**
  - `.claude/scripts/run_gates.py` — `_MODULE_LEVEL_DATA` allowlist (replaces
    `_EXEMPT_TOP_LEVEL`), `_HUNK_HEADER`/`_diff_positions` old-count-based
    `pure_insert_hunk` fix, anchor comments moved to `#`-prefixed form.
  - `.claude/scripts/tests/test_run_gates.py` — 4 new tests, 20 total.
- **Commits:** `eee239e` — fix(repo): replace denylist with allowlist for
  module-data protection (Refs: OME-369).
- **Gates:** `uv run .claude/scripts/tests/test_run_gates.py -v` → 20/20 pass.
  All 4 new tests confirmed to fail on round-4 code, pass on round-5 code.
  `python3 -m py_compile` and `uvx ruff check` clean.
- **Deviations:** none from the round-5 plan.

## Round 6 (2026-07-17) — second structured code-review pass

Ran the same 8-angle `code-review` pass again on the now-pushed round-5 state,
per the user's request for another round before filing follow-up tickets.
5 of 8 angles came back clean (line-by-line, removed-behavior, cross-file,
efficiency — all re-verified the fixes hold and found nothing new). 3 found
real, low-severity items:

- **Altitude** (verified by execution): `_MODULE_LEVEL_DATA = (Assign,
  AnnAssign)` missed `ast.AugAssign` — a module-level accumulator statement
  like `_CASES += [4, 5]` was unprotected. Fixed: added `ast.AugAssign` to the
  allowlist (trivial, safe — same shape as the existing types). Also found a
  bare module-level walrus statement (`(_TOTAL := 10)`) is unprotected too, but
  judged too exotic a pattern in real test code to special-case — documented
  as a third known limitation alongside the class-attribute and
  nested-conditional-Assign gaps already in the code's AIDEV-NOTE.
- **Conventions**: Round 1's ledger Outcome section still had the literal
  placeholder `<fill after commit below>`, never filled in across all 5 prior
  rounds. Fixed — filled with the real sha (`ee8addd`).
- **Reuse** and **Simplification** each found one low-severity polish item
  (a duplicated git-error-handling block between `_diff_positions` and
  `append_only_check`; collapsing `old_count` into a direct string comparison).
  Deliberately NOT acted on — pure style, no correctness impact, and the
  Reuse finding itself warns that naively unifying the git-helper would risk
  breaking `_old_protected_ranges`'s deliberately-different permissive-on-404
  behavior.

## Planned changes (round 6)

- `.claude/scripts/run_gates.py`: `_MODULE_LEVEL_DATA` gains `ast.AugAssign`;
  AIDEV-NOTE gains a third known-gap entry (walrus statements).
- `.claude/scripts/tests/test_run_gates.py`: 1 new test —
  `test_module_level_augassign_edit_detected`.
- `docs/work/2026-07-09-OME-369-append-only-line-diff.md`: Round 1's Outcome
  Commits field filled in (`ee8addd`).

## Test plan (round 6)

- Same discipline as every prior round: the new test confirmed to fail against
  a snapshot of round-5 code, pass on round-6 code.
- Full 21-test matrix (20 from rounds 1-5 + 1 new) passes.

## Acceptance (round 6)

- `AugAssign` gap fixed; 21/21 tests pass.
- No regression: all 20 prior tests still pass unmodified.
- Ledger placeholder gap fixed.

## Outcome (round 6, fill at the end — required before COMMIT)

- **Actual files:**
  - `.claude/scripts/run_gates.py` — `_MODULE_LEVEL_DATA` gains `ast.AugAssign`;
    AIDEV-NOTE gains the walrus-statement known-gap entry.
  - `.claude/scripts/tests/test_run_gates.py` — 1 new test, 21 total.
  - `docs/work/2026-07-09-OME-369-append-only-line-diff.md` — Round 1's
    Commits placeholder filled.
- **Commits:** `249e462` — fix(repo): protect module-level augmented-assignment
  test data (Refs: OME-369).
- **Gates:** `uv run .claude/scripts/tests/test_run_gates.py -v` → 21/21 pass.
  New test confirmed to fail on round-5 code, pass on round-6 code.
  `python3 -m py_compile` and `uvx ruff check` clean.
- **Deviations:** none from the round-6 plan.

## Round 7 (2026-07-17) — third structured code-review pass

Per the user's request to loop review rounds until one comes back clean. 5 of
8 angles clean this round (cross-file, reuse, removed-behavior auditor,
efficiency clean-except-one-polish-nit, simplification clean-except-one-doc-nit).
Two angles found real things:

- **Line-by-line** (verified by execution): a protected range's LAST line, if
  it lacked a trailing newline at `base`, produces a git-diff artifact when new
  content is appended after it — git represents the unchanged line as a
  remove+add pair purely because its EOF status changed (a newline character
  had to be added to make room for what follows), not because its text
  changed. `_diff_positions` tracked only line *numbers*, so this false-matched
  as a real edit — a plausible, non-adversarial trigger (any file lacking a
  trailing newline, then having a normal new test appended), unlike the
  already-deferred shadowing class. Fixed: track whether a removed line was
  marked `\ No newline at end of file` and, if the immediately-following `+`
  line is byte-identical, treat it as a no-op rather than a real change.
- **Altitude** (verified by execution): found two more concrete instances of
  mutating a protected object in place rather than rebinding its name —
  `_CASES.append(...)` (an `ast.Expr` wrapping a `Call`) and `del _CASES[1]`
  (`ast.Delete`) both bypass the gate. On reflection these are NOT new
  independent allowlist gaps — they're the SAME structural
  name-shadowing/monkeypatching limitation already identified and deferred
  (mutating shared state in place instead of rebinding a name; adding
  `Expr`/`Delete` to the allowlist wouldn't close this class either, and
  broadly allowlisting `ast.Expr` would reopen the round-5 docstring false
  positive). Folded into the existing "known gaps" AIDEV-NOTE as bullet (4)
  with these two concrete examples, rather than treated as new code to write.

Also applied, from **simplification**: a doc-only addition warning that the
"just add the type to `_MODULE_LEVEL_DATA`" fix pattern (used for `AugAssign`)
would NOT work for the walrus-statement gap, since `tree.body`'s direct child
there is the outer `ast.Expr`, never the inner `NamedExpr` — prevents a future
contributor from shipping a no-op "fix."

Deliberately NOT acted on: efficiency's suggestion to fold 3 `git config`
subprocess calls into `-c` flags on the commit call in the test suite (pure
speed polish, zero correctness impact).

## Planned changes (round 7)

- `.claude/scripts/run_gates.py`: `_diff_positions` tracks `last_removed`
  (old_line, content, no_newline_flag) so a `-`/no-newline-marker/byte-identical
  `+` sequence is recognized as an EOF-status artifact and excluded from
  `removed`. "Known gaps" AIDEV-NOTE gains bullet (4) (mutation-in-place
  examples) and a warning note on bullet (3) (walrus fix-pattern doesn't work).
- `.claude/scripts/tests/test_run_gates.py`: 1 new test —
  `test_append_after_file_without_trailing_newline_passes`.

## Test plan (round 7)

- Same discipline as every prior round: the new test confirmed to fail against
  a snapshot of round-6 code (reproduced the exact real `git diff` shape:
  `-content` / `\ No newline at end of file` / `+content` / more `+` lines),
  pass on round-7 code.
- Full 22-test matrix (21 from rounds 1-6 + 1 new) passes.

## Acceptance (round 7)

- EOF-newline-artifact false positive fixed; 22/22 tests pass.
- No regression: all 21 prior tests still pass unmodified.
- Documentation gaps (walrus fix-pattern warning, mutation-in-place examples)
  added without any corresponding code change, since both are correctly
  out-of-scope for this allowlist mechanism.

## Outcome (round 7, fill at the end — required before COMMIT)

- **Actual files:**
  - `.claude/scripts/run_gates.py` — `_diff_positions`'s `last_removed`
    tracking for the EOF-newline-artifact fix; AIDEV-NOTE additions.
  - `.claude/scripts/tests/test_run_gates.py` — 1 new test, 22 total.
- **Commits:** `ddf8371` — fix(repo): recognize EOF-newline artifacts as
  non-edits (Refs: OME-369).
- **Gates:** `uv run .claude/scripts/tests/test_run_gates.py -v` → 22/22 pass.
  New test confirmed to fail on round-6 code, pass on round-7 code.
  `python3 -m py_compile` and `uvx ruff check` clean.
- **Deviations:** none from the round-7 plan.
