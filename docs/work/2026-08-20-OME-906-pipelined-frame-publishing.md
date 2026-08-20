---
ticket: OME-906
stack: url4, screamingface-engine
status: in_progress
started: 2026-08-20
finished:
---

# OME-906 — Pipelined frame publishing for the Runner event bridge

## Intent

A DRACO Evaluation fails when many model calls return from the cache at once. The Runner
publishes one frame for each broker round trip. The engine makes events at CPU speed.
Therefore the bridge between them overflows its hard cap and the Evaluation stops. The
Evaluation was correct.

This unit separates two ideas that `EventPublisher.publish` holds together: the transport
accepted the frame in order, and the broker made the frame durable. The adapter then keeps
a bounded number of acknowledgements in flight, and the lifecycle waits for them at the
boundary where it decides the outcome of the run.

## Planned changes

- `packages/url4/src/url4/streaming/interfaces/stream.py` — add `EventPublisher.flush`
  with a default body that does nothing. Extend the `publish` contract.
- `packages/url4/src/url4/streaming/lifecycle.py` — call `flush` at the end of
  `_publish_execution` and after the terminal frame in `_terminate`.
- `apps/screamingface-engine/src/screamingface_engine/adapters/jetstream.py` — make
  `JetStreamPublisher` use `publish_async`, record the first failed acknowledgement, and
  implement `flush`. Set `publish_async_max_pending` explicitly.
- `apps/screamingface-engine/src/screamingface_engine/runner/executor.py` — record the
  `_Bridge` high-water mark. Report it in the overflow message and in `_closing_logs`.
- Tests in `packages/url4/tests/`, `apps/screamingface-engine/tests/unit/` and
  `apps/screamingface-engine/tests/integration/`.

## Test plan

Written RED first, per step:

1. The default `flush` returns `None`. `flush` is not abstract.
2. `flush` runs after the result frame. A raising `flush` produces
   `Terminated(status="failed")`. Cancellation still produces `stopped`.
3. The bridge high-water mark appears in the overflow message. `_closing_logs` reports it
   only above the soft cap.
4. `publish` does not wait for its acknowledgement. The call order is kept. A rejected
   acknowledgement raises on the next `publish` and on `flush`. A second `flush` does not
   raise the same error. A cancelled future is ignored.
5. A DRACO-shaped burst of 700 or more cached calls completes against a pipelined
   publisher fake. The frames stay in order and none is lost. A publisher that never
   answers fails the run with a bounded buffer.

## Acceptance

The six criteria of OME-906:

- A deterministic regression covers a DRACO-shaped cache burst with a delayed publisher.
- A 100-Case DRACO Fusion Evaluation with 700 or more cached Judge responses completes.
- The started, span, cost, result and terminal frames stay in order and lossless.
- A failed acknowledgement fails the Evaluation with a correct terminal error.
- The memory stays bounded when the publisher stalls without end.
- The bridge records the high-water mark.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
