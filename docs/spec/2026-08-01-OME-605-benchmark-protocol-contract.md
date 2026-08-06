---
title: Link flat Benchmark and Candidate URL4 expressions
ticket: OME-605
status: approved
date: 2026-08-01
updated: 2026-08-05
---

# Link flat Benchmark and Candidate URL4 expressions

## Decision

The Engine publishes each executable Benchmark protocol as one flat
`screamingface.benchmark.v1` resource. The SDK compiles an `sf.Model` or `sf.Fusion` into
generic Candidate URL4 and structurally links only the universal bindings referenced by that
Benchmark. The resulting URL4 is complete, readable, and executes through the existing URL4 GET
lifecycle.

Benchmark behavior stays Engine-owned. The SDK has no DRACO, IFEval, Judge, grading, retry, or
aggregation branch. There is no public Benchmark Family resource, Benchmark-parameter DSL,
model allowlist, `required_models`, `total_case_count`, or implicit synthesizer selection.

## Domain language

- A **Candidate** is the system being evaluated: either one `Model` or one `Fusion`.
- A **Fusion member** is a direct child of that Fusion.
- A **Fusion synthesizer** is Candidate configuration used when the ordinary Fusion combines
  member answers. A Benchmark may reuse that explicitly selected Model in a Benchmark-owned
  Judge role, but the concepts remain distinct.
- A **Benchmark** is one executable, revisioned experiment identified by its full `id`.
- `variant` is descriptive metadata. The canonical protocol uses the base id (for example
  `ifeval`); alternatives use complete ids such as `ifeval/self-corrective` and
  `ifeval/verifying-ensemble`.
- A shared **family** may exist inside the Engine solely to reuse assets and route installation.
  It is not a public resource and the SDK never dispatches on it.

## Public Candidate API

- `Model(model, prompt=None, params=None)` compiles to one input-consuming Model expression.
- `Fusion(members, synthesizer=None, prompt=None, params=None)` may be incomplete while the user
  is authoring it.
- No SDK, Engine, AI Gateway, or Benchmark-global default fills an omitted synthesizer.
- A Benchmark that references `$candidate` requires a complete Candidate expression. A Fusion
  without a synthesizer therefore fails planning.
- A Benchmark that references `$candidate_synthesizer` requires an explicit Fusion
  synthesizer. Omission fails planning before model availability checks or paid execution.
- Candidate prompts and generation parameters remain Candidate policy. Benchmark retry, Judge,
  retrieval, grading, and aggregation prompts remain Benchmark policy.

## Benchmark resource

`GET /v1/benchmarks/{id}?limit=N` returns exactly one executable resource:

```json
{
  "schema": "screamingface.benchmark.v1",
  "id": "ifeval/verifying-ensemble",
  "variant": "verifying-ensemble",
  "title": "IFEval Verifying Ensemble",
  "description": "IFEval with member verification and judge-guided correction.",
  "revision": "<opaque immutable revision>",
  "case_count": 541,
  "url4": "(members:... , rows:...iteration.slice=0:3, result:...)!'$result'"
}
```

The fields are deliberately small:

- `case_count` is the full installed Case count and does not change with `limit`.
- `limit` is represented inside the returned URL4 as Case selection, so the exact executed
  program remains auditable.
- `url4` is canonical Candidate-independent URL4, not a second template language.
- The immutable `revision` identifies the exact protocol and prepared assets.
- The response has an ETag over its representation.

`GET /v1/benchmarks` lists each executable Benchmark as a flat entry. The base id represents
the canonical protocol; slash-qualified ids are explicit alternatives. Discovery never requires
the SDK to fetch a Family and then choose a method.

## Universal structural bindings

The SDK recognizes only these URL4 references:

| Binding | Meaning |
| --- | --- |
| `$candidate` | the complete Model or ordinary Fusion expression |
| `$candidate_member_N` | the Nth direct member expression |
| `$candidate_members` | a readable URL4 struct referencing the direct member bindings |
| `$candidate_synthesizer` | the explicit Fusion synthesizer as a direct Model expression |

The SDK parses the Benchmark URL4 and binds only the names it actually references. It does not
inspect the Benchmark id or infer protocol behavior.

Each executable member expression appears once in an ordinary named URL4 binding.
`$candidate_members` contains stable names and references to those bindings; it is not Base64,
an encoded JSON workflow, or a duplicate executable representation. The final Report retains the
same complete URL4 that ran.

## Candidate Invocation

`/candidate` is the Runner's generic Candidate Invocation boundary:

- the call creates a fresh `$input` scope and evaluates a supplied Candidate expression against
  the same restricted URL4 node;
- the Runner enforces recursion and invocation limits;
- credentials, cancellation, observations, usage, and failures stay in the same run;
- the route contains no Benchmark-specific grading or protocol behavior;
- Benchmark-owned query parameters such as guarded retrieval remain visible on the invocation.

The route is ordinary URL4 resolution infrastructure. A Benchmark can invoke a Candidate once or
many times without the SDK constructing that workflow.

## Validation

Validation has two layers:

1. The SDK performs generic structural checks while linking: required bindings exist, member
   indices are contiguous, direct-member requirements receive direct Models, and required
   synthesizer/whole-Candidate expressions are complete.
2. A Benchmark may place one private validation/resolution call in its own URL4 before Case
   iteration. That route owns only protocol-specific shape rules and fails the run before a Case
   can spend.

IFEval `verifying-ensemble` uses the second layer. Its `resolve-candidate` route is called once,
requires two through four direct Model members plus one explicit direct-Model synthesizer,
canonicalizes the readable member bindings, and returns the collection used by every Case.
It does not choose a Judge, inject a default, or enforce a guessed Judge-model allowlist. Different
Judge models in the paper are experiment configurations supplied by the user, not Benchmark ids
or a public enum.

DRACO may use the same authoring pattern if it later exposes Candidate-shape options. Fixed
protocol models remain explicit model routes in its Benchmark URL4.

## Ownership

### SDK

- Candidate values, prompts, parameters, and explicit synthesizer selection.
- Flat Benchmark discovery and resource decoding.
- Generic structural linking and preflight model availability.
- Report, Event, auth, connection, notebook, and packaging UX.

### URL4 Cloud / ScreamingFace Engine

- Benchmark ids, metadata, revisions, Cases, private assets, protocol URL4, validation routes,
  Candidate Invocation, grading, aggregation, and fail-loud behavior.
- Internal family reuse is allowed only as an implementation detail.

### AI Gateway

- Exact dispatchable model catalog, credentials, provider-neutral parameters, provider metadata,
  and provider response evidence.
- No Benchmark selection, Candidate topology, grading, or synthesizer default.

### packages/url4

- General expression parsing, rendering, scoping, execution, streaming, and observation semantics.
- No ScreamingFace or Benchmark-specific concepts.

## Failure and evidence contract

- A Case with no valid score/check record is retained with `grade=null` or a null Grade score and
  a structured Case failure; it is never converted into a plausible zero.
- If any selected Case is unscored, the Candidate score is null rather than a partial mean over
  the surviving Cases.
- An in-band Case error survives Aggregation with its Case id and bounded stage, code, message,
  retryability, and diagnostic metadata.
- Provider refusal and finish reasons are inherited from the URL4/URL4 Cloud baseline and remain
  attached to streamed spans. The SDK preserves those fields rather than fabricating them.
- Actual usage comes from execution telemetry. The manifest does not predict calls or cost.
- The Candidate result retains exact input, output, finish reason, Grade, Checks, raw Evidence,
  metadata, and Case failures. The SDK decodes these into immutable Case Results and preserves
  them through `Report.to_dict()` and `Report.to_json()`.
- Aggregation accepts only the protocol's exact Engine-bound Case-evaluation envelope. It never
  searches arbitrary nested text or values for grading records and has no compatibility decoder.

## Non-goals

- A Client-side Benchmark workflow compiler.
- A public Family/method hierarchy.
- A manifest parameter/default/allowed-model DSL.
- An Engine-global or Benchmark-global synthesizer default.
- Treating Fusion and Benchmark ensemble protocols as the same thing.
- Hiding linked expressions in opaque encodings.
- Changing URL4 merely to shorten an otherwise valid Benchmark expression.

## Acceptance

- Every executable Benchmark is addressable by one complete id and one
  `screamingface.benchmark.v1` resource.
- The public resource contains exactly schema, id, variant, title, description, revision,
  case_count, and URL4.
- `limit` changes the URL4 selection but not installed `case_count`.
- The SDK links universal bindings without branching on Benchmark identity.
- Omitted synthesizers fail only when the selected Benchmark requires one.
- IFEval verifying-ensemble accepts two through four direct Models, requires an explicit direct
  Model Judge selection, resolves once before Case iteration, and exposes no guessed allowlist.
- Linked URL4 round-trips through `url4.build` and `url4.render` and remains readable.
- DRACO and IFEval fail loudly when a Case cannot produce a valid scoring record.
- Relevant SDK, URL4 Cloud, AI Gateway, URL4, notebook, build, and distribution gates pass on the
  final independent branches rebased onto current `main`.
