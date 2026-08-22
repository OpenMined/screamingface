# OME-934 — Generic run-scoped structured Log seam

Status: DRAFT 2026-08-22. The issue split is approved; production implementation awaits explicit
approval of this specification and plan.

## Purpose

Allow an injected observational component to establish run-local state from the exact rendered URL4
and emit ordinary structured Logs through the existing Runner bridge.

## Contract

The Runner accepts one optional generic run-scope factory:

```text
open_run_scope(rendered_url4, emit_structured_log) -> context manager
```

The context surrounds exactly one `url4_run`. The emitter accepts an opaque body and scalar
attributes and submits an ordinary Log to the run's existing `_Bridge`.

## Extension capacity

The seam is intentionally schema-agnostic. A future Benchmark-owned producer can publish
namespaced lifecycle records for Answering, Judging, Grading, terminal Case accounting,
provisional scores, or another scalar progress fact without changing the Runner, URL4 expression,
or wire discriminator. The producer and Client own the record schema; the Runner only transports
an ordinary structured Log.

This is not a universal event bus:

- attributes retain the existing `LogData` scalar value contract;
- existing URL4 spans and `cost.usage` remain their own first-class signal types rather than being
  copied into Logs;
- Logs retain the bridge's existing lossy-under-pressure policy, so correctness-sensitive progress
  uses complete cumulative snapshots and reconciles from the authoritative final result;
- a future requirement for guaranteed delivery, nested payloads, or a new first-class wire event is
  a separate protocol decision rather than an expansion of this seam.

## Invariants

- The factory and scope are optional; absence preserves current behaviour.
- Every execution receives its own scope/emitter; concurrent runs cannot cross-talk.
- Setup, emission, and teardown are observational and fail-open.
- Logs retain existing sequence, run subject, transport, and eviction behaviour.
- Runner code imports no Benchmark module and recognizes no ScreamingFace schema.
- Generated URL4, URL4 execution, results, paid work, errors, and `packages/url4` are unchanged.
- No Benchmark progress producer is included in this PR.

## Acceptance

1. Exact rendered URL4 is passed once to the factory.
2. An emitted structured Log arrives through the existing bridge in normal order.
3. Concurrent and nested test runs remain isolated.
4. Missing, declining, malformed, or failing instrumentation cannot alter the run.
5. Existing Runner/protocol gates and layering checks pass.
