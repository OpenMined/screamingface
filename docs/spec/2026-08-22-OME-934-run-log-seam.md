# OME-934 — Generic run-scoped structured Log seam

Status: APPROVED 2026-08-22. The owner approved the issue split, grilled architecture, and OME-934
implementation in plain words.

## Purpose

Allow one injected observational adapter to establish state for exactly one Engine execution and
submit ordinary structured Logs through that execution's existing Runner bridge. Finish the
production composition path now so a later Benchmark change can add live progress semantics
without another generic Runner or URL4 change.

## Boundary

OME-934 owns:

- one generic Runner run-scope port;
- lifecycle integration around exactly one `url4_run`;
- validation and same-bridge delivery of injected structured Logs;
- one Benchmark adapter wired by the existing production composition root;
- an inert, task-local Benchmark recorder that future Benchmark operations can activate; and
- unit, composition, isolation, failure-containment, and layering tests for that complete path.

OME-934 does not publish `screamingface.evaluation-progress.v1`. OME-932 will add the terminal Case
signals and provisional-score semantics in `screamingface_engine/benchmarks/*`.

## Generic Runner contract

The `Url4Executor` accepts at most one optional run-scope factory:

```text
open_run_scope(rendered_url4, emit_structured_log) -> context manager | None
```

- `rendered_url4` is the exact input string, passed once. The Runner neither parses nor rewrites it.
- The factory and returned context manager are synchronous and perform no I/O or paid work.
- A returned context manager must unwind partial acquisition inside a failing `__enter__`; Python
  does not call `__exit__` after entry fails, and neither does the Runner's fail-open wrapper.
- Returning `None` declines instrumentation for that execution.
- The scope opens after world resolution and surrounds only `url4_run`.
- Scope teardown completes before the bridge closes, so teardown may submit its final Log.
- `emit_structured_log` is synchronous, non-blocking, and event-loop-thread-local. An off-thread
  call is invalid and is dropped before it can mutate the Runner bridge.
- The emitter accepts a non-empty string body plus flat attributes whose values already satisfy
  the JSON wire meaning of `LogData`: `str | int | finite float | bool | None`. `nan` and positive
  or negative infinity are malformed rather than being serialized as `null`.
- A valid submission enters the same `_Bridge` immediately and is mapped to an ordinary INFO
  `LogData` on the run root. There is no second queue, poller, sequence, wire type, or Client path.

An injected Log is a Runner-local bridge input, not a new `url4.observe.Log` shape. This preserves
`packages/url4` unchanged while retaining the existing wire Log contract and ordering.

## Benchmark adapter

The composition root constructs one adapter from the same immutable `BenchmarkRegistry` already
used to install Benchmarks and injects it through the generic Runner port.

The adapter opens an inert run-local recorder for every execution. It does not inspect the URL4
syntax. A Benchmark-owned operation may claim that recorder with its registered Benchmark ID and
submit a structured Log. Until that happens, the adapter emits nothing.

- An unknown Benchmark ID declines the signal.
- The first registered Benchmark ID owns the recorder for that execution.
- A signal claiming a different Benchmark ID disables instrumentation for that execution; it never
  mixes counters or scores and never selects a winner by registration order.
- Zero claims is the normal behavior for a non-Benchmark execution.
- Nested scopes restore the outer recorder when the inner execution closes.
- A retained emitter or recorder becomes inert after its scope closes and cannot contaminate a
  later execution.

There is no second progress registry. Existing `BenchmarkRegistry` construction remains the sole
static validation of Benchmark identity.

## Failure and diagnostic contract

Instrumentation is observational and fail-open:

- factory setup, context entry, submission, context exit, and Benchmark-adapter failures cannot
  replace a URL4 result or its existing exception;
- a malformed body, attribute key, or attribute value drops the complete submitted record rather
  than coercing or partially publishing it;
- a factory may decline by returning `None` without a diagnostic;
- an expired emitter is inert and may produce at most one operator diagnostic;
- diagnostics use the normal internal logger, never this Log seam, so reporting a seam failure
  cannot recurse; and
- diagnostics identify only a stable seam phase and safe exception information. They never include
  rendered URL4, Log bodies, attributes, prompts, answers, rubrics, or other payload material.

Static composition defects still fail at startup through their existing contracts. Fail-open
behavior is not a way to hide an invalid `BenchmarkRegistry` or broken Engine configuration.

## Delivery and reliability

Injected Logs have the existing ordinary-Log policy:

- they attach to the execution root; semantic identity belongs in attributes;
- they receive the same run subject and lifecycle sequence as every other streamed frame;
- they are immediately eligible for the bridge's existing Log eviction policy under pressure; and
- they provide no correctness guarantee beyond ordinary Logs.

OME-932 must therefore publish complete cumulative snapshots. The authoritative final evaluation
result remains the reconciliation source if an intermediate or final progress Log is evicted.

## Privacy and schema ownership

The generic seam validates only the body and flat scalar attribute shape. It recognizes no
ScreamingFace schema and performs no domain-specific redaction.

OME-932 owns an exact producer whitelist for `screamingface.evaluation-progress.v1`. Its tests must
forbid Case IDs, prompts, inputs, answers, attachments, rubrics, judge explanations, provider
errors, model identity, and private metadata. The Client ignores ordinary Logs whose schema it does
not recognize.

## Architecture invariants

- Generic executor modules depend only on the generic run-scope port.
- The generic port is a dependency-free app-owned leaf; the Benchmark adapter never imports the
  Runner implementation.
- Only the production composition root imports and wires the concrete Benchmark adapter.
- Runner code recognizes no Benchmark, Candidate, model, grading, or progress vocabulary.
- URL4 source, rendered expressions, execution graphs, protocol/revision/cache identity, results,
  paid calls, public errors, and `packages/url4` remain unchanged.
- Spans and `cost.usage` remain their existing first-class signals rather than being copied into
  Logs.
- This is one optional seam, not a generic instrumentation registry or universal event bus.

## Acceptance

1. The exact URL4 is handed to one synchronous run scope around only `url4_run`.
2. A valid injected record arrives through the existing bridge as an ordered INFO `LogData`.
3. Existing Log eviction treats injected Logs identically to URL4 Logs.
4. Missing, declining, malformed, expired, or failing instrumentation cannot alter execution.
5. Concurrent and nested runs remain isolated and restore the correct outer state.
6. The Benchmark adapter is wired through `build_executor`, remains inert without a Benchmark
   claim, and rejects unknown or conflicting ownership without affecting evaluation.
7. A composition-path test proves the production registry adapter reaches the sequenced Log stream.
8. A layering test proves the executor imports no Benchmark module or concrete adapter.
9. Existing result, error, Runner, protocol, and Engine gates remain green.
10. No progress schema, URL4 change, Client change, wire change, or `packages/url4` change lands.
