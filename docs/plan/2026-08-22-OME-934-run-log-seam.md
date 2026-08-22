# OME-934 — Implementation plan

Spec: `docs/spec/2026-08-22-OME-934-run-log-seam.md`
Stack: `screamingface-engine`
Ledger: `docs/work/2026-08-22-OME-934-run-log-seam.md`

Owner implementation approval received 2026-08-22. Each iteration follows the `sdlc-python`
RED → GREEN → review loop and appends coverage rather than weakening inherited tests.

## Iteration 1 — define the generic run-scope port

### RED

- The optional factory sees the exact URL4 once.
- A synchronous context surrounds only `url4_run`, after world resolution and before bridge close.
- A missing or declining factory preserves the existing result and error behavior.
- Concurrent and nested executions receive isolated state and restore the outer scope.

### GREEN

- Define the smallest generic factory, structured-Log emitter, and scalar types in a
  dependency-free app-owned port leaf; keep lifecycle implementation in the Runner adapter.
- Add one optional factory dependency to `Url4Executor`.
- Keep the port internal Python dependency injection: no env, HTTP, Client, or URL4 option.

## Iteration 2 — deliver through the existing bridge

### RED

- A valid record enters the existing bridge immediately and maps to an INFO `LogData` with its flat
  scalar attributes intact.
- It shares existing ordering, root attachment, eviction, drop accounting, and lifecycle sequence.
- Malformed records are dropped whole.
- Setup, entry, emission, exit, and expired-emitter failures cannot replace success or the original
  URL4 exception.
- Operator diagnostics cannot recurse or disclose URL4 or submitted payloads.

### GREEN

- Add one Runner-local structured-Log bridge input; do not widen `url4.observe.Log`.
- Validate before enqueueing and treat the input as an evictable ordinary Log.
- Make emitters inert on scope close.
- Contain observational failures at the seam and report only safe internal diagnostics.

## Iteration 3 — wire the dormant Benchmark adapter

### RED

- `build_executor` injects one adapter derived from its existing `BenchmarkRegistry`.
- The adapter opens inert run-local state and emits nothing without a Benchmark-owned claim.
- A registered claim can use the generic emitter; unknown and conflicting claims are ignored or
  disable instrumentation without changing evaluation.
- Nested and concurrent Benchmark scopes cannot cross-talk.
- Generic executor modules cannot import `screamingface_engine.benchmarks`.

### GREEN

- Implement the adapter and task-local recorder under `screamingface_engine/benchmarks`.
- Validate claims against the existing immutable registry; add no second registry.
- Wire the adapter only in the existing composition root.
- Add the layering guard for port → adapter dependency direction.

## Iteration 4 — prove production composition and regressions

### RED

- A `build_executor` test drives the fully composed path and observes an injected record in the
  existing sequenced Log stream.
- Default/non-Benchmark execution emits no new record.
- Existing successful results, URL4 failures, cancellation, early consumer exit, bridge pressure,
  cache summaries, and world teardown retain their contracts.

### GREEN

- Add only the minimum composition fixture needed to activate the dormant recorder.
- Keep all ScreamingFace progress schema and terminal Case semantics out of OME-934.

## Verification

```text
uv run .claude/scripts/run_gates.py screamingface-engine
```

Before commit and PR-ready review:

- confirm `git diff origin/main -- packages/url4 packages/screamingface` is empty;
- confirm no generated/discovered URL4 fixture changed;
- confirm generic executor modules contain no Benchmark import or schema vocabulary;
- run the focused executor, Benchmark adapter, composition, and layering suites;
- run the complete ScreamingFace Engine gate; and
- inspect the final diff against every invariant in the approved specification.
