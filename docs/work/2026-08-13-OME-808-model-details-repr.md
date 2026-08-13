---
ticket: OME-808
stack: screamingface
status: in_progress   # planned | in_progress | done | blocked
started: 2026-08-13
finished:
---

# OME-808 — repr + notebook card for ModelInfo and ModelDetails

## Intent

`client.models.list()` returns `ModelInfo` and `client.models.get(...)` returns
`ModelDetails` (frozen dataclasses in `packages/screamingface/src/screamingface/discovery.py`).
Neither defines `__repr__`, so both fall back to the dataclass default — for `ModelDetails`
an unreadable wall of 15 fields including three `MappingProxyType` mappings of full nested
reprs. Give both a compact constructor-style `__repr__`, and give the richer `ModelDetails`
an SFDS notebook card (`_repr_html_`), matching the rest of the SDK (`Model`, `Benchmark`,
`Leaderboard`, `Report`). The `Model` recipe already has both reprs and is not touched.

## Planned changes

- `src/screamingface/discovery.py` — add `ModelInfo.__repr__`; add `ModelDetails.__repr__`
  and `ModelDetails._repr_html_` (lazy import of the card helper).
- `src/screamingface/_ui/cards.py` — add `model_details_card_html()`; add `ModelDetails`
  to the `TYPE_CHECKING` import.
- `tests/test_model_parameter_discovery.py` — repr assertions for `ModelInfo` +
  `ModelDetails` (incl. a stale/degraded flag case).
- `tests/test_rich_display.py` — `ModelDetails` card test (real escaped fields present,
  `_FABRICATED` terms absent).

No schema change (S1 n/a). No public-interface change — `ModelInfo`/`ModelDetails` already
exported.

## Test plan

- RED first. `repr(ModelInfo(...))` and `repr(ModelDetails(...))` exact-string assertions
  against the existing `_model_parameter_fixtures` (3 params / 1 tool / 1 transport, fresh).
- Boundary: a `stale=True` (and a `degraded=True`) `ModelDetails` surfaces the flag; fresh
  shows neither.
- Card: `_repr_html_()` contains escaped `id`/`provider`/`scope`/`fresh`; loops the
  `_FABRICATED` tuple asserting each banned metric term is absent.

## Acceptance

- `repr(ModelInfo(...))` == `ModelInfo('<id>', provider='<p>', parameters=N, tools=M)`
- `repr(ModelDetails(...))` == `ModelDetails('<id>', provider='<p>', scope='<s>', parameters=N, tools=M, transport=K)` (+ flags only when set)
- `ModelDetails._repr_html_()` renders a card and passes the `_FABRICATED` guard.
- Full screamingface gate suite green (coverage ≥95%).

## Outcome

- **Actual files:** exactly as planned —
  `src/screamingface/discovery.py` (`ModelInfo.__repr__`; `ModelDetails.__repr__` +
  `_repr_html_`), `src/screamingface/_ui/cards.py` (`model_details_card_html` +
  `TYPE_CHECKING` import), `tests/test_model_parameter_discovery.py` (3 repr tests, incl.
  parametrized stale/degraded), `tests/test_rich_display.py` (1 card test).
- **Commits:** branch `OME-808-model-details-repr` — `feat(screamingface): repr + notebook card for model discovery values` (final squash-merge sha recorded in the Linear close comment).
- **Gates:** `run_gates.py screamingface` — ALL GREEN (append-only · ruff · ruff format ·
  pyright · pytest --cov=screamingface --cov-fail-under=95 · notebook determinism ·
  uv build · distribution check).
- **Deviations:** none affecting code. The fresh worktree `.venv` first failed pyright on
  unresolved `ipywidgets`/`IPython` in untouched `_ui` files; resolved with
  `uv sync --extra notebook` (the step CI runs before pyright) — no gate weakened.
