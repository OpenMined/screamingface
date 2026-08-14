# OME-832 — the notebook view must not present an inert flag as trust

Status: approved (owner, 2026-08-14) · Stack: screamingface

## 1. Problem

`OME-820` makes `verified_by_openmined` default to `True` for every submission. It asserts
nothing: nothing re-runs submissions (`OME-414`) and nothing attests where a run executed. The
scoreboard portal withdrew its verification UI accordingly (#588).

The Python client did not. `_ui/leaderboard_view.py` renders a `verified` chip per row and a
"verified only" checkbox that hides `[data-verified=false]`. With the flag uniform, the chip
appears on every row and the checkbox removes nothing.

This is the highest-visibility instance of the problem, because the notebook view is what renders
in Colab for the tester cohort. A green chip on every row plus a dead filter is a worse first
impression than no verification UI at all.

## 2. Why relabelling is not an option here

The chip could be reworded. **The filter could not.** Its defect is that every row carries the
same value, so no wording makes the control do something. Same conclusion as #588: hide.

## 3. The trap in the deletion

`_row_chip` is ordered:

```python
if value.verified:                 # -> "verified"
if value.python_source is None:    # -> "baseline"
return ""
```

Removing the first branch does **not** simply remove the chip. A candidate with no forkable url4
falls through to the second branch and is labelled **"baseline"** — presenting a community
submission as an imported single-model reference. That is a worse error than the one being fixed.

The predicate must key on what actually distinguishes a baseline: `_baseline_row` sets
`kind="single"`, `_candidate_row` sets `kind="candidate"`.

This also fixes a **pre-existing** case: today an *unverified* candidate with no forkable url4
already renders the `baseline` chip.

## 4. Contract

- No verification control and no verification chip in the rendered view.
- `baseline` chips render for baseline rows only, keyed on `kind`.
- `data-verified` is not emitted; its only consumer was the filter handler.
- `Leaderboard.verified_by_openmined` stays on the decoded model. The API still returns it; only
  presentation is withdrawn.

## 5. Reversal

`OME-821` gives the flag a real signal and restores both the chip and the filter. The checkbox CSS
is therefore kept, unused, rather than deleted and re-added.

## 6. Sequencing

**#588 must not merge before this.** Otherwise the flag goes uniform-true while the notebook still
badges every row, against a board that has just withdrawn the claim.
