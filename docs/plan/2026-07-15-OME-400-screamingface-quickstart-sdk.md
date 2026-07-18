# OME-400 — URL4-native ScreamingFace SDK implementation plan

**Spec:** `docs/spec/2026-07-15-OME-400-screamingface-quickstart-sdk-spec.md`

## Scope decision

Build the SDK exclusively against URL4. ScreamingFace compiles complete expressions and submits
them to an engine port; it never calls AI Gateway or model providers. The default engine is a real
in-process `Url4Node` with deterministic model-route handlers. An explicitly configured HTTP
engine is strict and never falls back.

Authentication, hosted-engine discovery, and engine-owned scalable model discovery remain owner
consultation gates. Do not restore the superseded `sf.setup()`/direct-gateway design.

## Phase 1 — Minimal repeatable GPQA path — complete

1. Add package skeleton, public exports, catalog, Fusion, reducer, result, session, engine client,
   and benchmark seams.
2. Compile canonical unresolved recipes and concrete per-question expressions with URL4 builders.
3. Execute through `EnginePort`, validate labeled panel results, reduce, and calculate
   score/baseline/gain from the same answers.
4. Provide a bundled 20-case GPQA-shaped fixture and optional gated live GPQA loading.
5. Ship a generated bare quickstart with no model discovery or authentication dependency.

**Complete when:** zero configuration returns a repeatable 100/80/+20 mechanics demonstration and
an explicit unavailable HTTP engine raises a typed error without fallback.

## Phase 2 — Reducer and model-call generalization — complete

1. Accept plain model IDs and strict per-model dictionaries with optional name, prompt, and URL4
   parameters.
2. Normalize panel and reducer calls through one internal model-call representation.
3. Introduce `Reducer`, local `MajorityVote`, and engine-executed `ModelReducer`.
4. Preserve repeated calls to one model with stable private call-slot identities.
5. Add strict YAML parity with portable reducer mappings.

**Complete when:** Python and YAML compile identically; model-backed synthesis is part of the URL4
graph; local voting remains deterministic and creates no extra model request.

## Phase 3 — Benchmark and grader contracts — complete

1. Normalize benchmark cases behind internal definitions rather than embedding data cleaning in
   the public Fusion API.
2. Keep experiment prompts/reducers in researcher code and benchmark grading in the adapter.
3. Add DRACO-shaped fixture/live loading, rubric parsing, weighted scoring, and repeated URL4 judge
   calls.
4. Require `tools=["web_search"]` explicitly for DRACO panel members.
5. Pin judge system/user semantics and request parameters.

**Complete when:** the SDK can express the full DRACO panel → model reducer → independent rubric
judge flow without hard-coding experiment prompts into the SDK.

## Phase 4 — Zero-setup real-node mock — complete

1. Centralize deterministic responses in route handlers shared by in-process and optional HTTP
   execution.
2. Make an in-process `Url4Node` the default engine and mock only model-route leaves.
3. Keep engine selection independent from fixture/live dataset selection.
4. Record both provenance axes in `Run` and its notebook representation.
5. Keep `./scripts/dev-url4.sh` as an optional HTTP transport proof.
6. Run all notebooks in CI without a server.

**Complete when:** GPQA, YAML, custom prompts, model reduction, and DRACO all traverse real URL4
execution with deterministic leaf responses and no service setup.

## Phase 5 — Documentation and learning paths — in progress

1. Keep `00_quickstart.ipynb` below 12 cells and defer graph/wire details.
2. Teach recipe/request/node/response internals in `screamingface-engine.ipynb`.
3. Teach benchmark-owned judge requests and production route requirements in `draco.ipynb`.
4. Add a brand-aligned package-local HTML page covering every public export, runtime topology,
   configuration matrix, wire envelopes, benchmarks, and production boundary.
5. Add append-only docs contract tests for API inventory, links, design constraints, notebook
   learning levels, and execution-boundary language.
6. Reconcile README, spec, task mirror, work ledger, and hidden local notes.

**Complete when:** a new user can choose the correct learning path, cannot confuse deterministic
routes with provider inference, and can inspect representative requests/responses without reading
source code.

## Phase 6 — Engine integration — owner dependent

ScreamingFace side:

1. retain the strict HTTP adapter and current request/response contract;
2. add integration fixtures only when the engine contract changes; and
3. never add a direct AI Gateway fallback.

URL4 engine side:

1. register production `/provider/model` routes;
2. translate parameters and `tools=web_search` into backend semantics;
3. preserve intent/context mapping;
4. call AI Gateway internally when chosen by the engine owner; and
5. later return usage, cost, failure, retry, tool, citation, and trace telemetry.

Authentication, discovery, and hosted deployment require explicit owner agreement before SDK UX
is implemented.

## Phase 7 — Share/import and future orchestration — deferred

1. OME-408: parse a teammate's URL4, preview it offline, copy it, and rebuild an editable Fusion.
2. Design multi-round orchestration separately from reduction.
3. Preserve URL4 portability and label arbitrary local Python as non-portable.
4. Support suites, multi-source experiments, caching, statistics, and publication as separate
   layers over benchmark/Fusion contracts.

## Quality and handoff

1. Run `uv run .claude/scripts/run_gates.py screamingface` from the repository root.
2. Execute and deterministically regenerate all three notebooks.
3. Validate the static HTML API inventory and every local link.
4. Verify the optional HTTP mock engine end to end.
5. Perform security, ownership-boundary, provenance, simplicity, visual, and confidence reviews.
6. Update the active work ledger with actual files, counts, coverage, deviations, and commit.
7. Preserve all pre-existing `packages/url4` changes and stage ScreamingFace/docs paths explicitly.

## Approval record

The owner explicitly approved implementing the zero-setup deterministic-leaf engine and, on
2026-07-17, requested the notebook/API/documentation reconciliation in this phase.
