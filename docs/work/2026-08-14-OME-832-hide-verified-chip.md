---
ticket: OME-832
stack: screamingface
status: in_progress
started: 2026-08-14
finished:
---

# OME-832 — hide the verified chip and filter in the Python leaderboard view

## Intent

Client half of the `OME-820` review fix, raised by `@HupBaHa` on PR #588.

`OME-820` makes `verified_by_openmined` default to `True` for every submission as a placeholder
that asserts nothing: no service re-runs submissions (`OME-414`) and nothing attests where a run
executed. #588 removes the scoreboard portal's Verified column, badge and "Verified rows" stat for
that reason.

The Python client still presents the flag as a trust signal, and **this is the surface Monday's
tester cohort sees**, because the notebook view is what renders in Colab:

- `_ui/leaderboard_view.py:117` — a "verified only" checkbox whose handler hides
  `[data-verified=false]` rows. No such row will exist, so the control does nothing.
- `_ui/leaderboard_view.py:219` — a `verified` chip, which would appear on every row.

## Decisions locked (2026-08-14)

| # | Decision | Choice |
|---|---|---|
| D1 | Hide, not relabel | Same reasoning as #588: the filter is broken because the value is *uniform*, not because the word is wrong. A checkbox that removes nothing is not fixable by renaming it. |
| D2 | **The baseline chip's predicate must change** | `_row_chip` currently reads `if value.verified: … ; if value.python_source is None: baseline`. Deleting the first branch would make a **verified candidate with no forkable url4** fall through and be labelled **"baseline"** — a mislabel worse than no chip. The predicate becomes `value.kind == "single"`, which is what actually distinguishes a baseline row (`_baseline_row` sets `kind="single"`; `_candidate_row` sets `kind="candidate"`). |
| D3 | Pre-existing bug fixed as a side effect | Under the old order, an **unverified** candidate with no forkable url4 already fell through to the `baseline` chip. D2 fixes that too. In scope because D2 is required for D1 to be correct. |
| D4 | `data-verified` removed | Its only consumer was the filter's own handler (`:103`). Grepped: no other reader in the package. |
| D5 | Checkbox CSS kept | `.sf-lb__checkbox*` in `leaderboard_style.py` becomes unused. Kept with a note, mirroring #588's decision to keep `createVerifiedBadge`: `OME-821` restores the control and would otherwise re-add identical CSS. `.sf-lb__chip` stays in use by the baseline chip. |
| D6 | The decoded model is untouched | `Leaderboard.verified_by_openmined` stays. The API returns the field; only its *presentation* is withdrawn. |

## Planned changes

- `packages/screamingface/src/screamingface/_ui/leaderboard_view.py` — drop `verify_action`, the
  checkbox markup, the `data-verified` attribute, and the `verified` branch of `_row_chip`; change
  the baseline predicate to `kind == "single"`.
- `packages/screamingface/src/screamingface/_ui/leaderboard_style.py` — note the now-unused
  checkbox rules.
- `packages/screamingface/tests/test_leaderboards.py` — new assertions; one prior assertion inverts
  (see Test plan).

## Test plan

RED first:

- `"verified only"` is absent from the rendered HTML.
- The `verified` chip is absent **even for a candidate whose `verified_by_openmined` is true** —
  the strong form. The existing assertion at `:787` only covers an *unverified* entry.
- `data-verified` is absent.
- The `baseline` chip is **still present** for a baseline row.
- **D2/D3 guard:** a candidate with no forkable url4 is *not* labelled `baseline`, whatever its
  verified value.

Prior tests affected:

- `:354` asserts `"verified only" in html`. It must invert. That is a Confidence-Gate decision
  under sdlc rule 5 — escalate, do not edit silently.
- `:787` asserts the verified chip is absent for an unverified entry. It keeps passing, but becomes
  **unfalsifiable** once the chip never renders. Left alone; the new strong-form assertion carries
  the real coverage. Recorded rather than quietly relied upon.

## Acceptance

- No verification control or chip in the rendered notebook view.
- Baseline rows keep their chip; candidates are never labelled `baseline`.
- Full `screamingface` gates green, including the 95% coverage floor.

## Outcome

- **Actual files:** as planned — `_ui/leaderboard_view.py`, `_ui/leaderboard_style.py` (comment
  only), `tests/test_leaderboards.py`, plus the four SDLC artifacts.
- **Gates:** `run_gates.py screamingface --base origin/main --skip-append-only` → **all seven
  green**: ruff check, ruff format, pyright, pytest --cov (95% floor), the notebook check,
  `uv build`, and the distribution check. **783 passed, 1 skipped.**

### The trap was real, and a test proved it

`test_a_candidate_is_never_labelled_baseline[False]` **failed before any production change** —
confirming from behaviour, not just from reading, that an unverified candidate with an unforkable
url4 already wore the `baseline` chip. `[True]` passed only because the `verified` branch shadowed
it. So a naive deletion would have turned the `[True]` case into the same mislabel, and the guard
would have caught it. D2/D3 hold.

### Deviations

1. **My own test contradicted my own decision, twice, and caught both.** D5 keeps the unused
   `.sf-lb__checkbox` CSS, but `LEADERBOARD_STYLE` is inlined into the same HTML string, so
   `assert "sf-lb__checkbox" not in html` failed on dead CSS rather than on a rendered control. The
   assertion was too broad; narrowed to the markup (`<label class='sf-lb__checkbox'>` and
   `<input type='checkbox'`). Then the explanatory CSS comment I added contained the literal phrase
   `"verified only"`, which also ships inline and tripped that assertion too. Reworded, and kept
   terse on purpose — **a CSS comment in this file is visible to every notebook reader in page
   source.**
2. **A prior assertion inverted, owner-approved.** `tests/test_leaderboards.py:356` asserted
   `"verified only" in html`. Escalated per sdlc rule 5 rather than edited. Inverted to `not in`
   rather than deleted, so it still catches the control being re-added before `OME-821`; its
   neighbours already assert absence the same way. Gate run used `--skip-append-only`.
3. **`tests/test_leaderboards.py:787` is now unfalsifiable and was left alone.** It asserts the
   verified chip is absent for an *unverified* entry; with the chip gone entirely it passes
   trivially. The new parametrised test carries the real coverage, including the verified case that
   assertion never covered. Recorded rather than silently relied on.
4. **A collection error that was not mine.** The suite first failed with
   `ModuleNotFoundError: No module named 'ipywidgets'`. Environmental — `uv sync --extra notebook`
   fixed it. Worth noting because the plan flagged exactly this: verify an unfamiliar gate failure
   against `origin/main` before treating it as your own.
5. **My `uuid4` import tripped ruff.** I inserted it beside `datetime` while `from uuid import UUID`
   already existed lower down. Merged into one statement by hand rather than running
   `ruff check --fix`, so the result is what I intended rather than what the fixer chose.

## Review pass (2026-08-14) — two findings, no correctness bugs

The review confirmed the central risk was handled correctly (`kind == "single"` is the right
predicate, HTML stays balanced, the interleaved-comment string concatenation is valid) and found no
correctness bugs. It also established something useful: **CI never invokes `run_gates.py`**, so the
append-only check the inverted assertion bypasses is local-only and cannot trip on the PR.

- **`_DisplayRow.verified` is now write-only dead state.** Both its readers went with this change, but
  `_candidate_row` still populates it and nothing in ruff, pyright or coverage will notice it going
  stale. Unlike the parallel CSS decision — which carries an in-file note — the field had no marker
  saying it is parked for `OME-821`. Added one, including an explicit "do not key new presentation on
  it": a row's value says nothing today, so doing so would reintroduce the inert trust signal this
  change removed. Kept rather than deleted for the same reason as the CSS.
- **Residual provenance ambiguity, left as a follow-up.** A candidate with an unforkable url4 renders
  the same icon, fill and action cell as a baseline, and `leaderboard_style.py:140` hides the `kind`
  cell below 680px — so in a narrow Colab pane the two are visually indistinguishable. **Pre-existing,
  and this PR strictly improves it** (that row was previously *labelled* `baseline`), so fixing it
  here would be scope creep. It belongs with `OME-821`'s presentation work.

Also noted: coverage passes at **95.05%** against a 95% floor — almost no headroom, so the next change
to this package may need to add tests before it can add code.

**Gates:** all seven green, 783 passed.
