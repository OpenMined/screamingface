---
ticket: OME-869
stack: url4-cloud
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-869 — Carry cache and reasoning token classes into the run totals

## Intent

The run-level cost frame reports only two of the five token classes. `_fold_usage`
(`runner/executor.py:307`) accumulates `input` and `output` only, and `build_subtree` (`:454`)
emits only those two, so `cache_read_tokens`, `cache_creation_tokens` and `reasoning_tokens` reach
the wire as `0` — while the per-span path (`_token_usage`, `:153`) carries all five. A span
reports `cache_read_tokens: 8000` and the run reports `0` for the same call.

User-visible: `packages/screamingface` surfaces all three classes
(`_engine/contract.py:371-391`), so a Report shows zeroes for tokens that were really used.

A plain omission from `OME-851` with no rationale behind it. Parent: `OME-849`. Found in peer
review of PR #620.

## Planned changes

- `src/url4_cloud/runner/executor.py` — `_RunState` gains run-level sums for the three missing
  classes; `_fold_usage` accumulates them; `build_subtree` emits all five.
- `tests/unit/test_run_total_token_classes.py` (new) — RED first, in its own module.

No wire/schema change. No new dependency.

## Design decision — run-level tokens do NOT poison

Money poisons on purpose: one unpriced call makes the run unpriced. That is correct *because the
wire can say so* — `pricing_version: "unpriced"` exists to carry it.

Tokens have no such escape hatch. `TokenUsage`'s fields are non-optional ints, so poisoning a
token class cannot express "unknown" — it publishes **zero**, a false claim rather than an absent
one. Concretely: an Anthropic call reporting `cache_read=8000, reasoning=None` beside an o1 call
reporting `cache_read=None, reasoning=610` would poison both to `0`, destroying two real numbers
to encode an uncertainty the frame cannot carry anyway.

So the poisoning rule stays for money and is deliberately NOT applied to run-level tokens. The
asymmetry is recorded at the code — it is exactly the kind of inconsistency a later reader would
otherwise "fix" back.

Per-span poisoning is left alone: a span is one model, so mixed reporting is unlikely there, and
changing it is out of scope.

## Test plan

RED first, in a new file.

1. A run whose calls report cache-read/cache-creation/reasoning publishes those sums, not zeroes.
   (This is the bug.)
2. Two calls each reporting a class sum to their total.
3. A class SOME calls reported sums the reported ones rather than collapsing to `0` — the
   no-poisoning decision, asserted directly so it cannot be silently reverted.
4. A class NO call reported stays `0`.
5. The run total agrees with the sum of its spans' `scope="self"` frames for every class — the
   invariant the whole unit restores.

## Acceptance

- All five classes summed across every `Usage` event and published by `build_subtree`.
- `test_n_usage_reports_sum_into_subtree_cost` passes unchanged — no append-only exception needed.
- `uv run .claude/scripts/run_gates.py url4-cloud` green with the append-only check intact.

## Outcome

Status: done.

- **Actual files:** as planned —
  - `src/url4_cloud/runner/executor.py` — three run-level sums on `_RunState`, accumulated in
    `_fold_usage` and emitted from `build_subtree`, with the money/token asymmetry recorded at the
    declaration.
  - `tests/unit/test_run_total_token_classes.py` (new, 8 cases).

- **RED evidence:** `6 failed, 2 passed`, each failure `assert 0 == 8000` — the class reaching the
  wire as zero while the span reported it. The two that passed are the guards: input/output were
  already carried, and a class no call reported was already zero.

  A first RED run failed for the WRONG reason — a harness error (`NodeFinished.__init__() got an
  unexpected keyword argument 'ok'`). Corrected before reading anything into it; a test that fails
  on its own scaffolding proves nothing about the code.

- **The design decision, and why it is NOT the money rule.** Money poisons: one unpriced call
  makes the run unpriced. Tokens deliberately do not. The difference is what the wire can spell —
  `pricing_version: "unpriced"` exists to carry an unknown price, while `TokenUsage`'s fields are
  non-optional ints. Poisoning a token class therefore cannot publish "unknown"; it publishes
  **zero**, a FALSE claim rather than an absent one, and it destroys the real counts the reporting
  calls did supply. The mixed-provider case is the normal one: one model reports cache reads and
  no reasoning, another the reverse, and poisoning would zero both real figures.

  `test_money_still_poisons_while_tokens_do_not` asserts both halves on the SAME run, so neither
  rule can later be "made consistent" with the other without a red test.

- **Mutation-checked, not assumed.** Replacing `+= x or 0` with `accumulate(...) or 0` — the exact
  "consistency" edit a later reader would be tempted to make — turns
  `test_a_class_only_some_calls_reported_sums_the_reported_ones` and
  `test_money_still_poisons_while_tokens_do_not` red, and restoring it turns them green. The two
  tests that pin the decision are load-bearing rather than tautological.

- **Left alone deliberately:** per-span poisoning through `accumulate`. A span is one model, so
  mixed reporting is unlikely there; a run spans many, which is why the rules differ. Recorded at
  the code with the condition that would justify revisiting it (optional counts on `TokenUsage`).

- **Gates:** `uv run .claude/scripts/run_gates.py url4-cloud --base origin/main` →
  **ALL GATES GREEN** (ruff · format · pyright · layering · pytest
  `--cov=url4_cloud --cov=url4.streaming --cov-fail-under=80` → **1697 passed, 5 skipped, 93%**).
  `test_n_usage_reports_sum_into_subtree_cost` passes unchanged, as predicted — it reports no such
  classes, so its zeroes remain correct. No append-only exception needed for this unit.

- **Deviations:** none.

- **S1 (migrations):** not applicable — no ORM or schema in this app.
