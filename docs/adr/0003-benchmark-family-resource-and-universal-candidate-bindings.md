---
status: accepted
date: 2026-08-04
supersedes: 0002-model-protocol-alternatives-as-benchmark-variants.md
---

# Fetch one Benchmark Family and link one explicit Variant locally

The Engine publishes one `screamingface.benchmark-family.v1` resource per Benchmark Family. The
resource contains family metadata, a `default_variant`, and a map of independently revisioned
Variants. Every Variant contains exactly one complete, Candidate-independent URL4 expression.
The SDK fetches the family once per Evaluation, selects the requested Variant locally, links every
Candidate, and submits one complete shareable URL4 per Candidate.

The public selection syntax is `family` for the default Variant and `family/variant` for another
Variant. The initial IFEval family contains:

- `ifeval` — canonical single-pass IFEval;
- `ifeval/self-corrective` — Khoa's current three-attempt whole-Candidate correction protocol;
- `ifeval/verifying-ensemble` — Khoa's current direct-member verification protocol, with the
  Fusion synthesizer acting as its selection and feedback model.

The resource is descriptive only at the family level. It is not a workflow schema: the SDK does
not interpret Benchmark steps, actions, routes, retries, verification, or scoring. Engine-side
Python continues to construct each opaque executable URL4. Adding an unusual Benchmark or Variant
therefore does not require an SDK release unless it needs a genuinely new universal Candidate
binding.

The universal structural bindings are `$candidate` for a whole Model or Fusion,
`$candidate_members` for an ordered collection of direct Fusion members, and
`$candidate_synthesizer` for a Fusion's synthesizer expression. A Variant references only the
bindings it needs. The linker discovers those references structurally, supplies inert expressions,
and otherwise remains unaware of the Benchmark. The Engine validates Variant-specific constraints,
such as the verifying ensemble's two-to-four direct Model members, before its first paid call.

`$candidate_members` is one runtime-sized collection, so the Engine returns the same URL4 for two,
three, or four members. The SDK no longer sends `?members=N`, and the resource contains no URL4
table keyed by Candidate shape. This keeps a Benchmark resource Candidate-independent and reusable
across every Candidate in the Evaluation.

This ADR changes the packaging of Variants, not Khoa's current IFEval behavior. In particular, the
three corrective rounds remain visibly unrolled and execute as before. A source comment beside the
verifying-ensemble builder records a possible follow-up: deterministic Engine routes can return
empty or singleton collections to gate early acceptance, passer-only selection, and retries. That
protocol-fidelity work must be confirmed against the authors' harness before it is described as an
exact reproduction.

## Considered options

- **One GET per Candidate shape (`?members=N`)** was rejected because the Benchmark expression is
  not inherently Candidate-specific. It duplicates fetches, makes cache identity depend on a
  Client shape, and requires the Engine to pre-expand the same member loop repeatedly.
- **A map such as `url4_by_direct_member_count`** was rejected because it duplicates executable
  graphs and imposes an artificial set of supported sizes when URL4 can iterate one runtime
  collection.
- **Separate top-level ids for every related protocol** remain executable but lose the Family
  relationship and force discovery clients to reconstruct it from naming conventions.
- **`method=`, verifier flags, an action list, or a binding declaration schema** were rejected
  because they make the SDK interpret Benchmark behavior and grow toward a second DSL.
- **An opaque Engine coordinator endpoint** was rejected because it would hide the evaluation
  graph. The submitted artifact must remain one inspectable and independently executable URL4.

## Consequences

- One Evaluation performs one family-resource GET regardless of Candidate count or shape.
- Catalog discovery groups Variants by Family, while the SDK exposes each Variant as a selectable
  Benchmark value. Discovery also fetches each family resource at most once.
- The default Variant retains the short identity (`ifeval`); non-default report identities are
  qualified (`ifeval/self-corrective`, `ifeval/verifying-ensemble`).
- Variant revisions, costs, and scores remain distinct even though Cases and runtime routes may be
  shared.
- The SDK temporarily accepts the older `screamingface.benchmark.v1` resource during rolling
  Engine/SDK deployments; new Engines publish the family resource.
