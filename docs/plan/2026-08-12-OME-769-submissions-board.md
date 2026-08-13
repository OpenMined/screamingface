---
title: Submissions board — implementation plan
status: executed
created: 2026-08-12
spec: docs/spec/2026-08-12-OME-769-submissions-board.md
---

# Submissions board — plan

> Companion to the spec, added alongside it for the same auditability reason (see the spec's
> provenance note). Records the intended sequence and what the executed work diverged into.

## Sequence

1. **RED** — pure-function tests under `node --test` for the three load-bearing judgements:
   reproducible-SOTA selection, row ordering, and bar-width scaling. Assert the *invariants*
   (only a reproducible entry may be presented as SOTA; ordering is stable; a zero maximum
   cannot divide by zero) rather than the current source of each signal, so the tests survive
   `OME-771` re-sourcing reproducibility from the engine cache.
2. **GREEN** — `portal/leaderboard-logic.js`, dual-mode (browser global + `require`), no DOM.
3. **Wire** — `benchmark.js`: Author column, `.score-cell` accuracy cell, mark column,
   summary strip.
4. **Verify** — seed a deliberate data mix (a high *unverified* row, a lower *verified* row, a
   row with a null author) and measure in Chrome rather than eyeball it.
5. **Gates** — `run_gates.py scoreboard`, plus the JS tests.

## Files

- `apps/scoreboard/portal/leaderboard-logic.js` (new) — the pure decisions.
- `apps/scoreboard/tests/portal/leaderboard-logic.test.js` (new) — 14 tests, zero dependencies.
- `apps/scoreboard/portal/benchmark.js` — columns, accuracy cell, mark column, summary.
- `apps/scoreboard/portal/portal.css` — the mark column. **No edits to `style.css`/`tokens.css`**
  (byte-identical vendored copies).
- `apps/scoreboard/portal/benchmark.html` — script order.

## Divergences from this plan

1. **The mark went into its own column** rather than an in-cell slot — the in-cell version was
   built, measured, and found to break the alignment it existed for (spec D3).
2. **The SOTA medal was descoped entirely in review** (spec D13), which removed the wave-mark
   vendoring, the fourth summary stat, and the badge sizing rule along with it. Two review
   findings — a broken four-child `.stats` grid and two different numbers both painted with the
   win colour — were resolved *by* that descope rather than patched separately.
3. **`Questions` was removed** to keep the primary action out of a horizontal scroll (spec D11).
4. **Tests landed for real** rather than being deferred: `node:test` needs no new toolchain
   (spec D10). CI wiring is `OME-798`.
5. A CSS token (`--text-xs`) that does not exist in the design system was used and then removed
   with the badge rule. Same failure mode as the `--accent` bug found in PR #558 — the lesson is
   to grep the token list before using a plausible-looking name, not to trust the pattern.
