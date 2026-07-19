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
benchmark definitions and data are SDK-local. DRACO remains absent from the SDK catalog until
Phase 4 supplies its canonical definition, while execution also requires its real judge route and
`web_search` adapter. Historical task/work ledgers remain explicitly labelled audit evidence, and the
untracked `packages/screamingface/examples/draco-eval-demo/` reference remains untouched.

## Phase 4 contract approval — 2026-07-19

Approved the canonical GPQA/DRACO publication contract without changing runtime behavior:

- GPQA pins the Hugging Face revision, source Record IDs, source order, 198-row invariant,
  SHA-256 option permutations, exact MCQ formatting, and source domain metadata;
- DRACO pins the dataset revision and raw digest, preserves its 100-case source order, and
  validates its full 3,934-criterion rubric corpus before publication;
- `draco@1` follows the executable benchmark pipeline with three passes, the exact Appendix F.5
  prompt, Gemini 3.1 public route, temperature/reasoning/token parameters, and 32-way judge work;
- incomplete verdict coverage remains invalid under the SDK's stricter no-missing-work contract;
- `web_search` is injected only onto answer-producing members and represents engine-owned search
  plus source fetching, with benchmark-source leakage blocked; and
- DRACO remains absent from discovery until its judge, named tool, at least one complete Fusion,
  and real SDK -> engine -> Gateway -> provider path all pass acceptance tests.

The reviewed implementation is split into canonical GPQA, hidden canonical DRACO, tools, judge,
and conditional-advertisement slices. Each still requires owner approval before runtime changes.
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
routes. DRACO remains hidden. Phase 4B contract review is next after the revised gates pass.
