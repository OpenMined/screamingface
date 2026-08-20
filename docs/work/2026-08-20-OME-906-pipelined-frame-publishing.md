---
ticket: OME-906
stack: url4, screamingface-engine
status: blocked
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

## BLOCKED — the measured root cause is not the one in the issue

Steps 1 to 4 of the plan are committed and green. Step 5, the DRACO regression, stopped the
unit: the reproduction shows that pipelined publishing does NOT raise the overflow ceiling.

### What was measured

A DRACO-shaped fan-out (N cache-hit case nodes under one fusion root, each reporting usage
and a `hit` model response) driven through the REAL `_Bridge` and the REAL
`lifecycle.run` publish loop. Two publisher fakes: `serial` waits per frame, the old shape;
`pipelined` writes through and waits at the barrier, the new shape.

**Peak backlog against publish latency, N = 1500, node I/O 1 ms:**

| Publish delay | serial: time / peak | pipelined: time / peak |
|---|---|---|
| 0 ms | 0.64 s / 4497 | 0.59 s / 4461 |
| 0.1 ms | 3.80 s / 4499 | 0.58 s / 4467 |
| 1 ms | 3.83 s / 4499 | 0.59 s / 4458 |
| 10 ms | 31.05 s / 4499 | 0.59 s / 4461 |

The publish delay moves over a 100x range. **The peak does not move.**

**Peak against run size, publish delay 0, node I/O 1 ms:**

| N | frames | peak | result |
|---|---|---|---|
| 500 | 1007 | 1224 | ok |
| 1000 | 2007 | 2700 | ok |
| 2000 | 4007 | 5964 | ok |
| 3000 | 5470 | — | `BridgeOverflowError` |

Peak is approximately 3N — near the whole event count of the run — and it overflows on run
SIZE alone, with a publisher that costs nothing.

### What this means

- The issue states the cause is "cached model responses produce events much faster than the
  serial publish path drains them". The drain rate is not the governing term. The bridge
  holds nearly every event a run emits, because the drain task cannot interleave with a
  fan-out producer on the same event loop, whatever the publisher costs.
- Acceptance criterion 2 is therefore NOT met by the committed work. A run of DRACO's size
  (about 3500 nodes, 8192 events) still overflows.
- The committed work is still worth keeping on its own merits: 31 s to 0.59 s at a 10 ms
  round trip is a 50x wall-clock gain, and the high-water mark from step 3 is what made this
  measurable at all. Neither is the fix the issue asks for.
- "Raise the 8192 cap", which the issue rejects as a delay tactic, is no longer obviously
  wrong. The cap is the binding constraint and the publisher is not. 8192 buffered
  `ObservationEvent`s is a few MB; a count-based cap chosen against an unmeasured cause is
  the thing to revisit, ideally as a memory bound.

### Outcome so far

- **Actual files:** `packages/url4/src/url4/streaming/interfaces/stream.py`,
  `packages/url4/src/url4/streaming/lifecycle.py`,
  `apps/screamingface-engine/src/screamingface_engine/runner/executor.py`,
  `apps/screamingface-engine/src/screamingface_engine/adapters/jetstream.py`,
  `apps/screamingface-engine/src/screamingface_engine/testing/mock_runner.py`,
  tests: `tests/unit/test_publish_durability.py`,
  `tests/unit/test_jetstream_pipelining.py`, `tests/unit/test_url4_executor.py`,
  `tests/unit/_fakes.py`.
- **Commits:** `ea829212` port + lifecycle barrier · `a7437086` high-water mark ·
  `32b5ba7d` adapter pipelining.
- **Gates:** url4 ALL GREEN; screamingface-engine ALL GREEN (1880 passed, 5 skipped).
- **Deviations:**
  1. `url4/streaming/*` is omitted from url4's own coverage and its tests live in the engine
     suite by design, so the plan's "tests in packages/url4/tests/" was wrong. All tests
     went to `apps/screamingface-engine/tests/`.
  2. Failures are harvested by reaping settled futures, not by `add_done_callback`. A
     callback runs through `loop.call_soon`, so a `flush` that does not await would miss it.
  3. `_acks` is an insertion-ordered dict, not a set. A set made "first failure" mean
     whichever future hash order yielded — it passed alone and failed in suite order.
  4. `_JetStreamEventStream.publish` in `tests/unit/_fakes.py` gained a flush. That is a
     prior fixture, so it was an approved rule-5 change, landed with
     `run_gates.py --skip-append-only` once.
  5. Step 5 not done — see above.
