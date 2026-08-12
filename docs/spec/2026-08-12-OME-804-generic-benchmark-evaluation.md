---
title: Generic benchmark evaluation capabilities
ticket: OME-804
status: approved
date: 2026-08-12
---

# Generic benchmark evaluation capabilities

## Outcome

URL4 Cloud exposes a small set of deep Benchmark Evaluation modules. A Benchmark definition
supplies its irreducible evaluator graph and scoring adapter; the shared modules own the repeated
outer lifecycle:

```text
selected Cases
→ complete $candidate invocation
→ Benchmark evaluator adapter
→ typed Case Result
→ fail-closed Aggregation
→ Candidate Result
```

URL4 remains the only executable graph. The Client binds one complete Candidate Recipe at
`$candidate`; neither the Benchmark card nor the Client re-describes Evaluation in another DSL.

## Interfaces and seams

### Protocol composition

One URL4 AST combinator owns the mechanics common to every Benchmark:

- iterate the immutable Case collection in selection order;
- evaluate one supplied Case graph;
- collect Case-scoped resolution failures rather than aborting the collection;
- materialize the ordered Case evaluations;
- pass them through context to the aggregate route;
- bind the exact selected count in the aggregate intent.

The combinator accepts a complete per-Case `Node`; it does not know whether that node performs a
deterministic check, one Judge call, multiple rubric passes, or a corrective strategy. This makes
it a URL4 composition capability, not a benchmark-manifest DSL.

### Installed runtime

Shared runtime functions own only mechanics proven identical across at least two Benchmarks:

- strict JSON object/array decoding and compact encoding;
- positive Case identity and selected-count validation;
- preservation of selected Case order so Benchmark result adapters can attach identity-less
  collected failures to the exact selected Case;
- Candidate Invocation decoding with exact refusal propagation;
- standard Case-evaluation collection and Aggregation endpoint envelopes;
- conversion of local asset/adapter errors into bounded `benchmark_unavailable` failures.

Benchmark adapters remain ordinary callables registered on revision-pinned routes. The runtime
does not add a generic registry whose only implementation is one Benchmark.

### Evaluator adapters

The real evaluator seam is one complete per-Case URL4 node plus its installed routes:

- IFEval supplies deterministic instruction verification.
- DRACO supplies multi-pass criterion Judging and evidence-to-credit logic.
- HealthBench supplies per-rubric-item Judging and penalty-bearing credit logic.

These are distinct adapters because they genuinely vary. Shared endpoint envelopes may be
extracted; evaluator semantics, schemas, prompts, retry policy, and scoring remain local.

## Behavioral invariants

- Each selected Case invokes the complete Candidate according to the immutable Benchmark
  protocol and appears exactly once in the final ordered result.
- Candidate output, finish reason, refusal, and Candidate Invocation failure remain distinguishable.
- Operational failure never becomes an incorrect answer or a numeric zero.
- The scorer runs only when the Benchmark's selected Case coverage is complete, as established by
  OME-802.
- Direct URL4 evaluation and `sf.evaluate(...)` resolve the same expression.
- A structural extraction that changes rendered URL4 changes the immutable Benchmark revision,
  even when score mathematics are unchanged.

## Benchmark-specific remainder

Each Benchmark directory may retain files for immutable data preparation, evaluator semantics,
prompts, evidence validation, scoring mathematics, and thin registration. File-count reduction is
not itself the objective: shared knowledge and mechanics must move to the deep module, while
genuinely different research protocols remain obvious and local.

## Compatibility

This is unreleased v1. Do not add legacy routes, aliases, dual builders, old-shape readers,
migrations, fallbacks, or new schema versions. Existing successful-result semantics are preserved
and structurally changed Benchmark URL4 receives a new immutable revision.

## Exclusions

- Client Report consumption and widgets (OME-803).
- Pipeline or CorrectiveLoop Candidate construction (OME-796 and its dependencies).
- Arbitrary user Python or manifest-authored execution graphs.
- Timing, usage, cost, cache, and dynamic operation-occurrence attribution.
