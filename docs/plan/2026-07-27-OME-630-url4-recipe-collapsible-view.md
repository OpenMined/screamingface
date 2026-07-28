---
title: Collapsible syntax-highlighted url4 recipe view — plan
ticket: OME-630
status: approved
date: 2026-07-27
spec: docs/spec/2026-07-27-OME-626-sdk-display-contract.md
---

# Collapsible syntax-highlighted url4 recipe view — plan

Display-only enhancement under the OME-626 display contract. One RED → GREEN → gate cycle.

## Design

New module `src/screamingface/_url4_format.py`:

- `recipe_details_html(url4: str) -> str` — the collapsible recipe block:
  - `<details class='sf-url4'>` (no `open` → collapsed by default).
  - `<summary>`: "url4 recipe" label + node count + a copy `<button>` whose fixed inline JS
    (`event.stopPropagation()` + `navigator.clipboard.writeText(<raw>.textContent)`) reads the
    raw url4 from a sibling hidden `<pre class='sf-url4__raw'>` — no recipe text in the JS, so
    no injection and no JS-string escaping.
  - body: the structured view + the visible/selectable raw `<pre>` as copy source and fallback.
- `_structured_html(url4)`: `node = url4.build(url4)`; if `Expression`, render each `Source`;
  per `Source` emit name/weight and, for a `RelExpr`, route (`path`), params, context, and
  intent (`Text.value` unquoted, else `render`). Unknown node kinds fall back to
  `url4.render(node)`. Wrap the whole thing in `try/except url4.Url4Error` → return `None` so the
  caller shows the raw string only. (WHY: a display path must never raise; failing to the real
  raw url4 is honest, not a security fail-open.)

`_card_display._recipe_html(url4)` becomes a thin delegate to `recipe_details_html`. CSS
(`.sf-url4*`) appended to `_card_display._STYLE`; route accent = `--sf-gain`, labels/params =
`--sf-ink-2/3`, intent block = `--sf-surface`. All injected text HTML-escaped.

## Critical files

- New: `src/screamingface/_url4_format.py`
- Edit: `src/screamingface/_card_display.py` (`_recipe_html` delegate + `.sf-url4` CSS)
- Test: new `tests/test_ome630_url4_view.py`

## Verification

`uv run .claude/scripts/run_gates.py screamingface` green (stash the pre-existing unrelated
notebook WIP first). Manual: render a Fusion in the notebook, confirm collapsed → expand →
readable, copy button copies the exact url4.
