---
id: OME-400
linear_url: https://linear.app/openmined/issue/OME-400
status: in_progress
type: task
priority: unknown
labels: [Python SDK, agentic, autonomous, Feature]
created: unknown
closed:
---

Ship the importable ScreamingFace Python SDK and its executable quickstart as a URL4-native
compose → run → compare path.

Superseded implementation state (not a compatibility target):

- optional `sf.config(engine=..., mode=...)`, with independent engine/data selection;
- `sf.models`, strict model dictionaries, and `sf.Fusion`/`Fusion.from_yaml`;
- `sf.MajorityVote`, `sf.ModelReducer`, canonical `.url4`, and concrete `request_for(...)`;
- `fusion.evaluate("gpqa" | "draco", first=...)`; and
- immutable `Run`/`ModelResult`/`RunFailure` execution identity and comparison results.

The existing in-process `Url4Node`, deterministic model responses, and mock/live mode have been
removed from the Phase 1 SDK. The target SDK always calls the effective HTTP URL4 engine; local
development uses the temporary Dockerized
`packages/screamingface/apps/screamingface-engine` profile, and only that engine will reach AI Gateway
once model execution is implemented.

Documentation deliverables are:

- a deliberately small `00_quickstart.ipynb`;
- a detailed `screamingface-engine.ipynb` request/node/response walkthrough;
- a DRACO panel/reducer/judge walkthrough;
- a brand-aligned static HTML reference covering every exported API; and
- reconciled README/spec/plan/task/work records that remove the superseded direct-gateway design.

Owner metadata sync remains required: confirm Linear priority/created date and add/register the
`pkg/screamingface-sdk` landing label in Linear and `.claude/task-board.local.md`.

## Greenfield benchmark architecture — 2026-07-18

The owner confirmed that the SDK and notebooks have no external users and authorized replacing
the current public evaluation surface without compatibility wrappers. The approved direction is
recorded in:

- `docs/plan/2026-07-18-OME-400-screamingface-benchmark-architecture.md`; and
- `docs/spec/2026-07-18-OME-400-benchmark-public-contract.md`.

Phase 0 locks universal cases, plain-Python benchmark recipes, and immutable in-memory
`Run` → `Grades` → `Report` artifacts before production implementation. Persistence and budget
enforcement are later additive contracts once their engine and storage requirements exist.

## Phase 1 implementation — 2026-07-18

Implemented the network-free public value layer and strict discovery/loading boundary:

- `sf.config`, immutable `Case`, `Benchmark`, and `Fusion` authoring;
- namespaced reducers, graders, and aggregators;
- engine-backed `models.list`, SDK-local `benchmarks.list`, and eager canonical
  `benchmarks.load`;
- typed registry, transport, and benchmark-source failures; and
- a real Dockerized `Url4Node` profile in the temporary package-development app location.

Phase 1 intentionally does not implement model execution, Fusion evaluation, grading,
aggregation, or authentication. A development-only Phase 1 engine-profile walkthrough documents
the implemented boundary; public quickstart and DRACO notebook regeneration remain in their
reviewed later phase.

## Phase 2A implementation — 2026-07-18

Implemented the persistent engine-to-Gateway model execution boundary:

- one long-running `Url4Node` with three startup-registered model routes;
- one reusable asynchronous AI Gateway client and typed request translation;
- plaintext assistant response extraction and URL4-native failure mapping;
- unprefixed benchmark and reducer resource identities;
- application-owned lifecycle, global admission, timeout, and graceful cleanup; and
- an honest tool-free model registry while `web_search` and the DRACO judge route are unavailable.

Phase 2A does not add the deterministic reducer, SDK Fusion execution, grading, aggregation,
authentication, automatic retries, or mock fallbacks.

## Phase 2B implementation — 2026-07-19

Implemented deterministic Fusion reduction through the persistent engine:

- one private SDK-owned exact-string majority selector with stable member-order tie breaking;
- one startup-registered `/reducers/majority-vote` URL4 endpoint;
- strict resolved-context validation and permanent URL4 `malformed_source` failures;
- literal and model-backed complete-expression coverage, including proof that the reducer makes no
  additional AI Gateway request; and
- a reproducible no-mock Docker smoke for reducer execution and engine-to-Gateway topology.

Phase 2B does not add SDK URL4 compilation, `Run`, grading, aggregation, tools, authentication,
automatic retries, or runtime mocks. Those boundaries remain in their reviewed later phases.

## Phase 2C contract approval — 2026-07-19

Approved the greenfield compiler and run-stage contract before runtime implementation:

- `fusion.url4` is a canonical parameterized recipe built and rendered through URL4's public SDK
  facade;
- member questions are context, member prompts are intent, and model reducers automatically
  receive a stable labeled question/panel context;
- `fusion.run(str | Benchmark, first=...)` returns typed immutable `Run`, `CaseResult`,
  `MemberResult`, and `RunFailure` values;
- strict plaintext result validation never repairs partial or malformed engine output;
- four cases may run concurrently while results retain canonical order;
- Phase 2C performs no retries or execution-time cancellation of unrelated cases; and
- grading, `evaluate()`, persistence, budgets, authentication, tools, and public execution-policy
  controls remain deferred.

## Phase 2C implementation — 2026-07-19

Implemented the approved SDK run boundary:

- canonical parameterized `fusion.url4` recipes and concrete per-case expressions built through
  URL4's public AST/builder facade and renderer;
- stable member slots, automatic model-reducer context, and exact majority-vote routing;
- registry, model, reducer, tool, case, reference, and response-schema preflight;
- one `GET /v1?q=...` request per selected case with four-way bounded concurrency, stable result
  order, and no retries;
- strict plaintext `screamingface.fusion-result.v1` decoding with atomic typed failures; and
- immutable `Run`, `CaseResult`, `MemberResult`, and `RunFailure` records plus `run.to_dict()`.

The no-runtime-mock Docker smoke now exercises public `Fusion.run()` through the persistent URL4
node and AI Gateway topology. Grading, aggregation, `evaluate()`, tools, authentication,
persistence, and public execution-policy controls remain deferred.

## Phase 3A grading and aggregation contract approval — 2026-07-19

Approved the grading, aggregation, and facade contract without changing runtime code:

- `run.grade()` grades the captured Fusion answer and every member, returning nested immutable
  `Grades`, `CaseGrades`, `Grade`, `CriterionVerdict`, and `GradeFailure` values;
- `ExactChoice` is deterministic local A–J/index/full-text grading, while malformed references
  fail preflight and unparseable non-blank model answers remain valid zero scores;
- `Rubric` validates all references before spend, sends one ordinary URL4 judge-model request per
  target/criterion/pass, and requires complete verdict coverage for a valid score;
- judge transport failures are not retried; invalid structured judge output alone receives up to
  two byte-identical retries, and successful evidence is retained after partial failure;
- `Mean` uses one strict common paired case set for Fusion, baseline, gain, member scores, and
  metrics; and
- `Fusion.evaluate(benchmark, first=...)` is exactly `run -> grade -> aggregate`, while
  `benchmarks.load()` remains an eager SDK-local canonical source load rather than an alternate
  execution mode.

Implementation is intentionally deferred to separately reviewed Phase 3B–3D slices. Phase 3B is
limited to public grading values/failures and deterministic `ExactChoice` behavior.

## Phase 3B implementation — 2026-07-19

Implemented the reviewed grading-value and ExactChoice foundation:

- immutable exported `Grades`, `CaseGrades`, `Grade`, `CriterionVerdict`, and `GradeFailure`
  values with strict state validation and JSON-compatible snapshots;
- nested Fusion/member grades, stable failure flattening, completeness, and preservation of the
  originating immutable `Run` for later aggregation;
- the proven A–J, explicit-marker, decorated-choice, numeric-string, and normalized-full-text
  ExactChoice parser with article/pronoun/medical-abbreviation guards;
- shared exact-reference validation in run preflight, requiring publisher-normalized non-empty
  strings and rejecting literal integers rather than guessing index conventions; and
- focused value/parser tests plus full SDK lint, format, type, and coverage verification.

As approved, Phase 3B does not add `Run.grade()`, Rubric judge traffic, aggregation,
`Fusion.evaluate()`, or any engine-profile change. Phase 3C will add public grading dispatch only
after both supported grader strategies work.

## Phase 3C contract approval — 2026-07-19

Approved the complete grading-execution slice without changing runtime code:

- `Run.grade()` has no policy arguments, dispatches ExactChoice locally, and grades Rubric answers
  through the configured URL4 engine without rerunning captured panel or reducer work;
- Rubric preflight validates every selected reference together, including stable section metrics,
  globally unique criteria, non-zero weights, and a positive criterion in every section;
- every Fusion/member target, rubric criterion, and pass produces one ordinary URL4 judge-model
  request whose context is the official judge user text and whose intent is the pinned system
  prompt;
- passes and invalid-output retries are byte-identical, transport failures are never retried, and
  unresolved verdicts preserve evidence while preventing partial score publication;
- judge work is bounded at 16 concurrent requests to match the current engine admission limit,
  with results and failures restored to stable semantic order; and
- the SDK validates generic URL4 parameters while the engine owns model-specific compatibility
  and rejects invalid parameters before AI Gateway spend.

Phase 3C excludes aggregation, reports, `Fusion.evaluate()`, engine-profile changes,
authentication, persistence, and notebook regeneration. Canonical DRACO remains blocked on the
engine profile advertising `gemini/3.1-pro-preview` and working `web_search` support.

## Phase 3C implementation — 2026-07-19

Implemented the approved complete grading execution slice:

- added public synchronous `Run.grade()` dispatch without policy parameters or captured-model
  reruns;
- added complete ExactChoice grading for Fusion/member answers and preservation of failed Run
  cases;
- added strict all-reference Rubric preflight, deterministic section metric keys, and advertised
  judge-model preflight;
- compiled literal URL4 judge expressions through the URL4 SDK, with the official criterion type,
  requirement, query, response, and pinned intent mapping;
- added 16-way bounded judge traffic, byte-identical invalid-output retries, no transport retries,
  safe typed failures, stable evidence ordering, and strict plaintext judge-schema parsing;
- added DRACO weighted overall/section scoring, pass rate, complete-coverage enforcement, and
  retained successful/failed verdict evidence; and
- extracted shared engine HTTP error/JSON decoding so run and grade use one boundary contract.

Verification passes with 270 repository tests at 97.6% ScreamingFace coverage, 49 engine-profile
tests at 98.1% coverage, lint, formatting, typing, fixture regeneration, notebook regeneration,
and package builds.

## Phase 3D implementation — 2026-07-19

Implemented the approved paired aggregation and report slice:

- preserved the Fusion name and ordered `member_n -> model ID` identities through `Run`,
  `Grades`, and `Report`, including runs where every case fails;
- added strict validation that every successful case uses the expected member slots and models;
- added deterministic local `sf.aggregators.Mean()` aggregation over the common case set where
  the Fusion and every member have valid grades;
- added immutable `sf.Report` and `sf.MemberReport` values with score, baseline, gain, coverage,
  consistently available metrics, failures, and JSON-compatible serialization; and
- added `Fusion.evaluate()` as the exact `run -> grade -> aggregate` convenience facade.

Phase 3D makes no new engine, URL4, AI Gateway, authentication, persistence, cost, or confidence
interval behavior. Phase 4 contract review is next.

## Pre-Phase 4 greenfield cleanup — 2026-07-19

Removed the obsolete pre-contract notebooks, generators, YAML/HTML surfaces, mock server, local
in-process runtime configuration, dead dependencies, and superseded normative documents. Updated
the live README and CI instructions to describe only the Dockerized HTTP engine boundary.

The runtime now requires an origin-only engine configuration, uses strict duplicate-key JSON at
every engine boundary, and captures each Run's exact selected cases so grading cannot reload
changed references. The engine registry now advertises only executable models and reducers;
benchmark definitions and data are SDK-local. DRACO entered the SDK catalog in Phase 4B after
its canonical definition passed, while execution still requires its real judge route and
`web_search` adapter. Historical task/work ledgers remain explicitly labelled audit evidence, and the
untracked `packages/screamingface/examples/draco-eval-demo/` reference remains untouched.

## Phase 4 contract approval — 2026-07-19

Approved the canonical GPQA/DRACO publication contract without changing runtime behavior:

- GPQA pins the Hugging Face revision, source Record IDs, source order, 198-row invariant,
  SHA-256 option permutations, exact MCQ formatting, and source domain metadata;
- DRACO pins the dataset revision and raw digest, preserves its 100-case source order, and
  validates its full 3,934-criterion rubric corpus before publication;
- `draco@1` follows the executable benchmark pipeline with three passes, the byte-pinned Appendix
  C.5 prompt, Gemini 3.1 public route, and temperature/reasoning/token parameters;
- incomplete verdict coverage remains invalid under the SDK's stricter no-missing-work contract;
- `web_search` is injected only onto answer-producing members and represents engine-owned search
  plus source fetching, with benchmark-source leakage blocked; and
- DRACO enters SDK-local discovery once its canonical definition is valid; evaluation remains
  blocked until its judge, named tool, at least one complete Fusion, and real SDK -> engine ->
  Gateway -> provider path pass acceptance tests.

The reviewed implementation is split into canonical GPQA, canonical DRACO, tools, and judge
slices. Each still requires owner approval before runtime changes.
See `docs/work/2026-07-19-OME-400-phase-4-contract.md` for the complete decision and gap record.

## Phase 4A implementation — 2026-07-19

Implemented the approved canonical SDK-local GPQA slice:

- moved GPQA source handling into an SDK-local benchmark module and removed benchmarks from the
  engine registry and HTTP surface;
- pinned the exact Hugging Face revision and lazily cached one fully validated 198-case tuple per
  researcher process;
- replaced generated row IDs and Python `random` with source Record IDs and SHA-256-stable A-D
  ordering;
- mapped source `High-level domain` and `Subdomain` into normalized metadata and preserved source
  row order and text;
- rejected missing/malformed fields, duplicate IDs, and correct-answer/distractor collisions
  before publishing any cases; and
- verified the real pinned dataset end to end. Its one duplicate-distractor pair is canonical and
  is preserved without compromising the tagged correct-answer reference.

The engine no longer needs the researcher's Hugging Face token or serves answer-bearing case
routes. Phase 4B subsequently added DRACO locally; engine execution remains blocked.

## Phase 4B implementation — 2026-07-19

Implemented the approved canonical SDK-local DRACO definition:

- pinned `perplexity-ai/draco` test split at revision
  `ce076749809027649ebd331bcb70f42bf720d387` and cached one successful normalized tuple per
  researcher process;
- validates all 100 source-order UUID rows, the exact ten-domain set, 400 four-per-case sections,
  and 3,934 criteria before returning the Benchmark;
- parses rubric JSON with recursive duplicate-key rejection and validates exact root, section, and
  criterion fields, local identities, nonblank text, and finite nonzero signed weights;
- maps `problem` to `Case.input`, the complete parsed rubric to the sealed reference, and `domain`
  to metadata without exposing any source through the engine;
- embeds and byte-pins the official 5,196-byte Appendix C.5 per-criterion prompt;
- configures the pipeline-aligned Gemini 3.1 judge, three passes, and approved parameters;
- exposes `draco@1` from the SDK catalog with `tools=("web_search",)`; and
- proves the current engine fails capability preflight without sending an evaluation request.

Phase 4B makes no engine, compiler, tool-injection, concurrency, notebook, URL4, or AI Gateway
change. Phase 4C member-only tool compilation review is next.

## Phase 4C implementation — 2026-07-19

Implemented the approved SDK-only benchmark capability overlay:

- validates ordered, unique lowercase tool IDs and applies the same contract to engine registry
  capability declarations and discovery filters;
- reserves `tools` from generic member, model-reducer, and rubric-grader parameters;
- compiles benchmark tools only onto concrete answer-producing member calls;
- preserves the benchmark-independent `fusion.url4` and `run.fusion_url4` recipes;
- leaves deterministic reducers, model synthesizers, and rubric judges tool-free; and
- proves single/multiple capability rendering and decoded `Url4Node` request parameters without
  introducing an in-process runtime fallback.

Phase 4C changes no engine, AI Gateway, URL4 package, authentication, concurrency, or notebook
behavior. The current engine still advertises no tools and rejects `tools`; the named
`web_search` adapter and Gemini 3.1 judge route require separate engine-phase review.

## Phase 4D implementation — 2026-07-19

Implemented the approved engine-owned web-research capability without changing the public SDK,
URL4, or AI Gateway:

- added a bounded standard model/tool loop to the temporary `screamingface-engine` profile;
- translated public `tools=web_search` into internal `web_search` and `web_fetch` functions while
  preserving every model turn through AI Gateway's existing chat-completions endpoint;
- added a pinned keyless SearXNG service on the private Compose network;
- limited and normalized search results, bounded public HTML/plaintext reads, rejected private
  targets and unsafe redirects, and filtered known DRACO-contaminating source prefixes;
- made Gemini and Claude advertise `web_search` only when the adapter is configured while Codex
  remains tool-free; and
- retained plaintext URL4 model responses and unchanged tool-free request behavior.

Phase 4D makes compatible DRACO research members executable. At that phase boundary, full DRACO
evaluation remained out of scope pending the separately reviewed `gemini/3.1-pro-preview` judge
route and long judge-expression transport. Authentication, budgets, persistence, telemetry,
notebook regeneration, and AI Gateway changes remained deferred.

## Phase 4E0 implementation — 2026-07-19

Implemented the safe transactional-GET boundary without changing URL4 or AI Gateway:

- changed standalone model/judge expressions to carry arbitrary context in a quoted native URL4
  binding, preserving model plaintext as the sole evaluation result;
- made `limits.max_request_target_bytes` a required strict engine-registry field;
- added exact encoded `/v1?q=...` preflight for all selected Fusion cases and all rubric judge
  tasks before either HTTP client—and therefore before model or judge spend;
- exposed `sf.EngineRequestTooLargeError` with actual and allowed byte sizes;
- set the development profile to advertise and enforce 61440 bytes with HTTP 414 and
  `request_target_too_large`; and
- configured 131072 bytes of Uvicorn/h11 parser headroom.

The 60 KiB application boundary leaves 4 KiB for the configured origin under `httpx`'s 64 KiB
absolute-URL ceiling. The real-socket verification caught this client constraint before release;
engine configuration may lower the boundary but cannot raise it.

The URL4 transaction remains GET-only. There is no truncation, POST fallback, hidden compression,
partial grading, or paid retry. The next reviewed capability slice is the missing
`gemini/3.1-pro-preview` judge route.

## Phase 4E1 implementation — 2026-07-19

Implemented the reviewed DRACO judge route entirely inside the temporary
`screamingface-engine` profile:

- added `/gemini/3.1-pro-preview` as an ordinary tool-free model route mapped to the assumed AI
  Gateway registration `gemini-cli/gemini-3.1-pro-preview`;
- reused the generic model executor and Gateway client for system/user message mapping,
  `temperature`, `max_tokens`, and `reasoning_effort`;
- preserved assistant judge JSON as plaintext URL4 output;
- proved repeated passes produce independent Gateway requests with no cache or automatic retry;
  and
- proved Gateway rejection, connection failure, timeout, and malformed success responses remain
  safe `502 resolution_failed` URL4 errors.

No URL4 or AI Gateway file changed. Provider-backed success depends on the AI Gateway owner
registering the assumed model ID and on ordinary provider authentication.

## Phase 5A contract approval — 2026-07-19

Approved the first public DRACO tutorial as an SDK walkthrough rather than a full reproduction:

- use the canonical SDK-local `draco@1` definition and real configured HTTP URL4 engine;
- compose the currently compatible Gemini 2.5 and Claude Sonnet 4.6 research panel with a Codex
  model reducer;
- teach explicit `run -> grade -> aggregate` stages and show `evaluate()` only as their shorthand;
- keep all paid work behind a default-off `RUN_LIVE` switch without fabricating a result;
- explain the roughly 354 average judge calls for one case of this two-member Fusion; and
- reserve a reproduction claim for the complete benchmark pipeline's seven standalone models and
  nine named fusions.

The generated artifact must contain no direct Gateway path, runtime fallback, private compiler
import, or hidden second evaluation.

## Phase 5A implementation — 2026-07-19

Implemented the approved generated DRACO SDK walkthrough:

- added `examples/05_draco.ipynb` and its deterministic builder;
- documented the local Docker, Hugging Face, AI Gateway registration, and provider prerequisites;
- showed the public parameterized URL4 recipe and HTTP engine boundary without importing the
  private concrete compiler;
- separated `run`, `grade`, and `aggregate`, with `evaluate()` shown only as non-executed shorthand;
- defaulted all model and judge work off and displayed the average one-case call scale before the
  live cell; and
- added append-only contract tests plus CI notebook regeneration enforcement.

The artifact is output-free and makes no full-reproduction claim. No SDK runtime, engine, URL4,
AI Gateway, authentication, persistence, or budget behavior changed.

## Phase 5B contract approval — 2026-07-19

Approved the public quickstart as one concise configure → compose → evaluate → compare path:

- use the current three executable model routes with `sf.reducers.MajorityVote()`;
- evaluate five canonical `gpqa@1` cases through one `fusion.evaluate(...)` call;
- teach only `score`, `baseline`, and `gain` after evaluation;
- document the Docker, Hugging Face, provider-access, and 15-model-call prerequisites;
- keep the live call disabled initially without constructing a substitute report; and
- omit discovery, raw URL4, response schemas, manual stages, custom benchmarks, and private APIs.

The notebook is a generated, output-free artifact and introduces no SDK runtime or engine change.

## Phase 5B implementation — 2026-07-19

Implemented the approved generated bare-bones quickstart:

- added `examples/00_quickstart.ipynb` and its deterministic builder;
- reduced the product path to engine configuration, one three-member majority-vote Fusion, one
  five-case GPQA evaluation, and one `score`/`baseline`/`gain` comparison;
- kept the 15 model calls behind a default-off live switch without a substitute report;
- documented only the Docker, Hugging Face, and provider-access prerequisites needed to run it;
- excluded discovery, raw URL4, response schemas, manual stages, and private APIs; and
- added append-only notebook contract tests and CI regeneration enforcement.

No SDK runtime, engine, URL4, AI Gateway, authentication, persistence, or budget behavior changed.

## Phase 5C contract approval — 2026-07-19

Approved replacing the Phase 1 development walkthrough with a focused public architecture guide:

- configure one ScreamingFace engine and show the localhost/hosted-deployment boundary;
- inspect raw registry plaintext and the validated `sf.models.list()` view;
- distinguish parameterized `fusion.url4` identity from a concrete encoded transaction;
- build one canonical URL4 expression through public URL4 builders and execute it through
  `GET /v1?q=...` against the deterministic majority-vote route;
- explain SDK-local benchmark/reference/grading/aggregation ownership and engine-owned
  model/Gateway/tool execution; and
- require only the Docker stack, with no benchmark source or provider credentials.

The explicitly superseded Phase 1 notebook/generator and CI step are removed in the same unit.
No compatibility copy is retained because the SDK has no external users.

## Phase 5C implementation — 2026-07-19

Implemented the approved generated configuration and architecture guide:

- replaced `phase_1_engine_profile.ipynb` and its builder with `01_architecture.ipynb` and
  `build_architecture.py`;
- documented the SDK, persistent URL4 engine, AI Gateway, provider, and SearXNG ownership
  boundaries;
- exposed raw registry plaintext beside validated `sf.models.list()` discovery;
- distinguished parameterized `fusion.url4` identity from a concrete encoded request;
- built the deterministic reducer expression solely through public URL4 builders and executed it
  through the real engine with no model/provider call; and
- replaced README and CI references and added append-only notebook contract tests.

A temporary notebook copy ran top-to-bottom against the tracked Docker stack on isolated ports and
returned the exact expected plaintext result. The isolated stack was removed afterwards without
touching the owner's older containers. No SDK runtime, engine, URL4, or AI Gateway behavior changed.

## Phase 5D contract approval — 2026-07-19

Approved one generated discovery notebook with deliberately separate model and benchmark sources:

- configure the ScreamingFace engine and list only its executable model IDs;
- demonstrate the existing `query`, `tools`, and `limit` filters;
- list only the canonical benchmark IDs installed in the SDK, without consulting the engine;
- explain that benchmark loading materializes a typed definition and can fetch the source through
  the researcher's ordinary Hugging Face access;
- keep the GPQA load visible but disabled by default so Docker is the only runtime prerequisite;
  and
- exclude raw registry parsing, Fusion execution, provider calls, authentication UX, mocks, and
  private APIs.

The phase adds no runtime contract or summary/metadata API.

## Phase 5D implementation — 2026-07-19

Implemented the approved generated discovery guide:

- added `examples/02_discovery.ipynb` and its deterministic builder;
- showed engine-backed executable model IDs and SDK-local canonical benchmark IDs separately;
- demonstrated `query`, `tools`, and `limit` against both list APIs without adding metadata;
- documented that provider availability is not established by model discovery;
- kept the real GPQA materialization call visible but disabled, with the researcher-owned Hugging
  Face access boundary explained; and
- added append-only contract tests, README navigation, and CI regeneration enforcement.

The notebook ran top-to-bottom against the tracked Docker stack on isolated ports and returned the
expected model and benchmark filter results without calling a provider or dataset. The isolated
stack was removed afterwards without touching the owner's existing spike containers. No SDK
runtime, engine, URL4, AI Gateway, authentication, or dataset behavior changed.

## Phase 5E contract approval — 2026-07-19

Approved one generated, network-free Fusion construction notebook:

- use string model IDs as the concise form and mappings only for per-member overrides;
- teach the shared Fusion prompt and explicit member `prompt` and scalar `params`;
- demonstrate repeated model IDs with distinct configurations and stable order;
- compare deterministic `sf.reducers.MajorityVote()` with model-backed
  `sf.reducers.Model(...)` and its one extra synthesis call;
- inspect only `fusion.models`, `fusion.model_ids`, `fusion.reducer`, and `fusion.url4`; and
- explain that `tools` belongs to benchmarks and compatibility/authentication belong to execution.

The notebook requires no Docker or credentials and excludes discovery, benchmark loading,
execution, YAML, HTTP, mocks, authentication UX, and private APIs. The phase adds no runtime API.

## Phase 5E implementation — 2026-07-19

Implemented the approved generated Fusion construction guide:

- added `examples/03_fusions.ipynb` and its deterministic builder;
- taught string members as the default and mappings only for per-member prompt/parameter
  overrides;
- demonstrated stable ordering and repeated model IDs through two differently configured Claude
  members;
- compared deterministic majority voting with one model-backed synthesis call;
- exposed only `models`, `model_ids`, `reducer`, and `url4` for definition inspection; and
- added append-only contract tests, README navigation, and CI regeneration enforcement.

The notebook ran top-to-bottom in a fresh kernel without an engine, credentials, or network access;
all three Fusions and their URL4 recipes compiled successfully. No SDK runtime, engine, URL4, AI
Gateway, authentication, or dataset behavior changed.
