---
title: url4-cloud ↔ url4 engine integration — technical specification
status: implemented (retroactive spec) — shipped on branch `url4-integration`
created: 2026-07-24
author: retroactive SDLC record (post-implementation)
epic: OME-513 (url4-cloud — REST + WebSocket url4 execution runner)
depends_on:
  - OME-446 — url4 SDK execution-observability + traceparent seams (the `packages/url4` half of this change)
commits:
  - e3affad2 — feat(url4): engine observation seam (Observer port + usage sink)   # OME-446
  - 87dec815 — feat(url4-cloud): split backend/runner/shared; engine integration, local mode, aigateway connector + web tools
  - 156bf0a3 — fix(url4-cloud): drop unconfigurable config.port and runner.command helm values
related:
  - docs/spec/2026-07-21-url4-cloud.md            # OME-513 v1 spec (the App this integrates into)
  - docs/spec/2026-07-15-url4-cloud-runner-spec.md # OME-443 reused event/taxonomy model
  - packages/url4/                                 # the engine
  - apps/url4-cloud/                               # the App + Runner
---

# url4-cloud ↔ url4 engine integration — technical specification

## 0. Status

**Implemented.** This spec is written retroactively to give the SDLC record (spec → ledger →
ticket) for work that already shipped on branch `url4-integration` (commits above), per the
owner's instruction to document the branch's purpose. It closes the single gap the OME-513 v1
explicitly deferred (see the epic's own close-out comment): *"OME-446 (real engine channel —
deferred; the runner uses `MockExecutor` until then)."* The runner no longer uses `MockExecutor`.

Per D9 this change is cross-cutting (it touches `packages/url4` **and** `apps/url4-cloud`) and so
splits along landings, not into one mega-ticket:

- **`packages/url4` — the observation seam** (commit `e3affad2`) is the deliverable of **OME-446**
  (url4 SDK execution-observability + traceparent + streaming-transport seams), which pre-existed
  in Backlog parented to OME-513. This spec documents it as the prerequisite; OME-446's own
  state/close is an owner call (it is only partially closed by this seam — see §6).
- **`apps/url4-cloud` — consuming the seam** (commits `87dec815`, `156bf0a3`) is the new
  SDLC unit filed under OME-513 (landing `url4-cloud`). This spec is its design record.

## 1. Purpose & scope

### 1.1 Problem
OME-513 v1 delivered the full url4-cloud control plane (REST + WS + NATS + k8s Jobs + Helm) but
ran a **`MockExecutor`** inside the Runner Job — the telemetry lifecycle it published was
synthetic. url4-cloud could not yet execute a real url4 expression, and `packages/url4` exposed
no observation surface an embedder could subscribe to without coupling the engine core to a
transport or tracing backend.

### 1.2 What this change delivers
Two halves, one contract between them:

- **Half A — engine observation port (`packages/url4`, OME-446).** A dependency-free,
  stdlib-only leaf module `url4.observe` exposing a closed set of pure frozen dataclasses
  (`RunStarted`, `NodeStarted`, `NodeFinished`, `Log`, `Usage`, `RunFinished`) emitted to an
  injected `Observer` protocol as the DAG runs, plus a `ContextVar` usage sink bound per-node so
  context-less world handlers can report model token usage against the current span. The executor
  is wired to emit span lifecycle and to bind/reset the sink around each `resolve`.
- **Half B — url4-cloud consumes it (`apps/url4-cloud`).**
  1. **Distribution split.** The single `src/` tree is restructured into three distributions
     released as **two images**: `backend/` (the stateless App — REST + WS control plane),
     `runner/` (the one-shot execution Job), and `shared/` (the `protocol` + NATS `bus` libraries
     both depend on). Each gets its own `pyproject`/`uv.lock`/`Dockerfile`; the release workflow
     builds backend + runner images in parallel.
  2. **Real `Url4Executor` adapter** (the only module in url4-cloud permitted to import `url4` —
     contract C6). It bridges `url4.observe`'s synchronous, inline `Observer.on_event` callback
     onto the async-generator execution stream the Runner consumes, and publishes the CloudEvents
     lifecycle `Started → Log/Span/CostUsage → CostUsage{subtree} → Result → Terminated` with a
     W3C `traceparent` threaded from the engine's real span tree.
  3. **Local mode.** `url4-cloud local` (and the in-process `JobRunner`) runs the whole protocol
     in-memory — no k8s, no NATS — for development and the headless integration test.
  4. **AIGateway connector + web tools.** `build_aigateway_world` mounts a model route per
     aigateway catalog entry and forwards the caller's identity; when a Tavily key is present it
     runs a bounded `web_search`/`web_fetch` tool-calling loop. The k8s `JobRunner` forwards the
     aigateway base URL, credentials, and the Tavily key into each Job.
  5. **Helm invariants.** Pin `containerPort` to the hardcoded `9108`; remove the
     `config.port` and `runner.command` knobs that never drove anything (`additionalProperties:
     false` now rejects them at install) — commit `156bf0a3`.

### 1.3 Non-goals
Distributing `spawn`/`execute_node`; a persistent trace store beyond JetStream retention; the
remainder of OME-446's listed seams (node-level sub-session stop, a streaming-capable transport
extension point) — those remain open under OME-446.

## 2. Architecture

### 2.1 The contract between the halves — `url4.observe`

`Observer.on_event` is **synchronous and non-blocking by contract**: the executor calls it inline
from its own coroutines, never behind a task or queue (a slow/blocking observer would slow the
run). An observer that raises is **not caught** in the engine — an embedder bug should be loud,
not swallowed — so the exception propagates out of the run exactly like any other node failure.
The module is a **dependency-free leaf** (stdlib only) so the engine core never gains a transport
or tracing-backend dependency merely because an embedder wants to watch a run.

The `ContextVar` usage sink (`current_usage_sink()`) is the escape hatch for **context-less world
handlers**: a connector that does not hold an `ExecutionContext` (e.g. the aigateway connector)
calls it to report `provider`/`model`/`input_tokens`/`output_tokens` against whichever span the
executor currently has bound. The executor binds it around each node's `resolve`, scoped to that
node's own `asyncio.Task` so concurrent siblings never cross-talk.

### 2.2 The sync→async bridge — `Url4Executor`

Because `Observer.on_event` MUST NOT block or await (engine hot path) while the Runner's
`publish` wants to `await` each frame, `Url4Executor` is a classic **sync-producer / async-consumer
bridge**: the synchronous observer callback feeds a queue; the async `execute()` generator drains
it and yields `ExecStep`s. Span identity (`span_id`/`parent_span_id`) is carried out per span as a
`SpanRef` alongside its `Traced` wrapper; `publish` is what turns that identity into the wire
`traceparent`/`tracestate` fields (traceparent PRD §3.2.2) — `Url4Executor` carries only raw ids,
never touching the CloudEvents envelope itself.

### 2.3 Distro / image topology

```
shared/protocol  (url4_streaming_protocol)  ┐
shared/bus       (url4_cloud_nats)          ├── both images
                                           ┘
backend/  (url4_cloud)        → image: url4-cloud-backend   (App: REST + WS + JobRunner)
runner/   (url4_cloud_runner) → image: url4-cloud-runner    (Job: Url4Executor → publish)
```

`runner/` is the **only** distribution that depends on `packages/url4` (C6). `backend/` schedules
Jobs and bridges NATS→WS but never imports the engine.

## 3. Key contracts / invariants

- **C6 — engine isolation.** `url4_cloud_runner.url4_executor` is the only module in url4-cloud
  allowed to import `url4`. Core never imports plugins; wiring is by port (`Executor`), not
  direct import.
- **Observer non-blocking contract.** `on_event` is sync, inline, non-blocking; may raise.
- **One trace tree.** The `traceparent` threaded onto CloudEvents is the engine's real span tree
  (not a synthetic id) — `RunStarted.trace_id`/`root_span_id` and each `NodeStarted.span_id` flow
  through the bridge unchanged.
- **Helm port invariant.** The App serves uvicorn on a hardcoded `0.0.0.0:9108` (`cli.main`) and
  reads no port from its environment; the Runner Job command is pinned in code
  (`jobs.factory.RUNNER_COMMAND`) with no env override. `containerPort` is pinned to `9108`;
  `config.port`/`runner.command` are not configurable and are rejected by the schema.

## 4. Decisions

- **D-i.** Observation is a **port + pure dataclasses**, not an event bus or callback registry —
  the closed dataclass union (`ObservationEvent`) is the entire surface; adapting it onto any wire
  format is the embedder's job, deliberately out of `url4.observe`.
- **D-ii.** Usage is reported through a **`ContextVar` sink**, not a return value or an extra
  observer method, so world handlers without an `ExecutionContext` can attribute tokens to the
  current span without a signature change.
- **D-iii.** url4-cloud splits into **distributions per deployment shape** (backend image vs
  runner image), sharing protocol + bus libs — keeps each image minimal and the engine dependency
  confined to the runner.
- **D-iv.** **Local mode reuses the real protocol**, not a parallel code path: the in-process
  `JobRunner` runs the same `Url4Executor` → `publish` lifecycle in-memory, so dev and the
  headless test exercise production code.

## 5. Test plan (as shipped)

- `packages/url4`: `tests/unit/test_observe.py`, `tests/unit/test_usage_sink.py`,
  `tests/unit/test_import_isolation.py` (asserts `url4.observe` stays stdlib-only).
- `apps/url4-cloud`: `tests/integration/test_local_spine.py` (runs the full local-mode protocol
  end-to-end through the real `Url4Executor`), `tests/unit/test_aigateway_base_url_forwarding.py`
  (+ `_fakes.py`), and the existing `test_e2e_compose_flow.py` updated for the distro split.

## 6. Gates

Two stacks are touched (per `.claude/sdlc.local.md`); both gate runners must be green:

- **`url4`** (`packages/url4`): `ruff check` · `ruff format --check` · `pyright` ·
  `pytest --cov=url4 --cov-fail-under=95`.
- **`url4-cloud`** (`apps/url4-cloud`): `ruff check` · `ruff format --check` · `pyright` ·
  `pytest --cov=url4_cloud --cov=url4_cloud_nats --cov=url4_streaming_protocol
  --cov=url4_cloud_runner --cov-fail-under=80`.

Run from the repo root: `uv run .claude/scripts/run_gates.py url4` and
`uv run .claude/scripts/run_gates.py url4-cloud`.

## 7. Open / deferred

- **OME-446 is only partially closed** by Half A: this seam delivers execution-observation +
  traceparent propagation; the ticket also lists node-level sub-session stop and a
  streaming-capable transport extension point, which remain open. Whether to advance/close
  OME-446 is an **owner call** (flagged, not decided here).
- The branch is **not rebased onto current `origin/main`** and carries the entire OME-513
  cascade; merge strategy for these three commits is an owner decision.
