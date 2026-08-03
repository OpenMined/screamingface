---
title: ScreamingFace direct evaluation interface
ticket: OME-605
status: approved
date: 2026-07-29
approved: 2026-07-29
supersedes: 2026-07-25-OME-605-screamingface-client-v1.md
---

# ScreamingFace direct evaluation interface

## Decision

The unreleased Python Client exposes one complete evaluation operation:

```python
import screamingface as sf

client = sf.Client()
report = client.evaluate(
    candidates=[opus, frontier_trio],
    benchmark="draco",
    limit=5,
)
```

`AsyncClient.evaluate(...)` provides the same domain behavior asynchronously.

There is no module-level or Recipe-owned evaluation alias, and no public `Plan`, `plan(...)`, or
`run(...)`. Benchmark resolution, capability validation, Candidate URL4 compilation, and execution
remain internal stages of `Client.evaluate(...)`. This preserves one obvious researcher workflow
while keeping the implementation free to validate before spending.

## Public execution interface

```python
Client.evaluate(
    candidates,
    *,
    benchmark,
    limit=None,
    on_event=None,
    progress=None,
) -> Report

await AsyncClient.evaluate(
    candidates,
    *,
    benchmark,
    limit=None,
    on_event=None,
    progress=None,
) -> Report
```

`candidates` accepts one `Model`/`Fusion` or an ordered sequence. Candidate names must be unique.
`benchmark` is a required Engine catalogue name or immutable identifier. `limit` is either `None`
for the complete Benchmark or a positive integer for a stable prefix.

The implementation resolves and compiles all Candidates before starting the first paid Run. It
then executes one flat Candidate URL4 per Candidate and assembles one ordered `Report`.

## Inspection and safety

The Client does not expose a second workflow object merely to preview execution. No-spend
inspection, capability validation, and future budget checks are internal prerequisites of
`evaluate(...)`.

Candidate URL4 remains available on each returned `CandidateResult`. Typed lifecycle Events remain
available through `on_event`. A future explicit inspection interface requires separate owner
approval; it must not recreate mandatory two-step evaluation.

`dry_run=True` is not part of the interface because it conflates:

- no-spend validation;
- a small real run; and
- mocked execution.

A small real evaluation uses `limit`. Mock execution belongs to the Engine or test environment.
Hard spend limits require the separately defined Engine budget contract.

## Ownership

The Client calls only its configured ScreamingFace Engine. The Engine owns Benchmark protocols,
model execution, grading, aggregation, tools, caching, and spend enforcement. The Client owns
Recipe authoring, strict input validation, internal URL4 compilation, lifecycle consumption, and
Report decoding.

Local and hosted Engines present the same `evaluate(...)` interface to callers.

## Migration

This package is unreleased, so the previous public `Plan` interface is removed rather than
deprecated:

- remove `sf.Plan`, `sf.Candidate`, `sf.plan`, and `sf.run`;
- remove `Client.plan/run` and `AsyncClient.plan/run`;
- add synchronous and asynchronous Client `evaluate`;
- keep internal compiled-Candidate and operation projections private; and
- regenerate examples and package documentation around the canonical operation.

Historical work ledgers may describe the earlier decision, but active package documentation and
tests must not teach it.
