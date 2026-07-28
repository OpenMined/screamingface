---
ticket: OME-550
stack: url4-cloud
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-550 — Use JSON-Schema `examples` (2020-12) not singular `example`

## Intent

The `CostUsageData` component annotation used the singular `example` keyword, which is not a
JSON-Schema-2020-12 / OpenAPI-3.1 keyword (validators ignore it). Switch to the conformant
`examples` array so the Scalar sample pane is fed by a spec-legal keyword in both the OpenAPI 3.1
and AsyncAPI 3.0 documents.

## Planned changes

- `src/url4_cloud/schemas/protocol_schemas.py` — `{"example": COST_USAGE_EXAMPLE}` →
  `{"examples": [COST_USAGE_EXAMPLE]}` (+ comment).
- `tests/unit/test_docs_ops.py` — tighten `test_cost_usage_data_carries_an_example` (rename →
  `_carries_examples`) to REQUIRE the `examples` array and REJECT the singular `example`
  (authorized contract tighten under this ticket).
- module docstring — "carries an example" → "carries examples".

## Test plan

- RED: assert `"example"` NOT in the CostUsageData component AND `"examples"` present (a non-empty
  list) whose `[0]` has `scope == "self"` and `cost.total_usd == "0.0435"`. Fails against the
  current singular-`example` code.

## Acceptance

- `CostUsageData` carries `examples` (array), not `example`; OpenAPI 3.1 + AsyncAPI 3.0 validate;
  `run_gates.py url4-cloud` green.

## Outcome

- **Actual files:** `src/url4_cloud/schemas/protocol_schemas.py` (`example` → `examples: [...]`
  + WHY comment); `tests/unit/test_docs_ops.py` (test `_carries_an_example` → `_carries_examples`,
  now requires the `examples` array and rejects singular `example`; module docstring updated).
  No protocol-model change.
- **Commits:** see the OME-550 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` GREEN (ruff · format · pyright · pytest
  118 passed · cov ≥ 80). `--skip-append-only` covers the authorized DOC-GATE tighten (a
  strengthen — requires the conformant keyword; nothing weakened).
- **Deviations:** the existing test already tolerated both keywords, so the RED step *tightened*
  it (assert `examples`, reject `example`) rather than adding a new test.
