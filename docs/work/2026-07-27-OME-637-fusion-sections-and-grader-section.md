---
ticket: OME-637
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-637 — separate always-visible members/reducer sections; grader section

## Intent

User feedback on OME-635 cards: make the Fusion card's members and reducer **separate,
always-visible** sections (not one collapsed block), and give the Benchmark grader its own
always-visible section so its (collapsible) prompt is unmistakable. Long prompts still collapse.

## Planned changes

- `_card_style.py`: add `.sf-section` / `.sf-section__title` (always-visible detail section);
  drop the `.sf-detail` collapsed-wrapper styling (keep item styles).
- `_card_display.py`: `_fusion_detail_html` → two sections (`_section("members", items)` and
  `_section("reducer", reducer_body)`), no `<details>`. `benchmark_card_html` → move grader into
  `_section("grader", _grader_detail(...))`; keep scalars in the grid; keep engine routes as a
  collapsed `<details>`.
- Tests: update the OME-635 fusion test (was "collapsed combined") and add OME-637 assertions
  (separate section titles, not wrapped in `<details>`, grader prompt still collapsible).

## Test plan (RED first)

- Fusion card contains separate `members` and `reducer` section titles and is NOT wrapped in a
  `<details class='sf-detail'>`; member/reducer long prompts collapse.
- Benchmark card has a `grader` section; a long Rubric prompt renders `<details class='sf-more'>`.

## Acceptance

- Members and reducer show as separate, uncollapsed sections; grader prompt collapsible in its
  own section. Full gates green.

## Outcome

- **Actual files:** `_card_style.py` (added `.sf-section`/`.sf-section__title`, replaced the
  `.sf-detail` collapsed wrapper); `_card_display.py` (`_section` helper; `_fusion_detail_html`
  → two always-visible sections; benchmark grader moved out of the grid into a `grader`
  section). New `tests/test_ome637_sections.py` (2 tests); updated the OME-635 fusion test.
- **Commit:** feat(screamingface): separate members/reducer sections + grader section
  (Refs: OME-637).
- **Gates:** `run_gates.py screamingface --skip-append-only` → ALL GATES GREEN. 754 + 2 = 756.
- **Deviations:** append-only skip — updated one same-session unmerged OME-635 fusion test to
  the new (uncollapsed, separate-sections) behavior per the user's request. Confirmed the grader
  prompt was already collapsible; the change gives it its own section so it's unmistakable.

## Follow-up fix — 2026-07-27 (spacing)

User: double line between source and grader, none between grader and engine routes. Cause: the
grid kept a `border-bottom` while each `.sf-section` also adds `margin-top` + `border-top`
(→ two lines), and engine routes had reverted to an unstyled `.sf-detail` wrapper (→ no line).
Fix: dropped `.sf-card__grid` bottom border (the following section's top border is now the sole
separator), added a `border-top` to `.sf-card__recipe`, and made engine routes a
`<details class='sf-section'>` (separated + collapsible). Guarded by `tests/test_ome637_spacing.py`.
Second commit on the branch; full gate green (append-only clean — new test file only).

## Follow-up — 2026-07-27 (drop source field)

User: drop the "source — engine-advertised…/N local cases" line from the benchmark card.
Removed the `source` field and the `_benchmark_source` helper; updated two same-session
unmerged OME-635 benchmark assertions (`--skip-append-only`). Third commit on the branch.