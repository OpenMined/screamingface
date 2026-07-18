# OME-400 — ScreamingFace benchmark architecture implementation plan

**Status:** Phase 0 contract approved; implementation not started  
**Date:** 2026-07-18  
**Normative contract:**
[`docs/spec/2026-07-18-OME-400-benchmark-public-contract.md`](../spec/2026-07-18-OME-400-benchmark-public-contract.md)

This plan supersedes the unreleased benchmark SDK and notebook contracts. ScreamingFace has no
external SDK users yet, so implementation should target the approved design directly. Do not add
compatibility aliases or preserve temporary mock and in-process execution paths.

No implementation phase begins automatically from this document. Review each phase with the
ScreamingFace owner before changing runtime code, engine-profile routes, or notebooks.

## 1. Product boundary

The architecture has three clear layers:

```text
Researcher Python
  ScreamingFace SDK
    definitions, URL4 compilation, orchestration, grading, aggregation
             |
             | GET /v1?q=<complete URL4 expression>
             v
  sf-url4-engine profile
    registry, benchmark data, deterministic reducer routes, model routes
             |
             | POST /v1/chat/completions (engine-owned adapter only)
             v
  AI Gateway
```

Rules:

- ScreamingFace contacts only the configured URL4 engine over HTTP.
- Only the sf-url4-engine model-route adapter contacts AI Gateway.
- URL4 remains a generic expression engine; ScreamingFace-specific routes and manifests live in
  the sf-url4-engine profile.
- Importing ScreamingFace and constructing local definitions are network-free.
- The SDK does not ship a mock or in-process execution fallback.
- Until a hosted deployment exists, the default engine URL is `http://127.0.0.1:4404`.
  `sf.config(engine=...)` overrides it.
- The current `.docs/spikes/sf-url4-engine` stack is local development infrastructure. It is not
  the final application location and is not part of the public SDK contract.

Do not modify `packages/url4` or `apps/aigateway` to implement ScreamingFace behavior. The engine
profile composes their public capabilities.

## 2. Approved MVP surface

The complete contract is normative; this is the implementation checklist.

### SDK definitions and namespaces

- `sf.Case(id, input, reference=None, metadata=...)`
- `sf.Benchmark(id, title, cases, grader, aggregator, tools=())`
- `sf.Fusion(name, models, reducer, prompt=...)`
- abstract interfaces: `sf.Reducer`, `sf.Grader`, `sf.Aggregator`
- concrete strategies:
  - `sf.reducers.Model`, `sf.reducers.MajorityVote`
  - `sf.graders.ExactChoice`, `sf.graders.Rubric`
  - `sf.aggregators.Mean`
- immutable, serializable, in-memory `sf.Run`, `sf.Grades`, and `sf.Report`

There are no top-level concrete-strategy aliases and no `sf.judges` namespace.

### Discovery and loading

The configured engine exposes `GET /.well-known/screamingface`. The SDK provides:

```python
sf.models.list(query=None, tools=(), limit=None)       # -> list[str]
sf.benchmarks.list(query=None, tools=(), limit=None)  # -> list[str]
sf.benchmarks.load("draco@1")                         # -> sf.Benchmark
```

Public model IDs are URL4 routes without the leading slash. Engine-private provider mappings do
not leak into Fusion recipes or result records.

### Evaluation stages

```python
benchmark = sf.benchmarks.load("draco@1")
run = fusion.run(benchmark, first=5)
grades = run.grade()
report = grades.aggregate()
```

The equivalent façade is:

```python
report = fusion.evaluate("draco@1", first=5)
```

Each case produces one complete Fusion URL4 expression and one `GET /v1?q=...` request. The
engine returns plaintext containing a serialized JSON object. The SDK parses and validates that
object. Grading requests are separate from the Fusion request.

`run.grade()` grades the fused answer and every member by default so baseline and gain use the
same paired cases. Missing work remains missing; it is never converted to a zero.

### Benchmark responsibilities

A remotely loaded benchmark consists of a manifest plus a case-data route. The manifest selects
the public grader and aggregator configurations; the SDK performs stage orchestration. Direct
benchmark authoring uses ordinary Python and the same `sf.Benchmark` constructor. ScreamingFace
does not add an ETL DSL, case-browsing API, export/fork mechanism, or benchmark CLI in the MVP.

`sf.graders.ExactChoice` is deterministic and local. `sf.graders.Rubric` is orchestrated by the
SDK but sends every judge-model call through the URL4 engine. `sf.aggregators.Mean` is
deterministic and local.

### Engine-profile responsibilities

The sf-url4-engine profile owns:

- the discovery registry;
- model routes and their private AI Gateway mappings;
- versioned benchmark manifests and NDJSON case routes;
- deterministic RDS reducer routes such as `/sf/reducers/majority-vote`;
- `context -> user` and `intent -> system` mapping for model calls;
- forwarding declared model parameters and tools; and
- plaintext success responses and consistent URL4 error responses.

The profile does not need separate grader or aggregator registry entries. Exact grading and
aggregation are local; a model-backed grader invokes an already-advertised model route.

## 3. Phased implementation

### Phase 0 — lock the contract

Deliver documentation and syntax-only fixtures for GPQA, DRACO, an in-memory benchmark, and the
four-stage walkthrough.

Complete when:

- the spec, plan, work record, and fixtures agree;
- fixtures parse without importing the unimplemented API;
- old mock, persistence, export, and provider-ID assumptions are absent; and
- no runtime files have changed.

### Phase 1 — core values and discoverable engine profile

Implement the minimum SDK and engine-profile foundation together.

SDK:

- engine configuration with the temporary localhost default;
- `Case`, `Benchmark`, reducer/grader/aggregator strategies, and validation;
- internal HTTP client and typed transport/protocol errors;
- model and benchmark `.list(...)` methods;
- manifest retrieval and conversion into a `Benchmark`; and
- preflight validation of models, tools, reducer route, cases, and response schema.

sf-url4-engine profile:

- `/.well-known/screamingface`;
- canonical public model IDs and supported-tool declarations;
- versioned GPQA and DRACO manifests and normalized NDJSON case routes; and
- an advertised `/sf/reducers/majority-vote` route identity.

Complete when the Phase 0 fixtures construct against the real public types and the SDK can list
and load the profile's benchmarks over HTTP. Invalid and incompatible manifests must fail before
model calls.

### Phase 2 — Fusion compiler and run stage

Implement:

- URL4 compilation from string and mapping model specifications;
- stable `panel_1`, `panel_2`, ... identities;
- one complete Fusion expression per case;
- HTTP evaluation through only `GET /v1?q=...`;
- plaintext JSON parsing and strict `screamingface.fusion-result.v1` validation;
- deterministic reducer routing and model-reducer compilation;
- bounded case concurrency (initial policy: four); and
- immutable in-memory `Run` results and failures.

The sf-url4-engine profile implements the model route mappings and deterministic majority-vote
RDS route needed by those expressions. The model adapter is the only component that contacts AI
Gateway.

Complete when real HTTP contract tests cover model and deterministic reducers, malformed
plaintext, partial failures, stable result ordering, and no direct gateway traffic from the SDK.

### Phase 3 — grading and aggregation

Implement:

- `ExactChoice` grading without engine calls;
- `Rubric` grading with one URL4 judge request per criterion per pass;
- official DRACO positive/negative criterion semantics and weighted scoring;
- five independent DRACO passes and strict coverage requirements;
- bounded judge concurrency (initial policy: 32);
- immutable `Grades` with scores, metrics, verdicts, coverage, and failures;
- paired-case `Mean` aggregation; and
- `Report.score`, `baseline`, `gain`, member scores, and coverage on a `0..1` scale.

The sf-url4-engine model adapter must map URL4 context to the user message and intent to the
system message, forward judge parameters, and allow independent repeated calls. No separate
grader or aggregator engine routes are introduced.

Complete when `fusion.evaluate(...)` equals `run -> grade -> aggregate`, GPQA and DRACO use the
same framework objects, and failed/unresolved work never becomes a zero score.

### Phase 4 — canonical GPQA and DRACO validation

Harden the Phase 1 manifests and stable case streams against their canonical sources. They use
the same public `Benchmark` and `Case` semantics available to researchers. Pin upstream dataset
revisions inside the publisher, not in the researcher-facing call.

Complete when:

- `sf.benchmarks.load("gpqa@1")` and `load("draco@1")` recreate equivalent typed definitions;
- cases have stable identities and sealed references;
- DRACO declares `web_search` and the official Rubric configuration; and
- repeated loads are deterministic.

### Phase 5 — notebooks and public documentation

Regenerate the tutorial series from the approved SDK rather than building compatibility around
the current notebooks. Cover:

- a bare-bones quickstart;
- configuration and architecture;
- model and benchmark discovery;
- Fusion construction in Python and YAML;
- explicit stage inspection;
- custom local benchmark definitions; and
- a clearly labeled DRACO reproduction.

Every executable notebook must use the HTTP URL4 engine. Document the local Docker prerequisite
and Hugging Face access where applicable. Show raw URL4 requests and plaintext responses only in
architecture/deep-dive material, not in the shortest quickstart.

Complete when notebooks run top to bottom against the configured Docker stack and contain no
mock-mode or in-process fallback.

Before promoting the hidden spike, agree the engine profile's final location and ownership. If
it moves to `apps/sf-url4-engine`, preserve the same external contract rather than its temporary
filesystem layout.

### Future phases — explicitly deferred

Design separately when the infrastructure exists:

- authentication and provider connection UX;
- usage, pricing, cost, and enforceable budgets;
- persistence, resume, caches, and distributed execution;
- hashes, publication, attestation, and verified hosted evaluation;
- leaderboard submission and anti-cheating policy;
- richer search/ranking and multiple simultaneous engine clients; and
- multi-round orchestration graphs beyond one panel-and-reducer Fusion.

These are additive concerns, not hidden MVP requirements.

## 4. Cross-side completion matrix

| Capability | ScreamingFace SDK | sf-url4-engine profile |
|---|---|---|
| Configure engine | Store/resolve one base URL | Bind and publish the service |
| Discover models | Parse/filter registry | Advertise route IDs and tools |
| Load benchmark | Fetch/validate manifest and cases | Serve manifest and NDJSON cases |
| Run Fusion | Compile and send complete URL4 | Evaluate expression and model/reducer routes |
| Model execution | Never call Gateway | Map route to AI Gateway and return plaintext |
| Majority vote | Compile RDS call | Execute deterministic route without Gateway |
| ExactChoice grade | Execute locally | No responsibility |
| Rubric grade | Schedule criterion/pass requests | Preserve model-call semantics and parameters |
| Aggregate | Execute paired Mean locally | No responsibility |
| Failures | Preserve typed per-case/per-grade failures | Return stable HTTP/URL4 errors |

## 5. Test strategy

### Contract and value tests

- constructor validation and immutability;
- JSON serialization for `Case`, `Run`, `Grades`, and `Report`;
- sealed references never appear in model expressions;
- only namespaced concrete strategies are exported; and
- public scores remain `0..1` while widgets format percentages.

### Registry and manifest tests

- discovery filtering by query, tools, and limit;
- model ID/route identity;
- benchmark version IDs remain opaque strings;
- malformed/unsupported manifests fail before model calls; and
- incompatible tools, reducer routes, or response schemas fail preflight.

### URL4 compiler and HTTP tests

- one request per Fusion case;
- stable panel mapping and nested member result structure;
- arrays are not emitted inside URL4 inline structs;
- model and deterministic reducer paths;
- plaintext JSON parsing and schema rejection; and
- timeout, transport, HTTP, parse, and execution errors remain distinguishable.

### Grading and aggregation tests

- ExactChoice normalization;
- one DRACO call per criterion per pass;
- positive/negative criterion scoring and five-pass averaging;
- incomplete judge coverage produces a missing score, not zero;
- Fusion and every member use the same selected cases; and
- `evaluate()` has exact stage parity with explicit orchestration.

### Docker integration tests

- registry and health checks;
- one model request reaches AI Gateway only through the engine;
- majority vote makes no AI Gateway request;
- context, intent, params, and tools arrive at the adapter correctly; and
- engine success is plaintext and SDK parsing produces the typed result.

## 6. Repository map

Expected areas, subject to phase review:

```text
packages/screamingface/src/screamingface/
  config and internal engine HTTP client
  models and benchmarks registries
  benchmark/case values
  fusion compiler and execution
  reducers, graders, aggregators
  run, grades, report values

packages/screamingface/tests/
  unit and HTTP contract tests

apps/sf-url4-engine/                 # proposed final owner/location
  URL4 profile, manifests, routes, Docker wiring

packages/screamingface/examples/
  quickstarts, architecture, GPQA, DRACO
```

The actual module split should follow repository conventions found during implementation. Public
names and behavioral boundaries are fixed by the spec; private filenames are not.

## 7. Immediate next step

After Phase 0 is committed, review Phase 1 with the owner before coding. The first implementation
slice should be value types plus registry/manifest contract tests. It must not also introduce
authentication, persistence, notebooks, or engine-profile deployment.
