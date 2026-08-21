# OME-692 — Show authoritative live cache progress (implementation plan)

Authority: `docs/spec/2026-08-21-OME-692-live-cache-progress.md`.

## Interface and seam

Widen the existing public Event seam in `events.py` with the two optional Engine fields. Decode
them in the existing strict CloudEvent adapter; do not introduce a second cache DTO or parser.

Keep all aggregation behind `_EvaluationProgress`. Callers and the notebook view consume one small
interface: the aggregate cache counts and derived hit rate. `_EvaluationProgress` stores the latest
counts per Run so final summary Logs can replace live Span-derived observations without double
counting.

Render the derived values through the existing `_stats_html` table. The view performs formatting
only and contains no cache policy.

## TDD order

1. Extend public Event-value tests for valid and invalid cache status/reason.
2. Extend Engine contract tests to require preservation of both fields.
3. Add progress-fold tests for live counting, bypass denominator semantics, multi-Run aggregation,
   and authoritative summary replacement.
4. Add HTML tests for the fourth cache cell, unknown state, and receipt formatting.
5. Implement the minimal Event, decoder, fold, and view changes.
6. Run focused tests, the complete `packages/screamingface` suite, and the `screamingface` gate set.

## Planned files

- `packages/screamingface/src/screamingface/events.py`
- `packages/screamingface/src/screamingface/_engine/contract.py`
- `packages/screamingface/src/screamingface/_ui/evaluation_state.py`
- `packages/screamingface/src/screamingface/_ui/evaluation_view.py`
- `packages/screamingface/tests/test_event_values.py`
- `packages/screamingface/tests/test_engine_contract.py`
- `packages/screamingface/tests/test_evaluation_progress_panel.py`
- OME-692 spec, plan, task mirror, and work ledger

