---
ticket: OME-520
stack: url4-cloud
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-520 — url4_cloud_runner Job entrypoint

## Intent
The Runner Job entrypoint (spec §1.1/§9; docs/protocol.md): execute a url4 expression and publish
the CloudEvents lifecycle to the `Bus` (OME-516) — `Started` → (`Log`/`Span`/`CostUsage{self}` as
available) → `CostUsage{subtree}` → `Result` → `Terminated{succeeded}`; on any exception
`Terminated{failed, error=ErrorInfo}`. The envelope (uuid4 `id`, `source=/trace/<topic>/node/<node>`,
`subject=topic`, monotonic string `sequence`, `time`) is the Runner's responsibility.

## Design
- `run(bus, executor, topic, url4, *, node="root")` — pure orchestration with **injected** `Bus`
  and `Executor`, so tests drive an `InMemoryBus`/recording bus + a stub executor (NO real
  url4/network — INFRA rule). The real url4-backed executor is the deferred OME-446 seam.
- `Executor` port (`executor.py`): `execute(url4) -> AsyncIterator[ExecStep]` where `ExecStep` is a
  telemetry payload (`LogData`/`SpanData`/`CostUsageData`) streamed "as available", then exactly one
  terminal `Completed(result, subtree_cost)`. PEP 525 forbids an async-generator return value, so
  the outcome rides as the final yielded item.
- `MockExecutor` — interim §8-valid fake (one Log, one GenAI Span, one `CostUsage{self}`, then a
  `Completed`) so `url4-cloud-runner` runs end-to-end for the compose e2e (OME-524) before OME-446.
- `_error_info(exc)` duck-types `.code`/`.permanent` (url4 `Url4Error` shape) without importing
  `url4` — keeps the runner dependency-free.
- `main()` reads env (`URL4_CLOUD_TOPIC`/`_EXPRESSION`/`_NATS_URL` — the docker adapter's contract),
  wires `NatsBus` + `MockExecutor`, `asyncio.run(run(...))`. The pure `_params_from_env` helper is
  unit-tested; the NatsBus + event-loop glue is `# pragma: no cover` (INFRA rule).

## Planned changes
- `src/url4_cloud_runner/executor.py` — `Executor`/`ExecStep`/`Telemetry`/`Completed` + `MockExecutor`
- `src/url4_cloud_runner/publish.py` — `run()` + envelope emitter + `_error_info`
- `src/url4_cloud_runner/__main__.py` — `main()` + `_params_from_env` (replaces the stub)
- `src/url4_cloud_runner/__init__.py` — export the seam
- `tests/unit/test_runner.py`

## Test plan
- success (MockExecutor): published order is `started, log, span, cost.usage{self}, cost.usage{subtree},
  result, terminated{succeeded}`; `sequence` strictly monotonic; envelope `id`/`source`/`subject`/`time`
  set; the pre-result cost has `scope="subtree"`.
- failure (stub raises mid-stream): last event is `terminated{failed}` with `error` mapped from the
  exception (`code`/`permanent` duck-typed; generic exception → `internal_error`/`permanent=True`).
- executor ends without `Completed` → `terminated{failed}`.
- `_params_from_env`: required vars present → params; missing → clear config error.
- round-trip through `InMemoryBus.subscribe` re-assigns stream sequences 1..N in order.

## Acceptance
- Gates green (`run_gates.py url4-cloud`); `run` publishes the exact lifecycle with a monotonic
  sequence; failure always terminates with an `ErrorInfo`.

## Outcome
- **Actual files:** `src/url4_cloud_runner/{executor,publish,__main__,__init__}.py` +
  `tests/unit/test_runner.py` (11 tests). `__main__.py` replaced the OME-520 stub.
- **Design as planned.** `run(bus, executor, topic, url4, *, node="root")` orchestrates; `Executor`
  is a streaming port (`AsyncIterator[ExecStep]`) yielding telemetry then one terminal `Completed`
  (PEP 525 forbids an async-generator return value). Envelope stamped by `_Sequencer` (uuid4 hex id,
  `/trace/<topic>/node/root` source, monotonic string sequence, UTC time). The pre-result cost is
  forced to `scope="subtree"` via `model_copy` (invariant by construction, not by trust).
- **Robustness beyond the ask:** `run` calls `bus.ensure_stream` first (NatsBus.publish does not
  auto-create); an executor that streams no `Completed` funnels to `Terminated{failed}`.
- **Gates:** `run_gates.py url4-cloud` ALL GREEN (ruff · format · pyright · pytest+cov). Runner
  package coverage 100%; suite aggregate ≥ 80%.
- **Deviations:** the real url4-backed executor is the deferred OME-446 seam — `main()` wires the
  interim §8-valid `MockExecutor` so `url4-cloud-runner` runs end-to-end for the compose e2e
  (OME-524). No `url4` dependency added (exception mapping duck-types `code`/`permanent`).
