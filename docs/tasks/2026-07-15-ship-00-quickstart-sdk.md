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

Implemented the network-free public value layer and strict remote discovery/loading boundary:

- `sf.config`, immutable `Case`, `Benchmark`, and `Fusion` authoring;
- namespaced reducers, graders, and aggregators;
- strict `models.list`, `benchmarks.list`, and eager `benchmarks.load`;
- typed registry, transport, manifest, and case-stream failures; and
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

- one private SDK-owned exact-string majority selector with stable panel-order tie breaking;
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
