---
title: Recipe full-form pretty-print + Fusion member/reducer detail — plan
ticket: OME-635
status: approved
date: 2026-07-27
spec: docs/spec/2026-07-27-OME-626-sdk-display-contract.md
---

# Recipe full-form pretty-print + Fusion member/reducer detail — plan

Display-only, under the OME-626 contract. Two coordinated changes.

## 1. url4 recipe → full-form reflow in a `<pre>`

`_url4_format.py`:
- `_pretty_url4(text)`: single left-to-right pass. Track `in_quote` and backslash escapes
  (url4 quotes with `\\` and `\'`). Outside quotes: `(`/`{` → append + indent+1 + newline
  (but keep an empty `()`/`{}` inline); `)`/`}` → newline + indent-1 + append; `,` → append +
  newline; skip a single space immediately after a break. Everything else verbatim → the exact
  url4 is preserved, only whitespace added.
- `recipe_details_html(url4)`: `<details class='sf-url4'>` (collapsed) → `<summary>` with a
  copy `<button data-url4="{escape(raw, quote=True)}" onclick="…writeText(getAttribute('data-url4'))">`
  → `<pre class='sf-url4__pre'>{escape(pretty)}</pre>`. No `url4.build`, no hidden element.

## 2. Fusion card: members & reducer detail (collapsed)

`_card_display.py` `_fusion_detail_html(fusion)`:
- `<details class='sf-detail'><summary>members & reducer</summary>…`
- per member: `<div>` name + route; if a `Model`, its prompt and params; if a nested `Fusion`,
  a "nested fusion — see its own card" note.
- reducer row: kind; if a Model reducer, its model/prompt/params; MajorityVote → "deterministic".
- Embed in `fusion_card_html` between the grid and the recipe.

CSS: `.sf-url4__pre` (pre-wrap, overflow-wrap:anywhere, mono, no host background) replaces the
per-node classes; add `.sf-detail*`. Reuse `--sf-*` tokens; no raw colors.

## Critical files

- Edit: `src/screamingface/_url4_format.py`, `src/screamingface/_card_display.py`
- Test: new `tests/test_ome635_recipe_fullform.py`

## Verification

`uv run .claude/scripts/run_gates.py screamingface` green (stash pre-existing notebook WIP).
Manual: render a Fusion — recipe shows full url4 indented in a `<pre>`, copy copies exact raw;
"members & reducer" expands to prompts + params.
