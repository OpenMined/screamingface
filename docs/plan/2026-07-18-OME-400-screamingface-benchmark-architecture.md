# OME-400 — ScreamingFace benchmark architecture implementation plan

**Status:** Phase 5 notebook suite implemented; release-readiness review next
**Date:** 2026-07-18  
**Last updated:** 2026-07-19
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
    installed benchmark definitions, dataset access, URL4 compilation,
    orchestration, grading, aggregation
             |
             | GET /v1?q=<complete URL4 expression>
             v
  screamingface-engine (one persistent Python/ASGI process)
    Url4Node evaluator, executable registry, in-process reducer/model handlers
      |                              |
      | model turns                  | search / bounded public-page reads
      v                              v
  AI Gateway                     internal SearXNG
```

Rules:

- ScreamingFace contacts only the configured URL4 engine over HTTP.
- Only the screamingface-engine model-route adapter contacts AI Gateway.
- `screamingface-engine` constructs one `Url4Node` at startup and serves its ASGI application with
  Uvicorn. Model and reducer handlers execute inside that persistent process.
- Phase 2 uses the public `Url4Node` registration API, not the `url4 serve` TOML `[commands]`
  subprocess adapter. The engine executable is never launched recursively to handle a route.
- URL4 remains a generic expression engine; ScreamingFace-specific executable routes and
  capability metadata live in the screamingface-engine profile.
- Canonical benchmark definitions and source loaders live in the SDK. Gated data and answer keys
  are loaded through the researcher's process and are never published by the engine.
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

The configured engine exposes executable capabilities at `GET /.well-known/screamingface`.
The SDK separately exposes its installed canonical benchmark catalog:

```python
sf.models.list(query=None, tools=(), limit=None)       # -> list[str]
sf.benchmarks.list(query=None, tools=(), limit=None)  # -> list[str]
sf.benchmarks.load("draco@1")                         # -> sf.Benchmark
```

Public model IDs are URL4 routes without the leading slash. Engine-private provider mappings do
not leak into Fusion recipes or result records. `sf.benchmarks.list/load` perform no engine
request; loading uses the caller's ordinary dataset credentials.

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

A canonical benchmark is an SDK-installed Python definition that pins its source, validates and
normalizes it into `Case` values, and selects public grader and aggregator configurations. Direct
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
- engine-backed model discovery plus SDK-local benchmark `.list(...)` and `.load(...)`;
- canonical local source loading and conversion into a `Benchmark`; and
- preflight validation of models, tools, reducer route, cases, and response schema.

screamingface-engine profile:

- `/.well-known/screamingface`;
- canonical public model IDs and supported-tool declarations;
- an advertised deterministic reducer route identity. Phase 2 replaces Phase 1's provisional
  namespaced route with `/reducers/majority-vote` before it becomes executable. No compatibility
  alias is retained because the SDK is unreleased.

Complete when the Phase 0 fixtures construct against the real public types, the SDK can discover
engine models, and installed benchmarks list/load without contacting the engine. Invalid source
data and incompatible execution capabilities must fail before model calls.

The owner approved one development-only Phase 1 engine-profile walkthrough after implementation.
It documents and smoke-tests this boundary without introducing model execution. Regenerating the
public quickstart, architecture, and DRACO tutorial series remains Phase 5.

### Phase 2 — Fusion compiler and run stage

Implementation is split into reviewed vertical slices. Phase 2A now implements the persistent
engine lifecycle, canonical model route registration, typed parameter translation, shared AI
Gateway client, plaintext extraction, admission control, and
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
- replace the provisional Phase 1 reducer namespace with `/reducers/majority-vote` before
  execution ships;
- register every advertised model route in-process from the canonical model catalog;
- register `/reducers/majority-vote` as an in-process deterministic endpoint;
- serve executable registry and health reads through the same node;
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
- rubric grading supports any validated positive pass count. The Phase 4 `draco@1` publication
  pins three byte-identical independent passes to match the benchmark pipeline, with
  positive/negative criterion semantics, weighted section/overall scores, and a local
  unweighted `pass_rate` metric;
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
upstream dataset revisions inside the SDK definition, not in the researcher-facing call.

The approved canonical publications are:

- **GPQA:** `Idavidrein/gpqa`, subset `gpqa_diamond`, split `train`, revision
  `633f5ee89ab8ad4522a9f850766b73f62147ffdd`; exactly 198 unique source `Record ID` values;
  a fixed SHA-256-derived option permutation per record; source `High-level domain` and
  `Subdomain` mapped to `domain` and `subdomain` metadata; and the exact A-D prompt ending
  `Reply with only A, B, C, or D.`;
- **DRACO:** `perplexity-ai/draco`, default configuration, split `test`, revision
  `ce076749809027649ebd331bcb70f42bf720d387`, with source JSONL SHA-256
  `e35bfe78cd827fa1d541b79fbc7bc7b91966d3227d8742c83e99d26d4ac4679a`; exactly 100
  source-order UUID cases, ten domains, four rubric sections per case, and 3,934 criteria; and
- both definitions validate the complete source/schema before yielding cases and cache the
  normalized immutable cases once per researcher process. Dataset reads never contact the URL4
  engine or AI Gateway.

**Phase 4A is implemented:** GPQA now lives in an SDK-local benchmark module, loads the pinned
revision lazily through the researcher's Hugging Face session, validates all 198 rows, uses source Record IDs and metadata,
renders SHA-256-stable choices, and caches the normalized tuple once per process. A live check
against the pin confirmed all 198 cases. The source contains one pair of duplicate distractors;
the publisher preserves that canonical row and rejects only a collision between the correct
answer and a distractor.

`draco@1` follows the executable benchmark pipeline contract rather than claiming literal paper
parity: judge route `gemini/3.1-pro-preview`, three passes, temperature `0.2`, reasoning `low`,
`max_tokens=4096`, and the official Appendix C.5 per-criterion judge system prompt. The prompt is pinned by
SHA-256 `dbc1ae32e32be6fbc47180b4a246b997d299bb0e25373a8cde87c6461cb2397b` (5,196
UTF-8 bytes). Every Fusion/member target receives one independent request per criterion per pass;
invalid judge output alone gets up to two byte-identical retries. Judge concurrency remains the
SDK's internal 16-request bound until engine capacity is reviewed separately. The SDK retains its stricter publication rule: incomplete
verdict coverage keeps the evidence but produces `score=None`.

The DRACO benchmark declares `tools=("web_search",)`. The compiler adds that named capability
only to answer-producing Fusion member routes. Reducers, model synthesizers, and rubric judges do
not inherit it. In the engine, `web_search` means the complete named research capability needed
to search and open/fetch sources; its provider-specific payload is allowlisted and tested rather
than forwarding the string blindly. The profile blocks access to benchmark rubrics, references,
and result sources through this capability.

**Phase 4C is implemented:** tool identifiers are ordered, unique lowercase capability names;
`tools` is reserved from generic model parameters; and concrete case expressions encode benchmark
capabilities only on member calls. One tool renders as `tools=web_search`; multiple tools use the
canonical URL-query form `tools=web_search+code_execution`. The benchmark-independent
`fusion.url4` template and `run.fusion_url4` remain unchanged. URL4 transports and decodes the
parameter generically.

**Phase 4D is implemented:** the development engine owns a bounded standard model-tool loop,
translates the single public `web_search` capability into internal `web_search` and `web_fetch`
functions, uses a pinned keyless SearXNG container for discovery, safely reads bounded public
HTML/plaintext pages, and returns only the final assistant plaintext. Every model turn still goes
through the unchanged AI Gateway chat-completions endpoint. Unsafe targets and malformed calls
fail closed; a transient failure reading one page is returned as tool output so the model can use
other evidence. Gemini and Claude advertise the capability only when SearXNG is configured;
Codex remains tool-free.

The engine registry remains minimal and advertises only executable models and reducers. DRACO is
present in the SDK catalog now that its local definition is complete. Phase 4D made compatible
web-search Fusion members executable; at that phase boundary, complete evaluation still required
the judge route. The
stronger Phase 5 reproduction gate additionally requires the complete benchmark-pipeline model
lineup. Success bodies remain plaintext URL4 results; tool/cost telemetry, budgets, provider
selection, tool profiles, and verified server-side scoring remain deferred.

**Phase 4E0 is implemented:** generic model and rubric-judge context is held as native quoted
URL4 binding data rather than inserted into expression structure. The engine registry requires an
exact encoded request-target limit; the SDK validates every selected run expression before model
spend and every rubric task before judge spend. The development profile advertises and enforces
61440 bytes with HTTP 414, while Uvicorn/h11 receives 131072 bytes of parsing headroom. The 60 KiB
application limit leaves 4 KiB for the configured origin under `httpx`'s 64 KiB absolute-URL
ceiling. GET
remains the only transactional URL4 transport. There is no truncation, POST fallback, compression,
partial grading, or change to URL4 or AI Gateway.

**Phase 4E1 is implemented:** the development engine exposes the ordinary tool-free
`gemini/3.1-pro-preview` model route and maps it to
`gemini-cli/gemini-3.1-pro-preview`. It reuses the generic model/Gateway adapter, preserves the
official system/user message split and allowlisted judge parameters, returns assistant JSON as
plaintext, and makes every pass an independent Gateway request. Gateway rejection, connection,
timeout, and malformed responses remain safe transient `502 resolution_failed` URL4 errors with
no retry. This slice assumes the AI Gateway owner registers the mapped model; it changes neither
AI Gateway nor URL4.

Complete when:

- `sf.benchmarks.load("gpqa@1")` and `load("draco@1")` recreate equivalent typed definitions;
- cases have stable identities and sealed references;
- DRACO is listed by the SDK only after its local definition is complete, and can run only when
  the engine exposes its judge model and working `web_search` adapter;
- repeated loads are deterministic.

### Phase 5 — notebooks and public documentation

Regenerate the tutorial series from the approved SDK rather than building compatibility around
the current notebooks. Cover:

- a bare-bones quickstart;
- configuration and architecture;
- model and benchmark discovery;
- Fusion construction in Python;
- explicit stage inspection;
- custom local benchmark definitions;
- a clearly labeled DRACO SDK walkthrough; and
- later, a full DRACO reproduction only after the complete benchmark-pipeline model lineup is
  executable.

Every executable notebook must use the HTTP URL4 engine. Document the local Docker prerequisite
and Hugging Face access where applicable. Show raw URL4 requests and plaintext responses only in
architecture/deep-dive material, not in the shortest quickstart.

Complete when notebooks run top to bottom against the configured Docker stack and contain no
mock-mode or in-process fallback.

**Phase 5A is implemented:** `examples/05_draco.ipynb` uses the canonical `draco@1` definition with
an available Gemini 2.5 and Claude Sonnet 4.6 web-research panel plus a Codex model reducer. It
teaches explicit `run -> grade -> aggregate` stages and documents `Fusion.evaluate(...)` only as
their exact convenience equivalent, so researchers do not accidentally execute the paid workflow
twice. The parameterized public `fusion.url4` and HTTP `GET /v1?q=...` boundary are shown; the
notebook does not import private compiler functions merely to expose a concrete case expression.

Live execution defaults off and produces no substitute result. The notebook explains that a
two-member Fusion creates three answer targets and that DRACO's 3,934 criteria across 100 cases,
three judge passes, and Fusion-plus-member grading imply roughly 354 judge calls for an average
single case. The walkthrough is a valid evaluation of that named Fusion, not a reproduction of
the benchmark pipeline's seven standalone models and nine named fusions. Full reproduction remains
gated on the complete registered panel/synthesizer lineup plus separately reviewed persistence and
cost assumptions.

**Phase 5B is implemented:** `examples/00_quickstart.ipynb` is the shortest supported product path.
It configures one engine, constructs one three-member Fusion with `MajorityVote`, evaluates five
canonical `gpqa@1` cases, and reads `score`, `baseline`, and `gain`. It does not show model or
benchmark discovery, raw URL4, registry/response schemas, explicit execution stages, custom
benchmarks, or private APIs; those belong in deeper walkthroughs.

The five-case example implies 15 provider-backed member calls and no model-backed grading or
reduction. Until enforceable budgets exist, the one live `evaluate(...)` call defaults off and
creates no substitute report. The quickstart still documents the local Docker stack, caller-owned
Hugging Face access, and external provider-credential prerequisite.

**Phase 5C is implemented:** `examples/01_architecture.ipynb` replaces the broad development-only
Phase 1 walkthrough. It explains engine configuration, the SDK/engine/Gateway/tool ownership
boundary, raw registry plaintext and validated model discovery, `fusion.url4` recipe identity, and
one concrete encoded transactional GET. The executed expression uses URL4's public builders to
call only the deterministic majority-vote route with literal answers, so the notebook runs against
the Docker stack without dataset or provider access.

The old `phase_1_engine_profile.ipynb`, its generator, and its CI regeneration step are removed
rather than retaining overlapping public documentation. The replacement must not load a
benchmark, execute a model-backed Fusion, import a private compiler or engine implementation, or
contact AI Gateway directly.

**Phase 5D is implemented:** `examples/02_discovery.ipynb` teaches the two discovery boundaries without
mixing in execution. Model IDs come from `sf.models.list(...)` against the configured engine and
demonstrate the existing `query`, `tools`, and `limit` filters. Benchmark IDs come from the
installed SDK through `sf.benchmarks.list(...)` with the same filters; listings remain plain IDs,
not a new summary or metadata contract.

The notebook explains that `sf.benchmarks.load("gpqa@1")` materializes the canonical typed
definition and may fetch its source with the researcher's ordinary Hugging Face access. That load
is visible but defaults off, so the generated notebook runs top-to-bottom with only the Docker
stack. Raw registry inspection remains in the architecture notebook, and Fusion construction,
evaluation, provider calls, authentication UX, mocks, and private APIs remain out of scope.

**Phase 5E is implemented:** `examples/03_fusions.ipynb` teaches network-free Fusion construction.
String model IDs are the concise default; mappings with exactly `model`, `prompt`, and `params` are
used only for member-specific overrides. It demonstrates a shared default prompt, stable member
order, scalar parameters, duplicate model IDs with distinct configurations, deterministic
`MajorityVote`, and a model-backed `Model` reducer that adds one synthesis call.

The notebook inspects only the public `models`, `model_ids`, `reducer`, and `url4` values. It
explains that `tools` is benchmark-owned and reserved from ordinary model parameters, while route
availability and provider authentication are execution-time concerns. It performs no engine
configuration, discovery, benchmark loading, execution, YAML parsing, HTTP, or private compilation.

**Phase 5F is implemented:** `examples/04_custom_benchmarks.ipynb` builds a real local benchmark from
three ordinary `sf.Case` values, then selects `sf.graders.ExactChoice()` and
`sf.aggregators.Mean()`. It explains stable unique case IDs, exact model inputs, researcher-visible
but model-sealed references, optional metadata, versioned benchmark IDs, and the public benchmark
definition fields without adding case iteration or another dataset API.

The primary example uses an in-memory case list. A markdown-only loader pattern makes source access
and cleaning explicitly researcher-owned: ScreamingFace begins at validated `sf.Case` values rather
than becoming an ETL DSL. Benchmark `tools` are explained as requirements applied consistently to
answer-producing members. One optional three-member evaluation defaults off, states its nine model
calls, and creates no substitute report; enabling it requires Docker and working provider access,
but never Hugging Face because the cases are local.

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
| Discover/load benchmark | List installed definitions; fetch/validate source locally | No responsibility |
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

### Discovery and benchmark-source tests

- model and benchmark discovery filtering by query, tools, and limit;
- benchmark listing/loading never contacts the engine;
- model ID/route identity;
- benchmark version IDs remain opaque strings;
- malformed canonical source rows fail before model calls; and
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
- positive/negative criterion scoring, section metrics, pass rate, and configured-pass averaging,
  including the three-pass `draco@1` publication;
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
  engine model registry and installed benchmark catalog/loaders
  benchmark/case values and canonical source normalization
  fusion compiler and execution
  reducers, graders, aggregators
  run, grades, report values

packages/screamingface/tests/
  unit and HTTP contract tests

packages/screamingface/apps/screamingface-engine/  # temporary package-development location
  persistent Url4Node app, model/Gateway adapter, executable registry/routes, Docker wiring

apps/screamingface-engine/                 # proposed final owner/location after approval

packages/screamingface/examples/
  quickstarts, architecture, GPQA, DRACO
```

The actual module split should follow repository conventions found during implementation. Public
names and behavioral boundaries are fixed by the spec; private filenames are not.

## 7. Immediate next step

Review full DRACO notebook and deployment readiness against the implemented SDK/engine path. The
engine can execute compatible `web_search` members and now exposes the required judge route;
provider-backed success still depends on the external AI Gateway model registration,
authentication, and the selected reproduction's complete panel-model lineup. Keep the dataset
SDK-local and do not add a substitute judge, runtime fallback, or direct Gateway client.
