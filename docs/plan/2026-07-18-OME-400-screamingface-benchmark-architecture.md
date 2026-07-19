# OME-400 — ScreamingFace benchmark architecture implementation plan

**Status:** Phase 3D implemented; Phase 4 contract review next
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
  screamingface-engine (one persistent Python/ASGI process)
    Url4Node evaluator, registry, benchmark data, in-process reducer/model handlers
             |
             | POST /v1/chat/completions (engine-owned adapter only)
             v
  AI Gateway
```

Rules:

- ScreamingFace contacts only the configured URL4 engine over HTTP.
- Only the screamingface-engine model-route adapter contacts AI Gateway.
- `screamingface-engine` constructs one `Url4Node` at startup and serves its ASGI application with
  Uvicorn. Model and reducer handlers execute inside that persistent process.
- Phase 2 uses the public `Url4Node` registration API, not the `url4 serve` TOML `[commands]`
  subprocess adapter. The engine executable is never launched recursively to handle a route.
- URL4 remains a generic expression engine; ScreamingFace-specific routes and manifests live in
  the screamingface-engine profile.
- Importing ScreamingFace and constructing local definitions are network-free.
- The SDK does not ship a mock or in-process execution fallback.
- Until a hosted deployment exists, the default engine URL is `http://127.0.0.1:4404`.
  `sf.config(engine=...)` overrides it with an HTTP(S) origin (no path, query, or fragment).
- The tracked `packages/screamingface/apps/screamingface-engine` stack is temporary local development
  infrastructure. It is not part of the Python wheel or the final application boundary.

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
- immutable, serializable, in-memory `sf.Run`, `sf.Grades`, and `sf.Report`, including their
  exported inspection records (`CaseGrades`, `Grade`, `CriterionVerdict`, `GradeFailure`, and
  `MemberReport`)

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

The screamingface-engine profile owns:

- the discovery registry;
- one canonical model catalog that owns route registration, public discovery fields, and private
  AI Gateway mappings;
- persistent model handlers registered with `node.endpoint(...)` at process startup;
- versioned benchmark manifests and NDJSON case routes;
- deterministic RDS reducer routes such as `/reducers/majority-vote`;
- `context -> user` and `intent -> system` mapping for model calls;
- typed, allowlisted forwarding of declared model parameters and named tools;
- extraction of the first AI Gateway assistant text as the URL4 endpoint result; and
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

screamingface-engine profile:

- `/.well-known/screamingface`;
- canonical public model IDs and supported-tool declarations;
- a versioned GPQA manifest and normalized NDJSON case route; and
- an advertised deterministic reducer route identity. Phase 2 replaces Phase 1's provisional
  namespaced route with `/reducers/majority-vote` before it becomes executable. No compatibility
  alias is retained because the SDK is unreleased.

Complete when the Phase 0 fixtures construct against the real public types and the SDK can list
and load the profile's benchmarks over HTTP. Invalid and incompatible manifests must fail before
model calls.

The owner approved one development-only Phase 1 engine-profile walkthrough after implementation.
It documents and smoke-tests this boundary without introducing model execution. Regenerating the
public quickstart, architecture, and DRACO tutorial series remains Phase 5.

### Phase 2 — Fusion compiler and run stage

Implementation is split into reviewed vertical slices. Phase 2A now implements the persistent
engine lifecycle, canonical model route registration, typed parameter translation, shared AI
Gateway client, plaintext extraction, unprefixed benchmark resources, admission control, and
whole-evaluation timeout. Its registry is intentionally tool-free and excludes the unavailable
`gemini/3.1-pro-preview` route. Phase 2B now adds the SDK-owned exact-string majority selector,
its in-process `/reducers/majority-vote` adapter, complete-expression coverage, and no-mock Docker
topology proof. Phase 2C now implements the approved compiler and in-memory `Run` stage.

SDK:

- canonical `fusion.url4` template compilation from string and mapping model specifications using
  URL4's public builder/AST facade and certified renderer;
- stable `member_1`, `member_2`, ... identities;
- the question as member context and the member prompt as intent, with the minimal default
  `"Answer the question."`;
- automatic labeled question/panel context for model reducers;
- one complete Fusion expression per case;
- HTTP evaluation through only `GET /v1?q=...`;
- plaintext JSON parsing and strict `screamingface.fusion-result.v1` validation;
- deterministic reducer routing and model-reducer compilation;
- bounded case concurrency (initial policy: four); and
- immutable in-memory `Run`, `CaseResult`, `MemberResult`, and `RunFailure` values with
  JSON-compatible `run.to_dict()`.

`member_n` is the single slot identity used by URL4 bindings and every SDK result layer. “Panel”
may describe the group in researcher-facing prose, but does not create separate `panel_n` keys.

Each case evaluation is atomic. Any required panel or reducer failure invalidates that case; the
engine returns a non-success URL4 response rather than a partial Fusion envelope. The SDK records
the failure at the case's original position and continues other selected cases. It never converts
missing work to an empty answer or zero score, never grades a failed run case, and performs no
automatic Phase 2 retry—including 503—that could duplicate paid model calls. Once execution
begins, it does not cancel unrelated selected cases.

`Fusion.run(str | Benchmark, first=...)` is synchronous and notebook-safe. `first` selects only a
stable canonical prefix; there is no seed. Phase 2C deliberately does not add `evaluate()`,
grading, aggregation, persistence, resume, public concurrency controls, or retry controls.

Persistent screamingface-engine:

- construct one `Url4Node("screamingface-engine", eval_path="/v1")` per process;
- construct one reusable asynchronous AI Gateway client per process;
- replace the provisional Phase 1 resource namespace with `/benchmarks/<id>`,
  `/benchmarks/<id>/cases`, and `/reducers/majority-vote` before execution ships;
- register every advertised model route in-process from the canonical model catalog;
- register `/reducers/majority-vote` as an in-process deterministic endpoint;
- serve registry, manifest, case, and health reads through the same node;
- wrap `node.asgi()` with a thin application-owned lifecycle/admission layer that starts and closes
  the Gateway client, limits global in-flight evaluations, applies a whole-evaluation timeout, and
  closes node-owned resources during graceful shutdown; and
- remain framework-free beyond URL4's ASGI application and Uvicorn server.

One model endpoint receives URL4's decoded `Request(path, context, intent, params)` and performs:

```text
public route        -> private AI Gateway model ID
context             -> user message content
intent              -> system message content
temperature         -> validated float
max_tokens          -> validated positive integer
reasoning           -> validated AI Gateway reasoning_effort
tools=web_search    -> engine-owned named-tool translation
```

Unknown parameters, malformed values, and unsupported tools fail before an AI Gateway request.
The adapter sends `POST /v1/chat/completions`, validates the response envelope, returns only the
first assistant message's text to URL4, and turns upstream transport/status/schema failures into a
transient URL4 `ResolutionError`. It never returns an AI Gateway JSON envelope to the SDK.

The native `url4 serve` TOML wrapper remains useful for subprocess-backed deployments, but it is
not the composition root for this application. Phase 2 must not import URL4's private `_serve`
module merely to reuse its CLI-only command or ASGI helpers. The application wrapper contains no
routes, URL4 parsing, or expression logic: it delegates every accepted HTTP request to
`node.asgi()`, returns 503 when its in-flight limit is full, and returns 504 when the configured
whole-evaluation deadline expires.

Phase 2B's Docker smoke proves a complete literal URL4 reducer expression through the real
persistent container and proves that a model route reaches the real AI Gateway service (a
credential-free Gateway error is an acceptable topology result). No runtime mock or route-handler
subprocess participates. Phase 2C extends that smoke through public `Fusion.run()`: it proves the
SDK -> persistent engine -> AI Gateway topology and either validates a provider-backed result or
the expected atomic credential-free failure. Successful provider-backed expression evaluation is
also covered at the real persistent-node boundary with a controlled Gateway transport.

Phase 2 is complete when real HTTP contract tests cover model and deterministic reducers,
malformed plaintext, partial failures, stable result ordering, parameter translation, and no
direct gateway traffic from the SDK. One Docker integration test must prove the complete SDK ->
persistent engine -> AI Gateway path without a route-handler subprocess.

### Phase 3 — grading and aggregation

Phase 3A is the completed review-only contract unit. The approved behavior is:

- `run.grade()` grades the captured Fusion answer and every captured member without rerunning
  worker models; failed run cases receive no grading work;
- `ExactChoice` ports the proven A–J/numeric-string/full-text normalization behavior and makes no
  engine call; an unparseable non-blank answer is a valid incorrect answer, while benchmark
  publishers must normalize references to strings;
- `Rubric` makes one ordinary URL4 judge-model request per criterion per pass, maps judge context
  to the user message and the pinned prompt to the system message, and never uses a separate
  grader route;
- every rubric selected for a grading call is validated before judge spend;
- judge requests have a 16-request internal concurrency bound, matching the current engine's
  admission limit, and stable evidence order;
- transport failures are never retried by the SDK; invalid judge output alone receives up to two
  byte-identical retries;
- official DRACO uses five byte-identical independent passes, positive/negative criterion
  semantics, weighted section/overall scores, and a local unweighted `pass_rate` metric;
- rubric grades require 100% verdict coverage; missing work produces `score=None`, not a zero,
  inferred `UNMET`, or partial diagnostic score;
- immutable nested `Grades -> CaseGrades -> Grade -> CriterionVerdict` values preserve complete
  evidence and typed failures;
- `Mean` uses one strict common paired case set for the Fusion and every member; and
- immutable `Report`/`MemberReport` values expose score, baseline, gain, coverage, metrics, and
  failures on a `0..1` scale.

The screamingface-engine model adapter must map URL4 context to the user message and intent to the
system message, forward judge parameters, allow independent repeated calls, and keep AI Gateway
response caching disabled for judge work. No separate grader or aggregator engine routes are
introduced. `ExactChoice` and `Mean` remain deterministic SDK computations.

Implementation is split so the public values and deterministic behavior can be reviewed before
the paid model-backed path:

- **Phase 3B (implemented):** immutable grading values/failures, exact-choice normalization and
  reference validation, plus focused contract tests. It deliberately does not expose
  `Run.grade()` while Rubric remains unimplemented;
- **Phase 3C (implemented):** complete `Run.grade()` dispatch, rubric preflight,
  URL4 judge orchestration, response validation/retries, strict coverage/scoring, and evidence
  retention; and
- **Phase 3D (implemented):** paired Mean aggregation, immutable reports, stable Fusion/member
  identity at every result layer, and the exact `Fusion.evaluate()` facade over
  `run -> grade -> aggregate`.

Each implementation slice requires owner review before runtime changes begin.

Complete when `fusion.evaluate(...)` equals `run -> grade -> aggregate`, GPQA and DRACO use the
same framework objects, and failed/unresolved work never becomes a zero score.

### Phase 4 — canonical GPQA and DRACO validation

Harden GPQA and add DRACO only when both publications are runnable against their canonical
sources. They use the same public `Benchmark` and `Case` semantics available to researchers. Pin
upstream dataset revisions inside the publisher, not in the researcher-facing call.

Complete when:

- `sf.benchmarks.load("gpqa@1")` and `load("draco@1")` recreate equivalent typed definitions;
- cases have stable identities and sealed references;
- DRACO is advertised only after the engine exposes its judge model and working `web_search`
  adapter, and declares the official Rubric configuration; and
- repeated loads are deterministic.

### Phase 5 — notebooks and public documentation

Regenerate the tutorial series from the approved SDK rather than building compatibility around
the current notebooks. Cover:

- a bare-bones quickstart;
- configuration and architecture;
- model and benchmark discovery;
- Fusion construction in Python;
- explicit stage inspection;
- custom local benchmark definitions; and
- a clearly labeled DRACO reproduction.

Every executable notebook must use the HTTP URL4 engine. Document the local Docker prerequisite
and Hugging Face access where applicable. Show raw URL4 requests and plaintext responses only in
architecture/deep-dive material, not in the shortest quickstart.

Complete when notebooks run top to bottom against the configured Docker stack and contain no
mock-mode or in-process fallback.

Before promoting the temporary package-development app, agree the engine profile's final
location and ownership. If it moves to `apps/screamingface-engine`, preserve the same external
contract rather than its temporary filesystem layout.

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

| Capability | ScreamingFace SDK | screamingface-engine profile |
|---|---|---|
| Configure engine | Store/resolve one HTTP(S) origin | Bind and publish the service |
| Discover models | Parse/filter registry | Advertise route IDs and tools |
| Load benchmark | Fetch/validate manifest and cases | Serve manifest and NDJSON cases |
| Run Fusion | Compile and send complete URL4 | Evaluate it in one persistent `Url4Node` process |
| Model execution | Never call Gateway | Run in-process handler, call AI Gateway, return text |
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
- stable member mapping and nested member result structure;
- arrays are not emitted inside URL4 inline structs;
- model and deterministic reducer paths;
- one startup registration per advertised model route, with no per-call engine subprocess;
- context/user, intent/system, typed parameter, and named-tool translation;
- application-owned ASGI admission, timeout, and shutdown behavior without FastAPI, Hono, or a
  private URL4 import;
- plaintext JSON parsing and schema rejection; and
- timeout, transport, HTTP, parse, and execution errors remain distinguishable; and
- one failed case does not cancel unrelated cases, change result order, produce a partial
  envelope, become a zero, or trigger an SDK retry.

### Grading and aggregation tests

- ExactChoice A–J/index/explicit-marker/full-text normalization and false-positive guards;
- malformed exact references fail preflight while unparseable model answers score zero;
- one DRACO call per target, criterion, and pass through the advertised model route;
- invalid judge output alone receives two byte-identical retries; transport failures do not;
- positive/negative criterion scoring, section metrics, pass rate, and five-pass averaging;
- incomplete judge coverage produces a missing score and retained evidence, not zero;
- Fusion and every member use the same strict paired cases;
- nested immutable values and stable JSON-compatible serialization; and
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

packages/screamingface/apps/screamingface-engine/  # temporary package-development location
  persistent Url4Node app, model/Gateway adapter, manifests, routes, Docker wiring

apps/screamingface-engine/                 # proposed final owner/location after approval

packages/screamingface/examples/
  quickstarts, architecture, GPQA, DRACO
```

The actual module split should follow repository conventions found during implementation. Public
names and behavioral boundaries are fixed by the spec; private filenames are not.

## 7. Immediate next step

Review Phase 4 canonical GPQA/DRACO publication against the implemented SDK values before
changing engine manifests, routes, or notebooks. Keep authentication, persistence, budgets, and
notebook regeneration out of that contract review.

The current local engine profile intentionally does not advertise or serve DRACO: it lacks the
`gemini/3.1-pro-preview` judge route, and its model routes do not advertise `web_search`. Adding
those real capabilities and the canonical publication is Phase 4 engine-profile work.
