---
title: _repr_html_ cards for Connection, Case, and Rubric — plan
ticket: OME-628
status: approved
date: 2026-07-27
spec: docs/spec/2026-07-27-OME-626-sdk-display-contract.md
---

# _repr_html_ cards for Connection, Case, and Rubric — plan

Extends OME-626 under the same governing display contract (honest advertised/authoring fields
only; injected text HTML-escaped; reuse the `.sf-ui` token block). One RED → GREEN → gate
cycle; the three cards are independent and share the existing `_card_display` helpers.

## Design

Add three pure renderers to `src/screamingface/_card_display.py`, mirroring the existing
`model_card_html` / `benchmark_card_html` shape (head + `sf-card__grid` of `_field`s):

- `connection_card_html(connection)` — title = display_name, kicker "connection"; fields:
  provider, status (humanized), auth method, account label, advertised auth methods.
- `case_card_html(case)` — title = id, kicker "case"; fields: input (wide), reference
  (JSON, wide), metadata (JSON, wide). Render reference/metadata via `json.dumps` then escape.
- `rubric_card_html(rubric)` — title = model, kicker "rubric grader"; fields: passes, params,
  prompt (wide). Reuse `_params_text` for params.

Wire a lazy-importing `_repr_html_` onto `Connection` (`connections.py`), `Case`
(`benchmark.py`), and `Rubric` (`graders.py`). No custom `__repr__` (keep the dataclass
default so existing repr assertions stay green).

## Critical files

- Edit: `src/screamingface/_card_display.py`, `connections.py`, `benchmark.py`, `graders.py`
- Test: new `tests/test_ome628_value_cards.py`

## Verification

`uv run .claude/scripts/run_gates.py screamingface` green from the repo root; the same
pre-existing unrelated notebook WIP must be stashed to prove a clean whole-tree gate.
