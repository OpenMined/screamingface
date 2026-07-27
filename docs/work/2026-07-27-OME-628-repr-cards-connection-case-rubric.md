---
ticket: OME-628
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-628 — _repr_html_ cards for Connection, Case, and Rubric

## Intent

Follow-on polish to OME-626. Three more public value objects print a bare dataclass repr in a
notebook; give each a branded `_repr_html_` card using the same renderers and honesty contract
as OME-626. Governing spec: `docs/spec/2026-07-27-OME-626-sdk-display-contract.md`
(honest advertised/authoring fields only — no fabricated metrics; injected text HTML-escaped).

## Planned changes

- `src/screamingface/_card_display.py` — add `connection_card_html`, `case_card_html`,
  `rubric_card_html` (pure functions, reuse `_STYLE`, `_field`, `_recipe_html`).
- `src/screamingface/connections.py` — `Connection._repr_html_` (lazy import).
- `src/screamingface/benchmark.py` — `Case._repr_html_` (lazy import).
- `src/screamingface/graders.py` — `Rubric._repr_html_` (lazy import).
- `tests/test_ome628_value_cards.py` — new tests.

## Test plan (RED first)

- `Connection._repr_html_` shows display_name, provider, status, auth_method, account_label;
  escapes an injected account_label; no fabricated metrics.
- `Case._repr_html_` shows id, input, reference, metadata; escapes an injected input.
- `Rubric._repr_html_` shows model, passes, prompt, params; escapes an injected prompt.
- Text `__repr__` unchanged (dataclass default) — existing repr assertions stay green.

## Acceptance

- Each of the three renders a branded card in a notebook; no fabricated data; text escaped.
- Full `screamingface` gates green.

## Outcome

- **Actual files:** as planned. Added `connection_card_html` / `case_card_html` /
  `rubric_card_html` (+ `_json` helper) to `_card_display.py`; added `_repr_html_` to
  `Connection` (`connections.py`), `Case` (`benchmark.py`), and `Rubric` (`graders.py`).
  New `tests/test_ome628_value_cards.py` (6 tests).
- **Commit:** feat(screamingface): add repr cards for Connection, Case, Rubric (Refs: OME-628).
- **Gates:** `run_gates.py screamingface` → ALL GATES GREEN. Full SDK suite 733 + 6 new = 739.
- **Deviations:** none for the code. As in OME-626, the 7 pre-existing unrelated example
  notebooks (OME-400 WIP) were `git stash`-ed to prove a clean whole-tree gate, only the
  OME-628 files were committed, and the stash was restored.
