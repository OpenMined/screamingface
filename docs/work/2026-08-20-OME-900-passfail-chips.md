---
ticket: OME-900
stack: screamingface
status: done
started: 2026-08-20
finished: 2026-08-20
---

# OME-900 — Show PASS/FAIL on rubric criterion chips so word and color agree

## Intent

The SDK report panel renders each rubric criterion chip with the judge's raw word
(MET/UNMET) but colors it by score consequence — so a negative criterion shows a green
"UNMET" or a red "MET", forcing the reader to do polarity math (team Slack thread,
2026-08-20). Worse, `_check_good` only understands DRACO's `criterion_type` metadata;
HealthBench checks carry signed `points` instead, so HealthBench negative criteria render
with the WRONG color today (green MET on a −3 item), and `_case_passed` inherits that.
This unit derives PASS/FAIL at render time (PASS = positive∧MET ∨ negative∧UNMET), keeps
the judge's raw verdict as chip subtext/tooltip, and teaches polarity to read both
metadata vocabularies. Display layer only — stored verdicts are never rewritten.

## Planned changes

- `packages/screamingface/src/screamingface/_ui/report_view.py`
  - `_check_good`: polarity = `criterion_type == "negative"` OR `metadata.points < 0`
  - `_check_html`: chip text = derived PASS/FAIL; raw `judge: MET|UNMET` (+ "avoided" /
    "did the thing to avoid" gloss on negatives) as subtext/tooltip; unjudged unchanged
- `packages/screamingface/tests/test_report_panel.py` (or sibling): new cases

## Test plan

- Polarity matrix, both vocabularies (DRACO `criterion_type`, HealthBench signed
  `points`): 4 combinations → chip text PASS/FAIL + ok/bad badge class each
- HealthBench negative-points regression: MET on `points: -3` renders FAIL/red
  (invariant: a criterion that subtracted score can never render green)
- Raw verdict retention: chip still carries the literal judge word (MET/UNMET) in
  subtext/tooltip (invariant: archived verdict stays visible, only derived text changes)
- Unjudged check keeps the neutral warn badge (OME-848 invariant)
- `_case_passed`: HealthBench case with a tripped penalty no longer counts as passed

## Acceptance

- All four chip states render per the OME-900 display table; gates green
  (`run_gates.py` for the `screamingface` stack, coverage ≥95%)
- PR open from `OME-900-passfail-chips`; no Engine/schema/stored-data change

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `report_view.py` (`_check_negative` new, `_check_good`,
  `_check_html`, `_badge` + optional `title`), new `tests/test_criterion_chip_passfail.py`
  (11 tests), this ledger + `docs/tasks/2026-08-20-passfail-chips.md`
- **Commits:** single commit on `OME-900-passfail-chips` — `fix(screamingface): render
  rubric criterion chips as PASS/FAIL with the judge verdict in the tooltip` (sha in the
  Linear close comment; committed with this ledger, so the sha postdates this file)
- **Gates:** run_gates.py screamingface ALL GREEN — append-only ✓ ruff ✓ format ✓
  pyright ✓ pytest 955 passed 1 skipped, cov ≥95% ✓ notebooks ✓ build ✓ distribution ✓
- **Deviations:** one test sharpened during RED (asserting the badge markup, not the
  stylesheet, for "incorrect" — the CSS comment made the loose form vacuous); an
  `--all-extras` sync falsely reddened pyright in `_runtime/server.py` — env reverted to
  the intended notebook-extra-only install, no code touched there
