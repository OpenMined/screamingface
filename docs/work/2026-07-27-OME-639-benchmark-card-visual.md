---
ticket: OME-639
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-639 — elevate the benchmark card to the evaluate/report visual language

## Intent

Bring the Benchmark card up to the polish of the evaluation Report widget
(`_report_display.py`): a clean header + a mono **big-number stat grid** with hairline
dividers and uppercase mono labels, tools as chips, and restyled grader + engine-routes
sections. Brand-compliant (screamingface-design): near-monochrome, square, hairline, mono
labels, light+dark equal; gain reserved for a win (none here).

## Planned changes

- `_card_style.py`: add `.sf-stats` / `.sf-stat` / `.sf-stat__k` / `.sf-stat__v` (mirroring the
  report widget's stat grid), `.sf-chips` / `.sf-chip`, and `.sf-card__meta`.
- `_card_display.py` `benchmark_card_html`: header (title + id meta), a 4-up stat grid
  (aggregator / grader / passes / max tool calls), a tools chip row, a grader section
  (model + params + collapsible prompt, or "deterministic"), and the collapsible engine-routes
  section. Add `_grader_section_body` (model/params/prompt without repeating the kind).
- Tests: new `tests/test_ome639_benchmark_card.py`.

## Test plan (RED first)

- Benchmark card contains `.sf-stats` with labels aggregator/grader/passes/max tool calls and
  the right values (mean, rubric, 5, 12); tools render as `.sf-chip`s.
- Rubric grader section shows the model + collapsible prompt; ExactChoice shows "deterministic".
- No fabricated data; injected text escaped; both prior card tests still pass.

## Acceptance

- Benchmark card visually matches the report language (stat grid, sections, chips). Gates green.

## Outcome

- **Actual files:** `_card_style.py` (added `.sf-card__meta`, `.sf-stats`/`.sf-stat`/`.sf-stat__k`/
  `.sf-stat__v` mirroring the report stat grid + a 2-col mobile breakpoint, `.sf-chips`/
  `.sf-chip`); `_card_display.py` (rewrote `benchmark_card_html` → header + stat grid + tool
  chips + grader section + engine routes; added `_stat`/`_tool_chips`/`_grader_section_body`;
  removed the now-dead `_grader_detail`). New `tests/test_ome639_benchmark_card.py` (5 tests).
- **Commit:** feat(screamingface): elevate benchmark card to the report visual language
  (Refs: OME-639).
- **Gates:** `run_gates.py screamingface --skip-append-only` → ALL GREEN. 758 + 5 = 763.
- **Deviations:** append-only skip — the stat grid shows passes as a value ("5"), so two
  same-session unmerged assertions that expected "N passes" (OME-635, OME-637) were updated to
  `>N</div>`. Brand self-check: near-monochrome (no gain used — a static benchmark encodes no
  win), square, hairline, mono labels, tokens only, light+dark via the shared `.sf-ui` block.