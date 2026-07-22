# OME-400 — Split the ScreamingFace SDK from the engine reference

**Status:** Phases 1–2 implemented; handoff pending
**Created:** 2026-07-22
**Checkpoint:** `OME-400-ship-quickstart-sdk` at `71e2404`

This plan separates the releasable researcher SDK from the temporary engine implementation without
discarding the working end-to-end reference. The current checkpoint remains unchanged as the full
historical spike. No compatibility layer is required because the SDK is unreleased.

## Target branch topology

```text
main
  └─ OME-400-screamingface-sdk
       └─ OME-400-screamingface-engine-reference
```

The engine-reference branch is stacked on the SDK branch initially so its integration tests can
exercise the exact public SDK contract. After the SDK lands, the engine branch can be rebased or
retargeted to `main`. The existing checkpoint branch is not renamed or rewritten.

## SDK branch

`OME-400-screamingface-sdk` owns researcher-facing construction, discovery, transport, validation,
display, and documentation.

Keep:

- `packages/screamingface/src/screamingface/` public values, compiler, registry client, HTTP/SSE
  transport, connection UX, report decoding, and widgets;
- all nine tracked generated notebooks and their deterministic builders;
- public contract fixtures and the fixture/notebook verification scripts;
- SDK tests that use controlled HTTP, registry, SSE, and plaintext contract fixtures; and
- the current public API, benchmark, connection, tools, and full-run URL4 specifications.

Remove from the SDK branch:

- `packages/screamingface/apps/screamingface-engine/`;
- `screamingface._benchmarks`, `screamingface._exact_choice`, and
  `screamingface._reduction`;
- the `datasets` runtime dependency, which exists only for engine-owned canonical data loading;
- engine lifecycle tests (`test_engine_dev_compose.py`, `test_phase7a_dev_script.py`);
- built-in dataset implementation tests (`test_builtin_gpqa.py`, `test_builtin_draco.py`,
  `test_builtin_draco_lite.py`, `test_builtin_draco_preview.py`);
- engine execution-helper tests (`test_phase2b_reduction.py`, `test_phase3b_exact_choice.py`); and
- engine source/test paths from the SDK's Pytest, Pyright, CI, and local SDLC configuration.

The SDK must build and pass its gates without an engine source checkout. It may require a running
engine only for explicitly live, opt-in acceptance tests; ordinary tests use the public wire
contract and never import `screamingface_engine`.

## Engine-reference branch

`OME-400-screamingface-engine-reference` preserves the working Url4Node application as an
implementation handoff, not as SDK-owned production infrastructure.

Keep:

- the current Docker/Compose development stack, OpenAPI documentation, connection bridge,
  AI Gateway adapter, Tavily adapter, model/tool executor, benchmark routes, graders, reducers,
  aggregation, progress events, and engine test suite;
- `create_node(...)` as the reusable route-registration factory and `create_app(...)` as the local
  ASGI composition/lifecycle wrapper; and
- integration tests that compile requests through the public ScreamingFace SDK and execute them
  through the reference node.

Move into the engine namespace:

- the pinned GPQA and DRACO source adapters;
- DRACO Lite and Preview projections;
- the pinned DRACO judge prompt;
- exact-choice execution; and
- deterministic majority selection.

Production engine code must contain no `screamingface._...` imports. It may consume stable public
SDK values where that makes the benchmark-authoring boundary clearer, but wire serialization and
route execution remain engine-owned. Shared schema strings such as
`screamingface.model-input.v1` are asserted through executable fixtures instead of importing SDK
private constants.

The reference app stays in its current temporary package-local path during the handoff. Ionesio,
as engine owner, decides whether it is promoted to `apps/screamingface-engine`, incorporated into
another service, or used only as a source reference. This split does not make that ownership
decision on his behalf.

## URL4 Cloud boundary

No `apps/url4-cloud` changes belong in either branch.

The cloud runner's `Executor` owns job lifecycle, streaming telemetry, cancellation, and terminal
result framing. A future URL4-backed executor can construct one configured node per runner process
and evaluate submitted URL4 expressions through it. ScreamingFace contributes its route factory;
the URL4/cloud owners contribute the executor and observation adapter. A new shared protocol
package is not justified for this split.

## Documentation policy

- All tracked notebooks remain SDK examples because they teach researcher-facing behavior, even
  when they expose the engine boundary for learning.
- The checkpoint branch retains the complete dated work history.
- Clean review branches carry only the current task, normative specifications, consolidated work
  record, and engine handoff needed to explain their changes.
- Generated notebooks must be output-free and byte-equivalent to their checked-in builders.

## Execution phases

### 1. Create the clean SDK branch

Start from `main`, restore only the approved SDK manifest, remove engine-owned modules and tests,
split the SDK configuration, refresh its lockfile, and run the complete SDK gate.

Acceptance:

- no engine app or `screamingface_engine` import is present;
- no canonical dataset loader or `datasets` dependency is present;
- SDK lint, format, Pyright, tests, coverage, fixtures, notebooks, and build pass; and
- no URL4 SDK or AI Gateway file changes are included.

### 2. Create the stacked engine-reference branch

Branch from the clean SDK branch, restore the reference app, relocate engine-owned implementation
modules and tests, remove private SDK imports, and give the app an independent test/typecheck/CI
lane.

Acceptance:

- engine production code has zero `screamingface._...` imports;
- the app's unit and public-SDK integration tests pass at the required coverage;
- `create_node(...)` is reusable independently of the local ASGI wrapper;
- Docker development remains reproducible; and
- no `apps/url4-cloud`, `packages/url4`, or AI Gateway changes are included.

### 3. Handoff

Share the engine-reference branch, engine handoff specification, and passing gate evidence with
Ionesio. Discuss final app placement and the URL4-cloud executor seam only after he has the concrete
reference. Sergey does not need an SDK-side change request before that boundary is reviewed.

## Stop conditions

- Do not create or rewrite branches until the working tree is clean and the user explicitly
  approves execution after reviewing this plan.
- Do not silently duplicate benchmark implementations across the SDK and engine.
- Do not weaken tests to make either half pass independently.
- Do not edit `packages/url4`, AI Gateway, or `apps/url4-cloud` as part of the split.

## Phase 1 outcome

The clean `OME-400-screamingface-sdk` branch was created from current `origin/main`. The temporary
engine app, canonical dataset adapters, exact-choice execution, and majority execution are absent.
The SDK has no `datasets` dependency, private engine imports, or engine paths in its Pytest,
Pyright, CI, or SDLC configuration. Notebook setup now requires a separately available compatible
engine instead of referring to a bundled development app.

The SDK-only gate passes: Ruff lint and format, Pyright, 287 tests at 95.15% coverage, executable
contract fixtures, deterministic generated notebooks, package build, and diff hygiene.

## Phase 2 outcome

The stacked `OME-400-screamingface-engine-reference` branch restores the temporary app as an
explicit implementation handoff. Canonical GPQA/DRACO adapters, the pinned judge prompt,
exact-choice scoring, and deterministic majority selection now live under the engine namespace.
Engine production source imports no `screamingface._...` module. The app has its own runtime
dependency lock, Ruff/Pyright/Pytest/coverage/build lane, and CI job; `create_node(...)` remains
separate from the ASGI/Compose lifecycle wrapper.

The reported DRACO Lite `mean rows must be JSON objects` failure was caused by a stale Docker image
whose URL4 sources differed from the checked-out sources. The current URL4 implementation passes
the complete candidate-route → iteration → candidate-mean ASGI integration test. Rebuilding with
`./dev.sh restart` produced an image whose relevant URL4 source hashes match the checkout; the
stack is healthy and advertises the expected DRACO Lite candidate route. A rebuilt container must
receive `HF_TOKEN` through a local `.env` before live canonical dataset evaluation.

The independent engine gate passes: Ruff lint and format, Pyright, 432 tests at 95.09% coverage,
and reference-app package build. The stacked SDK gate remains green with the Phase 1 results. No
`packages/url4`, AI Gateway, or `apps/url4-cloud` file is changed by this branch.
