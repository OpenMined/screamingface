---
ticket: OME-623
stack: url4-cloud
status: done
started: 2026-07-26
finished: 2026-07-26
---

# OME-623 — surface WS pump failures instead of streaming heartbeats forever

## Intent

A client that attaches with an out-of-range `from_sequence` (e.g. `0`) gets **heartbeats
forever**: no frames, no error frame, no close, nothing in the logs. Reproduced live on kind —
`from_sequence` omitted and `1` both deliver the full frame set; `0` delivers nothing while the
run itself succeeds and every frame lands in JetStream.

Three independent defects compound:

1. `AttachData.from_sequence` has no lower bound, so `0` validates as a legitimate frame and no
   nack is emitted.
2. `NatsBus` turns it into `ConsumerConfig(deliver_policy=BY_START_SEQUENCE, opt_start_seq=0)`;
   JetStream requires >= 1 and rejects the consumer.
3. `Bridge._pump` is a bare `ensure_future` with **no done-callback**, so that exception is
   swallowed entirely — while the writer keeps heartbeating, so the connection looks healthy.

`nats_bus.py` already documents this exact shape for a *different* trigger ("because
`Bridge._pump` is a bare task with no done-callback, that failure is silent: the client then sees
heartbeats forever") and fixes only that trigger. The underlying silent-task hazard was never
closed, so a second trigger reaches the same dead end.

Unit tests cannot catch it: `InMemoryBus.subscribe` computes `cursor = 1 if from_sequence is None
else from_sequence` and filters `seq >= cursor`, so `0` matches everything and delivers normally.
The test double and the production adapter **disagree on this input**.

## Planned changes

Defence in depth — the pump fix alone closes every trigger; the other two stop this one at the edge.

- `shared/protocol/src/url4_streaming_protocol/signals.py` — constrain
  `AttachData.from_sequence` to `ge=1` (CloudEvents sequences are 1-based). A bad value then
  fails `InboundFrameAdapter` validation, so the existing `_parse_inbound` -> `invalid_frame`
  nack path handles it and the client learns immediately.
- `backend/src/url4_cloud/ws/bridge.py` — attach a done-callback to the `_pump` task that
  enqueues an `ErrorEvent` when the task dies with an exception. Ignores `CancelledError`
  (normal on re-attach and teardown). The callback only enqueues — the writer stays the sole
  `ws.send` caller, preserving the single-writer invariant.
- `shared/bus/src/url4_cloud_nats/memory.py` — reject `from_sequence < 1` with `ValueError` so
  the in-memory double stops diverging from JetStream on this input. This is the root cause of
  why the suite could not catch the bug.

## Test plan (RED first)

- `AttachData(from_sequence=0)` and `-1` raise `ValidationError`; `1` and `None` still construct.
- A WS client sending `attach {from_sequence: 0}` receives an `ai.url4.error` frame with code
  `invalid_frame` (not silence).
- A pump that raises a non-cancellation error causes an `ai.url4.error` frame to reach the
  client — asserted with a bus double whose `subscribe` raises, so it covers *any* pump failure,
  not just this trigger.
- Re-attach still cancels the previous pump **without** emitting a spurious error
  (`CancelledError` must stay silent) — guards the regression the callback could introduce.
- `InMemoryBus.subscribe(topic, 0)` raises `ValueError`; `1`/`None` behave as before.

## Acceptance

An invalid `from_sequence` produces a prompt `invalid_frame` nack rather than silence; any pump
exception surfaces as an `ai.url4.error` frame; re-attach stays silent; the in-memory double and
JetStream agree on out-of-range input; suite green.

## Outcome

- **Actual files:** all three planned source changes, plus two the plan missed:
  - `shared/protocol/.../signals.py` — `AttachData.from_sequence` gains `ge=1`.
  - `backend/.../ws/bridge.py` — `_resubscribe` attaches `_on_pump_done`; the callback nacks any
    non-cancellation pump death as `stream_failed`, naming the exception CLASS only.
  - `shared/bus/.../memory.py` + `nats_bus.py` — both call the guard.
  - **`shared/bus/.../bus.py` (unplanned)** — the guard landed on the PORT as
    `validate_from_sequence`, not duplicated per adapter. The whole bug was the two adapters
    disagreeing; one shared definition is what actually prevents a recurrence.
  - **`apps/url4-cloud/docs/protocol.md` (unplanned)** — §5.5 enumerated
    `code ∈ {invalid_frame, unsupported}`. Adding `stream_failed` is a protocol-surface change,
    so the contract had to say so, including why it stays advisory (a fresh `attach` rebuilds the
    subscription, so the failure is recoverable in place) and why it omits broker text.
  - Tests: `tests/unit/test_attach_from_sequence_bounds.py`,
    `tests/unit/test_ws_pump_failure_surfaces.py` (12 tests).
- **Commits:** see the OME-623 commit on `OME-587-url4-cloud-engine-integration`.
- **Gates:** `run_gates.py url4-cloud` — **ALL GATES GREEN** (append-only · ruff · ruff format ·
  pyright · pytest+coverage). Suite **288 passed / 6 skipped**, coverage **97.61%** vs the 80%
  floor; baseline before this unit was 276 passed, so the 12 new tests are the delta.

## Deviations

- **Tests went into NEW files rather than being appended** to `test_ws.py` / `test_protocol.py` /
  `test_nats_bus.py`. The first gate run failed the append-only check: it flags ANY `M` on a path
  matching `test_globs`, even a pure addition (my diff was +117/−0 — zero deletions). Rather than
  weaken the gate, I followed the house precedent — `test_nats_bus_subscribe_ensures_stream.py` is
  a self-contained one-behaviour file from an earlier cycle, which is how this repo satisfies
  rule 5. The new files therefore define their own fixtures instead of importing across test
  modules. Cost: a little duplicated setup. Benefit: the gate stays strict and the files stay
  independent.
- **A `type: ignore` pair was removed rather than kept.** `[override]` on the test fake turned out
  unnecessary; the `[attr-defined]` on `aclose` was real, so the test was rewritten to assert a
  bounded `TimeoutError` instead — which is a *better* assertion anyway, since it proves the value
  was accepted AND the subscription is live, without reaching for an untyped attribute.
- **Environment finding, not a code change.** The gate's `uv run pytest` kept resolving a
  DIFFERENT pytest (9.0.2, no `pytest-cov`) than `.venv` holds (9.1.1). Root cause: this worktree
  was renamed from `url4-integration`, so every `.venv/bin/*` console script carried a stale
  ABSOLUTE shebang pointing at a now-missing interpreter; `uv run` fell through to the linuxbrew
  pytest on PATH. Recreating the venv fixed it, and is what turned the pytest gate green.
  [[OME-624]] hit the same symptom first and recorded it only as an unexplained "local tooling
  quirk"; its ledger has since been amended with this root cause.
- No schema/model change, so stack rule S1 (migrations) does not apply.
