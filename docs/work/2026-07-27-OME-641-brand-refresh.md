---
ticket: OME-641
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-641 — refresh SDK notebook widgets to the current brand

## Intent

Align the SDK's notebook visual system to the current `screamingface-brand` and make the
cards genuinely appealing (owner: full brand refresh). The brand evolved: gain is now **gold**
(was green), the signature is a **gold→blue** gradient sampled from the 😱, and display type is
**EB Garamond** serif.

## Planned changes

- `_display.py` `STYLE` (shared `.sf-ui`): `@import` brand webfonts (EB Garamond 500, IBM Plex
  Sans/Mono) with fallback stacks; add `--sf-display`/`--sf-sans`/`--sf-mono`; change `--sf-gain`
  (+ `--sf-gain-bg`) green→gold in both light and dark. Body uses `var(--sf-sans)`.
- `_card_style.py`: serif card titles (`--sf-display`); define `--sf-gain-grad` (gold→blue,
  scoped to card style only — keeps the connection panel gradient-free); add `.sf-card__accent`
  (gradient) / `.sf-card__accent--solid` (gold) top bars; refine.
- `_card_display.py`: prepend an accent bar to each card — gradient on Fusion, solid gold on
  Model/Benchmark/Connection/Case/Rubric.
- `_report_display.py` / `_connection_panel.py` / `_progress.py`: serif-ize the titles; gold gain
  inherited automatically.
- Tests: new `tests/test_ome641_brand_refresh.py`.

## Test plan (RED first)

- Shared STYLE: `--sf-gain` value is a gold hex (not the old green `#0f7a3d`); an `@import` of
  the brand fonts is present; `--sf-display` defined.
- `_card_style`: `--sf-gain-grad` gold→blue gradient present; card title uses `var(--sf-display)`.
- Fusion card contains the gradient accent; Model/Benchmark contain the solid gold accent.
- Connection panel HTML still contains no `linear-gradient` and no `purple` (regression guard).

## Acceptance

- All widgets render in the current brand (gold, serif titles, real fonts online); Fusion shows
  the gold→blue signature; connection panel stays gradient-free. Full gates green.

## Outcome

- **Actual files:** `_display.py` (rewrote STYLE: `@import` brand webfonts, `--sf-display`/
  `--sf-sans`/`--sf-mono` vars, `--sf-gain` green→gold in light+dark; body font kept as the
  literal IBM Plex Sans stack so the prior report visual-rules test stays valid); `_card_style.py`
  (card-scoped `--sf-gain-grad` gold→blue, `.sf-card__accent`(+`--solid`), serif card + catalog
  titles); `_card_display.py` (accent bar on every card — gradient on Fusion, solid gold on the
  rest); `_report_display.py` + `_connection_panel.py` (serif titles). New
  `tests/test_ome641_brand_refresh.py` (4 tests).
- **Commit:** feat(screamingface): refresh notebook widgets to the current brand (Refs: OME-641).
- **Gates:** `run_gates.py screamingface` → ALL GATES GREEN (append-only clean — only a new test
  file added). 763 + 4 new = 767 tests.
- **Deviations:**
  - Kept `.sf-ui` body `font-family` as the literal IBM Plex Sans stack (not `var(--sf-sans)`)
    so the existing cross-phase report test (`test_report_display` asserts the literal) keeps
    passing while the serif `--sf-display` var drives titles. No prior test was modified.
  - Fusion gradient token is card-scoped (not in shared STYLE) so the connection panel stays
    gradient-free (its "no linear-gradient" contract holds). Gold→blue only; no purple — the
    rationale comment moved out of the shipped CSS to avoid the literal word in output.
  - Brand self-check: gold gain, gold→blue signature (Fusion), serif titles, real fonts via
    `@import` with fallbacks, square, hairline, light+dark equal.