---
ticket: OME-630
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-630 — collapsible, syntax-highlighted url4 recipe view

## Intent

The Model and Fusion cards show the compiled `url4` recipe as one long unreadable line.
Parse it with `url4.build(...)` and render a structured, syntax-highlighted, collapsed-by-default
view with a copy button for the exact raw string. Display-only; governed by the OME-626 display
contract (honest fields, HTML-escaped, `.sf-ui` tokens).

## Design

- New `_url4_format.py` (keep `_card_display.py` under 450 lines): `recipe_details_html(url4)` →
  a `<details>` (collapsed) whose body is the structured AST view; a copy button reads the raw
  url4 from a hidden `<pre>` (fixed JS, no interpolation → no injection, no escaping headaches).
  Parse via `url4.build`; walk `Expression.sources`; per `Source` show name/weight, and for a
  `RelExpr` the route/params/context/intent; `StructObject.raw` and other nodes fall back to
  `url4.render(node)`. On `url4.Url4Error`, fall back to the raw string (today's behavior).
- `_card_display._recipe_html` delegates to the new formatter (Model + Fusion cards use it).
- CSS: add `.sf-url4*` classes to `_STYLE` (route = gain accent, params/labels = ink-2/3,
  intent = surface block); no raw colors.

## Test plan (RED first)

- A compiled Fusion recipe renders a `<details>` without `open` (collapsed); contains a copy
  button; the raw url4 appears verbatim (copy source) and each member route + a param key show
  in the structured view; intent text is present and HTML-escaped.
- A recipe whose intent contains HTML is escaped in the structured view.
- `recipe_details_html("not a url4 %%%")` (unparseable) falls back to the raw string inside the
  details and does not raise.
- Model card and Fusion card HTML both contain the `<details class='sf-url4'>` wrapper.

## Acceptance

- Recipe is collapsed by default, expands to a readable structured view, copy button copies the
  exact url4, unparseable input degrades to raw. Full `screamingface` gates green.

## Outcome

- **Actual files:** as planned. New `src/screamingface/_url4_format.py`
  (`recipe_details_html` + AST walker over `url4.build`); `_card_display._recipe_html`
  delegates to it and `.sf-url4*` CSS added to `_STYLE`. New `tests/test_ome630_url4_view.py`
  (5 tests).
- **Commit:** feat(screamingface): render url4 recipe as a collapsible view (Refs: OME-630).
- **Gates:** `run_gates.py screamingface` → ALL GATES GREEN. Full SDK suite 739 + 5 new = 744.
- **Deviations:**
  - `_source_html` accepts `url4.Node` (not `Source`) and renders any non-Source via the value
    path — `Expression.sources` is typed `Node`; this keeps pyright honest and the display
    crash-proof.
  - Copy button uses fixed inline JS reading the raw recipe from a sibling hidden `<pre>` via
    textContent (no recipe interpolation → no injection/escaping issue). Works in trusted
    notebook output / VS Code / nbconvert; where a frontend strips inline JS the raw `<pre>`
    remains the selectable copy source.
  - As before, the 7 pre-existing unrelated example notebooks (OME-400 WIP) were stashed to
    prove a clean whole-tree gate; only OME-630 files committed; stash restored.
