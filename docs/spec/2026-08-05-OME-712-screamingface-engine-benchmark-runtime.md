---
title: OME-712 — ScreamingFace Engine benchmark runtime
status: accepted
created: 2026-08-05
ticket: OME-712
related:
  - https://linear.app/openmined/issue/OME-712/run-draco-end-to-end-as-a-url4-expression-on-the-runner-path
  - docs/adr/0004-flat-benchmarks-and-isolated-candidate-invocation.md
  - docs/plan/2026-08-05-OME-712-screamingface-engine-benchmark-runtime.md
  - docs/work/2026-08-05-OME-712-screamingface-engine-benchmark-runtime.md
---

# ScreamingFace Engine benchmark runtime

## Purpose

The ScreamingFace Engine publishes reproducible Benchmarks and executes their complete protocols
as ordinary URL4. It owns Cases, Candidate Invocation sites, Grading, Aggregation, and
protocol-specific validation. The SDK owns only the submitted Model or Fusion expression and
links it structurally to the selected Engine expression.

The Engine is currently hosted and deployed from `apps/url4-cloud`; that package location does
not make Candidate Invocation generic URL4 Cloud infrastructure. `packages/url4` remains unaware
of ScreamingFace, Benchmarks, Candidates, Models, Fusions, and Judges.

The Engine also owns deliberately reduced smoke protocols. A smoke protocol exercises the same
Candidate Invocation, retrieval, Grading, Aggregation, failure, and result seams as its canonical
counterpart while reducing multiplicity. Its distinct id, revision, title, and description must
make clear that its score is diagnostic and never comparable to the canonical Benchmark.

## Public Benchmark resource

Every independently executable protocol is returned as one flat
`screamingface.benchmark.v1` resource. The initial ids are:

- `draco`
- `draco/lite`
- `draco/smoke`
- `ifeval`
- `ifeval/self-corrective`
- `ifeval/verifying-ensemble`

The bare `ifeval` id is the canonical default protocol. Alternative protocols have their own
ids, revisions, URL4, costs, and scores. They may share assets and implementation, but there is
no public Benchmark Family resource and no compatibility response containing nested Variants.

`draco` is the canonical 100-Case protocol: every selected Case, every criterion, and five
independent Judge passes. `draco/lite` is a non-comparable directional preview pinned to two
Cases, ten criteria per Case, and one Judge pass per criterion. Its Cases are selected from the
pinned dataset by one reviewable rule: take the two most represented domains, then choose the Case nearest the global
median rubric size in each domain, breaking ties by Case id. `draco/smoke` is a non-comparable
structural probe pinned to one Case, one criterion, and one Judge pass. All definitions are built
from the same DRACO protocol constructor so reduced paths cannot acquire a second Candidate,
retrieval, verdict, or reducer implementation. Multiplicity and pinned Case selection are their
only behavioral differences.

Each resource has this shape:

```json
{
  "schema": "screamingface.benchmark.v1",
  "id": "ifeval/self-corrective",
  "variant": "self-corrective",
  "title": "IFEval Self-corrective",
  "description": "...",
  "revision": "immutable-revision",
  "case_count": 541,
  "url4": "..."
}
```

`variant` is descriptive identity, not a parameter or execution switch. Catalog discovery is a
flat list of these resources. A slash in an id is part of the id and is accepted by detail and
Case-discovery routes.

`case_count` is always the complete installed Benchmark size. An Evaluation request such as
`?limit=3` changes the returned URL4's `iteration.slice`; it does not change or add resource
metadata. The SDK computes the effective Evaluation count as `min(limit, case_count)`, and the
Report records that effective count.

The resource has no action list, parameter DSL, route declarations, Candidate-shape schema,
fixed-Model dependency list, default synthesizer, or public Judge allowlist. The opaque URL4 is
the sole executable protocol.

## Standard URL4 artifact

The complete linked artifact uses only standard URL4 expressions, bindings, iterations, route
calls, contexts, intents, and protocol parameters. `/candidate` is an ordinary host-registered
route. No parser, compiler, AST, or evaluator behavior in `packages/url4` recognizes that name
or its ScreamingFace meaning.

Any compatible URL4 core can parse and execute the artifact. As with every URL4 expression, its
execution world must provide the referenced Candidate, Benchmark, Model, command, and data
routes. A missing route is the core's normal `endpoint_not_found` resolution failure, not an
invalid language artifact.

## Universal Candidate linkage

The SDK may supply three inert structural bindings:

- `$candidate` — one complete Model or Fusion URL4 expression;
- `$candidate_members` — a native URL4 struct describing the Fusion's ordered direct members;
- `$candidate_synthesizer` — the Fusion synthesizer expression.

For each direct member the linker emits one inert `$candidate_member_N` binding containing the
complete URL4 expression. The collection then contains only `member_N: {name, url4}` fields whose
`url4` value references that named binding. It contains no client-asserted kind,
Benchmark-specific letter, Base64, or JSON string carrying executable URL4. The final artifact is
standard URL4 and each executable member expression appears exactly once.

```text
candidate_member_1:0.0:'<complete member URL4>',
candidate_member_2:0.0:'<complete member URL4>',
candidate_members:0.0:{
  member_1: {name: 'first', url4: '$candidate_member_1'},
  member_2: {name: 'second', url4: '$candidate_member_2'}
}
```

A Benchmark references only what its protocol needs. `$candidate` is text in URL4's lexical
scope, not a callable language value. The Engine-owned `/candidate` route supplies the one
universal Candidate Invocation operation:

```text
/candidate(<Benchmark-owned input>)!'$candidate'
```

It evaluates the resolved Candidate expression with a fresh `$input` and returns its text result.
The route owns these ScreamingFace Engine invariants:

- one fresh lexical scope containing only the Benchmark-supplied `$input`;
- a per-Evaluation total invocation limit;
- recursion prevention;
- Benchmark-owned retrieval policy applied task-locally to Model calls. DRACO enables guarded
  retrieval at the Candidate invocation; ordinary Model calls inherit that ceiling and the
  universal Fusion compiler explicitly narrows synthesis with `web_search=false`. IFEval disables
  retrieval for every Candidate invocation. The Engine interprets no Fusion structure or role;
- parent cancellation, observation, usage, credentials, and typed-failure behavior.

## Candidate isolation

The Engine assembles separate orchestration and Candidate URL4 worlds that share only the
adapters and Evaluation state required for legitimate Candidate execution.

```text
Engine orchestration world
  /candidate
  declared Model routes
  private revisioned Benchmark routes
  operator-declared commands and data

/candidate
  delegates to a restricted Candidate world

Candidate world
  declared Model routes
  explicitly allowed commands and data
  no /candidate
  no private Benchmark routes
  no arbitrary absolute-URL outbound adapter
```

A Candidate cannot read private Cases, rubrics, verifier output, answer material, or Aggregation
routes, even if orchestration permits outbound URL4 sources.

Candidate Invocation belongs to the ScreamingFace Engine domain layer. Its implementation must
not live inside the AI Gateway connector: that connector owns provider-backed Model routes, while
Engine assembly injects those routes into the two worlds.

## Benchmark-owned resolution and validation

Candidate preparation is ordinary Benchmark URL4, not a mandatory Engine phase. A Benchmark may
use a universal binding directly or call any private revisioned route its protocol needs to
normalize or validate that value. If a protocol constrains Candidate shape, its author must make
paid Candidate Invocation depend on the prepared value so an invalid shape fails before spend.
Canonical and self-corrective IFEval accept an ordinary Candidate and add no shape validator.

`ifeval/verifying-ensemble` requires two to four direct Models and an explicitly configured Fusion
synthesizer; that synthesizer acts as the protocol Judge. Its URL4 calls `/resolve-candidate` with the native
`$candidate_members` struct as context and `$candidate_synthesizer` as intent. The route parses
each referenced URL4 expression itself—rather than trusting a client-supplied `kind`—and returns a
canonical runtime array as one Benchmark-local `$members` binding outside Case iteration. Every
Case and attempt iterates that immutable array directly. Parsing and shape validation happen once
per Evaluation, with no decoder alias, fallback representation, or default injection.

The `$candidate_synthesizer` expression retains the Candidate-selected model route and generation
parameters. The Benchmark owns the Judge instructions, so ordinary whole-Fusion blending prose is
not reused as a Judge prompt.

The Benchmark selects no default synthesizer, and the SDK does not invent one for this structural
binding. A missing `synthesizer=` fails during Client planning before paid work. The LANL paper's
two Judge models describe its five evaluated configurations; they are
not stated as a protocol allowlist. A different direct-Model Judge is therefore a custom
configuration, not a reproduction of Ens-1 through Ens-5. Declared Model-route availability
remains enforced by ordinary Candidate preflight and Invocation.

This composition uses the URL4 behavior already present in the inherited stack: an outer named
value is visible inside an iteration body. It does not require a new URL4 grammar/compiler change
or field access through a newly introduced validation object. Parameterized Candidate calls keep
their existing canonical-rendering wrapper.

Resolution and validation are Benchmark implementation. Candidate execution always crosses the shared
`/candidate` adapter. Neither the SDK nor AI Gateway interprets Benchmark protocol semantics.

## Model ownership

A Benchmark-owned Model is fixed directly in the Benchmark URL4 and included in its revision
hash. DRACO's grading Judge is Benchmark-owned: the Runner declaration and repository contract
tests pin its exact route, changing it creates a new revision, and an unavailable route fails
through ordinary URL4 resolution.

A Candidate-owned Model arrives through the submitted Model or Fusion. The verifying-ensemble
Judge is Candidate-owned because it is the Fusion's synthesizer and part of the system under
evaluation. Its `$candidate_synthesizer` binding is checked by this Benchmark's private route.

The two mechanisms intentionally differ. A public `required_models` field would duplicate facts
already owned by Engine installation and Candidate validation, so it is not part of
`screamingface.benchmark.v1`.

## Deterministic Benchmark routes

Each installed revision registers the private Cases, checking, selection, verdict, and
Aggregation routes referenced by its URL4. One registry owns resource generation and route
installation, so the Engine cannot advertise URL4 whose deterministic runtime is absent.

An incomplete installed Benchmark is a startup/configuration error, not a later paid-Evaluation
404. Missing assets remain a typed availability error before paid work whenever loading can
establish their absence.

## Failure and result integrity

- Zero selected or scored Cases cannot produce a plausible zero score.
- IFEval publishes no partial score when any selected Case lacks a valid verifier record. It
  retains every selected Case, attaches the bounded collected error to the affected Case, and
  returns a null Candidate score.
- DRACO likewise retains every selected Case and withholds the complete Candidate score when any
  Case is operationally ungraded or Judge coverage falls below the protocol threshold. Candidate
  output and valid grading evidence remain available for inspection.
- DRACO and IFEval Aggregation decode only their exact Engine-bound Case-evaluation envelopes.
  Neither searches nested text or arbitrary values for grading records, and neither has a
  compatibility fallback.
- Candidate-level failures are reserved for failures that cannot be attributed to a selected
  Case. The SDK's `Report.failures` includes Candidate, member, and Case failures.
- Provider finish reason and refusal remain distinguishable from empty successful text.
- Required retrieval never degrades silently: a missing Tavily key fails before model spend and
  Tavily authentication/transport failures surface as typed `web_retrieval_unavailable` errors.
- Benchmark id and revision travel into every Candidate result.
- No superseded resource shape, fallback model, default synthesizer, or silent error coercion
  remains.

## Deployment parity

Development and release workflows publish the same Benchmark-capable runner image topology. A
chart never references a Benchmark image the corresponding workflow did not build and push.
Local Evaluations and deployed Jobs use the same registry, route installation, and asset-root
rules.

## Non-goals

- A new URL4 grammar form or callable-binding feature.
- Benchmark-specific compilation in the SDK.
- A workflow or parameter DSL beside URL4.
- AI Gateway knowledge of Benchmark identity, Grading, or Aggregation.
- Public access to private verifier or rubric material.

## Acceptance

- Every resource is `screamingface.benchmark.v1`; no family schema is served or accepted.
- Flat ids select independently revisioned protocols, including slash-qualified ids.
- Complete linked artifacts execute through the ordinary URL4 core with no ScreamingFace-aware
  core behavior.
- Valid Models and Fusions succeed through `/candidate` with usage and cancellation intact.
- Candidate calls to private Benchmark routes or arbitrary absolute URLs fail inside the
  restricted Candidate world.
- Candidate recursion and total-invocation limits remain enforced.
- Variant-specific shape validation occurs exactly once and before Case evaluation or a paid
  Model call; every later member invocation uses the validated array.
- DRACO and IFEval empty selections fail execution; all-error selections return an unscored
  complete artifact with structured per-Case diagnostics.
- `draco/smoke` exercises the canonical DRACO execution seams with one pinned Case, one criterion,
  and one Judge pass, and is never described as a canonical or publishable DRACO score.
- `draco/lite` evaluates pinned Cases `2, 15`, ten criteria per Case, and one Judge pass per criterion;
  its selection rule and non-comparable status remain visible in repository documentation.
- URL4 Cloud's complete gate and focused cross-package Evaluation tests pass.
