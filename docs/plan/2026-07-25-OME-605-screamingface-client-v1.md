# OME-605 — Implement the ScreamingFace Python Client v1

**Status:** superseded by
[`2026-07-29-OME-605-direct-evaluation.md`](2026-07-29-OME-605-direct-evaluation.md)
**Created:** 2026-07-25
**Approved:** 2026-07-25
**Normative contract:**
[`2026-07-25-OME-605-screamingface-client-v1.md`](../spec/2026-07-25-OME-605-screamingface-client-v1.md)

## Outcome

Replace the unreleased exploratory package interface with one deep Client module:

```python
plan = sf.plan(candidates, benchmark="draco", limit=5)
report = sf.run(plan)
```

The Client hides validation, URL4 compilation, Engine transport, lifecycle replay, progress, and
Report assembly. Researchers learn two execution verbs. The asynchronous Client has the same
domain behavior and result types.

This work lands only in `packages/screamingface` plus its OME-605 repository artifacts. It does not
modify URL4, AI Gateway, `url4-cloud`, Studio, or the separately owned SF Engine.

## Confirmed test seams

Tests exercise behavior through these interfaces:

1. **Recipe authoring:** `Model`, `Fusion`, and `reducers.Synthesis`.
2. **Planning:** `Client.plan`.
3. **Execution:** `Client.run` and `AsyncClient.run`, observed through typed Events and Report or
   documented exceptions.
4. **Portable artifacts:** `Candidate.url4`, `CandidateResult.url4`, and Report JSON
   serialization. Plans and Reports do not invent a shared multi-Candidate URL4.
5. **Convenience interface:** lazy module-level `sf.plan` and `sf.run`.
6. **Engine contract adapter:** REST/WebSocket request and CloudEvents behavior against a
   controlled protocol server, without mocking private Client collaborators.

Future compiler helpers, transport state machines, caches, rich-rendering helpers, and default
Client storage are not independent test seams. They earn coverage through the interfaces above.

## Required migration exception

The inherited test and notebook suite specifies the deliberately superseded unreleased interface:
`sf.config`, `sf.benchmarks.load`, `Benchmark.evaluate`, `Recipe.url4`, SSE progress,
`Report | StudyReport`, and Client-side Benchmark authoring.

Implementing the approved contract therefore requires replacing or removing those obsolete
contract tests and regenerating the notebooks. This is an explicit exception to the ordinary
append-only-test rule, not permission to weaken retained behavior. Before each replacement:

- identify the obsolete assertion and the approved contract section that supersedes it;
- add the corresponding new public-interface test first;
- preserve still-valid security, parsing, naming, graph-identity, failure, and URL4 invariants; and
- record the append-only exception in the work ledger and PR.

## Vertical implementation slices

Each slice is one red → green → review cycle. Existing green behavior outside the explicitly
superseded interface remains green.

### Slice 1 — Immutable Recipe interface

**Public behavior**

- Implement the approved `Model`, `Fusion`, and `reducers.Synthesis` constructors.
- Preserve user-facing names while generating opaque URL4-safe internal bindings.
- Preserve object-identity graph sharing and independent equal-looking Recipe instances.
- Remove arbitrary `params`, Model-owned Tools, legacy Reducers, and `Recipe.url4`.

**Likely files**

- `src/screamingface/recipe.py`
- `src/screamingface/model.py`
- `src/screamingface/fusion.py`
- `src/screamingface/reducers.py`
- `src/screamingface/errors.py`
- `tests/test_recipes.py`

**Contract tests**

- defaults, explicit controls, immutability, inferred and preserved names;
- ordered members and unique direct-member names;
- nested Fusions, duplicate Candidate names, cycles, and empty members;
- reused identity versus deliberately independent samples; and
- rejection of removed keywords and unsupported local values.

### Slice 2 — Client configuration

**Public behavior**

- Add keyword-only `Client` and `AsyncClient`.
- Add immutable `BenchmarkInfo` provenance used by Plans and Reports.
- Add the lazy module-level default configured by `SCREAMINGFACE_ENGINE_URL`, defaulting to
  `https://engine.screamingface.ai`.
- Remove mutable `sf.config` and Engine-global mutable state.
- Keep discovery absent until the SF Engine publishes model and Benchmark catalogue schemas.

**Likely files**

- `src/screamingface/client.py`
- `src/screamingface/discovery.py`
- `src/screamingface/_default_client.py`
- `src/screamingface/__init__.py`
- `tests/test_client_configuration.py`

**Contract tests**

- no network on import or construction;
- configuration precedence and origin validation;
- lazy resource creation and deterministic close;
- matching synchronous and asynchronous semantics.

### Slice 3 — Engine-aware Evaluation planning

**Public behavior**

- Implement `Plan`, `Candidate`, `Operation`, and immutable Candidate/Operation collections.
- Implement `client.plan(candidates, benchmark=..., limit=...)`.
- Compile one complete canonical Candidate Evaluation URL4 per Candidate.
- Implement `client.plan(url4)` for complete supported single-Candidate expressions.
- Render the Plan overview and each Candidate's actual inspected Operation DAG without inventing
  unavailable estimates.

**Likely files**

- `src/screamingface/planning.py`
- `src/screamingface/_manifest.py`
- `src/screamingface/_display.py`
- `tests/test_planning.py`
- `tests/test_plan_display.py`

**Contract tests**

- one and many Candidates, complete Benchmark, and stable prefix;
- pinned Benchmark revision and capability profile;
- canonical URL4 round-trip through the public URL4 SDK;
- one complete independently executable URL4 per Candidate;
- identity memoization and independent samples inside each Candidate graph;
- invalid imported URL4, incompatible models/controls, unavailable capabilities, and request-size
  limits; and
- no paid execution during planning.

**External gate**

The SF Engine owner must publish the Benchmark discovery/manifest, capability-profile, and
per-Candidate URL4 compilation resources before the production compiler is implemented. Until then this slice ships
the immutable values and a typed public blocker only; it does not use fixtures to create a
production-looking compiler.

### Slice 4 — Typed Events and Report values

**Public behavior**

- Implement the approved Event variants and immutable Report model.
- Replace `Report | StudyReport` with one Report shape.
- Implement ordered Candidate lookup by position/name plus `.only`.
- Preserve partial domain failures as data and invalid/missing Reports as exceptions.
- Assemble each Candidate Result from its verified Candidate URL4 and Engine Run lifecycle.
- Keep terminal result decoding gated until the SF Engine publishes its versioned result schema.

**Likely files**

- `src/screamingface/events.py`
- `src/screamingface/report.py`
- `src/screamingface/_report_display.py`
- `tests/test_events.py`
- `tests/test_report.py`
- `tests/test_report_display.py`

**Contract tests**

- strict JSON decoding and round-trip;
- one/many/failed Candidates, direct-member summaries, failure ownership, and `report.ok`;
- score/primary-metric consistency and direction-aware optional gain;
- decimal monetary usage, Candidate/member subtree accounting, and derived Report summaries;
- exact per-Candidate Run identity, lifecycle timestamps, and complete URL4; and
- rejection of duplicate names, invalid metrics, malformed failures, and inconsistent lifecycle
  identity/timestamps.

### Slice 5 — REST/WebSocket Engine lifecycle

**Public behavior**

- Define Engine execution ports owned by the Client domain and isolate the concrete
  REST/WebSocket adapter behind composition.
- Implement one shared lifecycle state machine used by thin synchronous and asynchronous adapters.
- Mint the execution capability, open the WebSocket, send the initial `ai.url4.attach`, start with
  `Prefer: respond-async`, validate and order CloudEvents, replay gaps, consume exactly one root
  result, and terminate cleanly.
- Implement synchronous blocking and asynchronous awaiting without alternate result types.
- Implement `on_event`, built-in progress, and best-effort `ai.url4.stop` when callbacks or
  interruption abort the caller.

**Likely files**

- `src/screamingface/_transport.py`
- `src/screamingface/_engine_contract.py`
- `src/screamingface/_progress.py`
- `src/screamingface/client.py`
- `src/screamingface/errors.py`
- `tests/test_engine_contract.py`
- `tests/test_client_run.py`
- `tests/test_async_client_run.py`
- `tests/test_progress.py`

**Contract tests**

- public `Client.run`/`AsyncClient.run` behavior against a controlled protocol server, without
  monkeypatching private Client or transport functions;
- an owner-run integration check against the real OME-587 `url4-cloud` executor lifecycle;
- initial attach before start, canonical start request, required WebSocket subprotocol, and no
  direct AI Gateway access;
- event ordering, duplicate suppression, attach/replay, and terminal result handling;
- partial domain failure Report versus authentication/planning/execution exceptions;
- callback sequence, asynchronous callbacks, callback failure cancellation, and keyboard
  interruption;
- sync/async result parity and concurrent AsyncClient Runs; and
- terminal close, dead connection, timeout, malformed CloudEvents, missing/duplicate result, and
  reconnect failure.

**External gates**

Do not guess:

- how a Client mints a fresh capability for an existing disconnected Run;
- the authoritative heartbeat/liveness interval;
- hosted caller authentication; or
- final SF Engine REST/WebSocket route and schema names.

Confirmed behavior continues while each unresolved point remains a named blocker in
[`2026-07-26-OME-605-engine-requirements.md`](../spec/2026-07-26-OME-605-engine-requirements.md).
The Client does not expose a fallback or fixture-backed production path.

### Slice 6 — Lazy module interface

**Public behavior**

- Export only the approved v1 symbols.
- Implement module-level `sf.plan` and `sf.run` through one lazy synchronous Client.
- Ensure explicit Clients remain independent from the default.

**Likely files**

- `src/screamingface/__init__.py`
- `src/screamingface/_default_client.py`
- `tests/test_public_interface.py`

**Contract tests**

- exact public symbol allowlist;
- lazy construction and configuration precedence;
- delegated Plan/Report identity and error behavior; and
- absence of superseded aliases.

### Slice 7 — Documentation and package cleanup

**Public behavior**

- Rewrite the package README around `plan → run`.
- Regenerate the quickstart and architecture/Fusion notebooks.
- Remove obsolete Benchmark authoring, SSE, temporary connection-preflight, and legacy
  Report/StudyReport modules only after their valid invariants have migrated.
- Keep the package free of any deployable Engine implementation.

**Likely files**

- `README.md`
- `scripts/`
- `examples/`
- obsolete modules and obsolete tests identified by the replacement ledger

**Verification**

- generated notebooks have an explicit deterministic output policy and contain no accidental paid
  Run output;
- generated notebooks match their builders;
- README examples are covered by executable tests; and
- wheel contents expose no engine application or private contract fixtures.

## Issue and commit structure

After this plan is approved, keep `OME-605` as the parent contract item and create one
`py-screamingface` child issue per implementation slice or tightly coupled pair. Every child issue
uses one focused ledger and one or more conventional commits carrying its own `Refs:` identifier.
The Engine-contract questions remain relations/blockers rather than guessed work inside the Client
ticket.

Recommended dependency order:

```text
Recipe values
    ↓
Client configuration
    ↓
Planning ───────────────→ module-level interface
    ↓
Events + Report
    ↓
REST/WebSocket lifecycle
    ↓
documentation and cleanup
```

Slices 1, 2's local configuration values, and 4's pure Report/Event values can begin without the
unsettled Engine transport details. Planning's production manifest adapter and the lifecycle slice
remain gated.

## Package gates

Run from the repository root after every completed slice:

```bash
uv run .claude/scripts/run_gates.py screamingface
```

The authoritative stack requires:

- Ruff lint and format;
- Pyright;
- full Pytest with at least 95% coverage;
- public protocol-server and owner-run `url4-cloud` lifecycle verification;
- deterministic notebook verification; and
- wheel build.

No slice is committed with red gates. At the end, verify the branch diff contains no changes under
`packages/url4`, `apps/aigateway`, `url4-cloud`, or any Engine implementation.

## Approval required before implementation

Approval of this plan confirms:

1. the six public test seams above;
2. the explicit replacement/removal of inherited tests and notebooks that assert superseded
   unreleased interfaces;
3. the vertical slice and child-issue structure; and
4. that implementation pauses rather than guessing whenever an external Engine contract is
   unresolved.

Approval does **not** authorize adding a new WebSocket dependency; that choice will be presented
separately with the transport slice.
