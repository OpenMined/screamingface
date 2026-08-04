---
status: superseded
date: 2026-08-03
superseded_by: 0003-benchmark-family-resource-and-universal-candidate-bindings.md
---

# Model protocol alternatives as separate Engine-owned Benchmark Variants

Each executable evaluation protocol is a separate Engine-owned Benchmark identity. Related
protocols may share one Benchmark Family, assets, verifier implementation, and runtime installer,
but every fetched `screamingface.benchmark.v1` resource contains exactly one canonical URL4 and
one immutable revision. Canonical IFEval is therefore `ifeval`; the fixed three-attempt corrective
protocol is `ifeval-corrective`; and the fixed three-member verifier-guided protocol is
`ifeval-corrective-ensemble`. The SDK accepts any id through the existing `benchmark=`
argument and remains unaware of IFEval, correction, verification, or family-specific behavior.

This decision keeps ownership aligned with execution. IFEval's verifier is deterministic
Benchmark code, not a Model selected by the Client. In the corrective Variant, the Engine URL4
invokes an ordinary Candidate, checks its response, converts the private check record into
sanitized feedback, and invokes the same Candidate again. Canonical IFEval invokes the Candidate
once and exposes no feedback loop. Both definitions share `/opt/benchmarks/ifeval` assets and the
same family runtime, while their ids, revisions, URL4 expressions, costs, and reported scores stay
distinct.

The ensemble Variant reproduces the showcased three-member, three-attempt, Flash-judged protocol
without introducing a special SDK Candidate. A Fusion is still ordinary Client data, but the
universal linker can expose each direct Model member as an inert structural binding. The
Engine-owned URL4 invokes those bindings, verifies each draft, returns sanitized feedback to the
same member, asks its pinned Judge to select one answer per attempt, and deterministically returns
the earliest passing selection. The Benchmark resource still contains only identity metadata,
required Engine Models, and one complete URL4; it has no action map or workflow description.

`limit` remains Case selection within one protocol and never creates a Variant. Running
`benchmark="draco", limit=1` is a smoke-sized DRACO Evaluation, not `draco-smoke`; a new id is
justified only when Candidate Invocation, Grading, or Aggregation semantics change. The familiar
bare family id names the canonical Variant, while noncanonical protocols receive qualified ids
such as `ifeval-corrective`.

## Considered options

- **`with_verifier=True` or similar evaluation flags** were rejected because each unusual
  Benchmark would add another SDK switch and capability matrix, gradually forming a workflow DSL.
- **A generic `method=` selector** was rejected because one resource id would conceal protocols
  with different revisions, costs, and comparability, and every SDK would need the method concept.
- **A verifier route or actions map in the Benchmark resource** was rejected because it splits the
  executable contract between URL4 and metadata and makes the SDK orchestrate Benchmark behavior.
- **A verifier-aware Fusion or CorrectiveEnsemble in the core SDK** was rejected because both
  final-answer and member-level correction are fully expressed by Engine-owned URL4. The Client
  exposes only universal structural bindings for direct Fusion members; it does not implement
  retry, verification, judging, selection, or finalization.
- **A directory-shaped manifest containing every Variant** was rejected because a resource would
  stop meaning one executable protocol. Family grouping belongs in catalog metadata and Engine
  source layout; evaluation fetches the selected Variant directly in one request.

## Consequences

- `ifeval` scores are the canonical paper-comparable single-pass protocol;
  `ifeval-corrective` scores must be labeled and compared separately.
- Current URL4 has no conditional early-stop primitive, so the corrective Variant visibly and
  deliberately executes exactly three attempts, then scores the earliest strict pass or the last
  attempt if none passes. It must not be described as skipping paid calls after success.
- The corrective feedback Adapter returns only failure descriptions or `PASSED`; private
  instruction identifiers and authoritative check records never enter Candidate context.
- The two corrective Variants are intentionally not interchangeable. `ifeval-corrective` retries
  one Candidate's final output; `ifeval-corrective-ensemble` requires exactly three direct Model
  members and retries them separately before its pinned Judge selects an answer.
