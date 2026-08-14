---
title: OME-712 — Engine benchmark foundation
status: accepted
created: 2026-08-06
revised: 2026-08-07 (r2 — contract decisions forced by the branch review of the implementation)
ticket: OME-712
superseded_in_part_by: OME-836
related:
  - docs/plan/2026-08-06-OME-712-engine-benchmark-foundation.md
  - docs/work/2026-08-06-OME-712-engine-benchmark-foundation.md
  - docs/spec/2026-08-04-OME-712-url4-runtime-foundations.md
---

# Engine benchmark foundation

> Historical decision record. OME-836 supersedes the public benchmark identity and `variant`
> portions of this specification; see
> `docs/spec/2026-08-14-OME-836-flat-benchmark-identities.md` for the current contract.

## Purpose

The Engine needs one small extension seam for discovering and executing Engine-owned Benchmarks
before scored protocols such as DRACO or IFEval are installed. This landing defines that seam,
including Candidate Invocation, retrieval ceilings, and terminal provider outcomes. It installs no
scored Benchmark and owns no rubric or scoring rule.

## Benchmark definition and installation

Each immutable `Benchmark` has explicit metadata, a total `case_count`, a pure
`build(selected_case_count) -> Node`, and an installer that receives the shared `Url4Node` plus an
explicit immutable asset root.

- Definitions build structured URL4; rendering happens only at the public resource boundary.
- Every concrete definition installs independently. Installer identity is not an aliasing or
  deduplication mechanism.
- `Url4Node.endpoint()` and `Url4Node.data()` remain authoritative for path validity and collisions.
- Installation validates every definition at its full selection, renders it, and checks every
  literal relative reference against the routes actually installed in the shared world. A call and
  a data reference both name a route, and the routes come from `endpoint()` and from `data()`.
- A reference names a route only while each segment is literal. `/judge/$item` names no route
  before the Runner substitutes the row, and installation does not check it. Installation also
  does not fail on an iteration template that it cannot parse before substitution. These
  references stay unchecked; installation must not reject a legal Benchmark.
- Assets and routes are validated before the first model request. A broken definition fails the
  Runner world atomically; it is never omitted from discovery and never discovered half-working.
- A non-empty registry requires a declared AI Gateway model world.

The registry is static and immutable for a process. There is no dynamic Python loading and no
compatibility behavior for unreleased contracts.

## Public resource contract

- `GET /v1/benchmarks` returns metadata only. Each item includes `id`, `variant`, `revision`, total
  `case_count`, and `href`; URL4 text is not duplicated into the list.
- `GET /v1/benchmarks/{id}` returns one `screamingface.benchmark.v1` resource containing metadata,
  total `case_count`, authoritative `selected_case_count`, `candidate_binding`, and complete
  executable URL4 text.
- `candidate_binding` names the source the client binds its Candidate expression under. The
  protocol reads that name back as `$candidate`. A client must not infer the name, and the Engine
  publishes one helper that builds the linked expression.
- IDs are explicit and slash-qualified (`draco`, `draco/lite`, `draco/smoke`). There is no
  `default` alias.
- An omitted `limit` selects all cases. A supplied limit is exact and valid only when
  `1 <= limit <= case_count`; it is never clamped.
- Selection changes the rendered protocol and HTTP entity tag, but not the installed Benchmark
  revision.
- List and detail responses are deterministic and support `If-None-Match`.
- An Engine with no installed Benchmarks returns an honest empty list.

Benchmark-specific reducers must bind and validate the exact ordered selection in their own
protocol. The shared foundation publishes the authoritative count; DRACO and IFEval add their
case-ID checks in their respective runtime PRs.

## Candidate Invocation

When Benchmarks are installed, the Runner adds `/benchmarks/candidate` to the same `Url4Node` as
model and Benchmark routes. Candidate URL4 therefore uses ordinary URL4 composition: nested
Candidate calls and calls to other installed routes are valid. The adapter is not a new URL4 node
kind and does not create a second execution world.

Each invocation requires an explicit policy:

- `web_search=true|false` is mandatory.
- optional `web_search_exclude` is a non-empty colon-separated list of bare domains and is valid
  only when retrieval is enabled.
- unknown or malformed policy parameters fail closed.
- a nested invocation may disable retrieval or add exclusions, but cannot enable retrieval that
  its parent disabled.
- exclusions are inherited by union, so a nested call cannot remove its parent's guard.
- `web_search=true` grants both Runner-driven `web_search` and `web_fetch`; it does not force a
  model to call either tool.
- a route that cannot provide the required capability fails before its first paid model request.
- exclusions are sent to Tavily, re-applied to returned search rows, and checked before direct
  fetches.

General URL4 deadlines and cancellation bound execution. Candidate Invocation has no global,
cross-run counter and no special recursion rule.

## Candidate outcome contract

The adapter returns exactly:

```json
{
  "schema": "screamingface.candidate-invocation.v1",
  "output": "...",
  "finish_reason": "stop",
  "refusal": null
}
```

All four fields are required. `finish_reason` is a literal supported provider value or null;
`refusal` is literal non-empty provider text or null. No benchmark synthesizes a refusal and no
soft-refusal classifier is applied.

The Connector reports every model round trip through the existing observation stream. It reports
one terminal outcome per model call to a small task-local recorder. A tool loop makes more than
one round trip for one call, but only the round trip that returns content is terminal. A typed
`provider_refusal` is converted only at the Candidate seam into a normal envelope with an empty
output plus its exact finish/refusal fields. Timeouts, transport errors, malformed responses, and
all other failures still fail normally. Each scored Benchmark decides how a refusal affects its
denominator and score.

Candidate URL4 composes freely, so one Candidate scope can record more than one terminal outcome.
The recorder does not know which model call produced the returned text. Therefore the adapter
applies this rule:

- One recorded outcome describes the answer. The adapter reports it.
- Two or more recorded outcomes that agree also describe the answer. The adapter reports them.
- Two or more recorded outcomes that disagree describe different branches. The adapter reports
  null for `finish_reason` and null for `refusal`, which this contract permits.

The adapter must not report the most recent outcome. That rule gives one branch's fields to
another branch's answer. It can also put a refusal beside a non-empty output, and this contract
has no such shape. A Benchmark that needs the exact fields of each model call must invoke one
Candidate for each model call.

## Ownership

- `url4_cloud.benchmarks` owns definitions, registry validation, Candidate adaptation, and wire
  envelopes.
- `url4_cloud.rest.benchmarks` owns discovery and conditional HTTP responses.
- `url4_cloud.model_outcomes` and `url4_cloud.retrieval_policy` are task-local shared leaves used by
  the Connector and Candidate adapter; neither depends on the serving or Runner half.
- `url4_cloud.runner.connector` builds only AI Gateway model routes and reports model outcomes. It
  does not install or import Benchmark protocols.
- `url4_cloud.runner.main` is the composition boundary: it builds the model world, installs the
  Candidate adapter, injects the asset root, and installs the registry.
- the App, local mode, and Runner receive the same registry through dependency injection.

## Deferred deliberately

- DRACO/IFEval cases, prompts, judges, reducers, exact case-ID validation, and scoring.
- public paginated case browsing (`{id,input}` only), which needs the first real benchmark-owned
  case-source interface.
- SDK linking, decoding, report construction, and defensive selected-count verification. The
  Engine publishes the binding name and one linking helper; the SDK that consumes them is deferred.
- benchmark image, Helm, and workflow changes.
- run budgets and paid notebook gates.

## Acceptance

- A fetched exact-selection resource structurally links to a Candidate and executes.
- list discovery is one request and carries revision/count metadata.
- missing routes, duplicate routes, invalid limits, invalid policies, and unavailable retrieval
  fail before model spend.
- nested Candidate calls inherit retrieval policy without task leakage.
- Tavily search and fetch honor exclusions defensively.
- output, `finish_reason`, and `refusal` survive Candidate Invocation for one model call, and a
  tool loop stays one model call.
- a Candidate never gives one branch's `finish_reason` or `refusal` to another branch's answer,
  and never reports a refusal beside a non-empty output.
- the whole URL4 Cloud gate passes with the URL4 Engine importer guard expanded only to the
  explicitly owned `benchmarks/` extension subtree.
