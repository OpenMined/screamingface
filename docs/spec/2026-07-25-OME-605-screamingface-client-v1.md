---
title: ScreamingFace Python Client v1 contract
ticket: OME-605
status: superseded
date: 2026-07-25
approved: 2026-07-25
superseded_by: 2026-07-29-OME-605-direct-evaluation.md
---

# ScreamingFace Python Client v1 contract

> Superseded by the approved
> [direct evaluation interface](2026-07-29-OME-605-direct-evaluation.md). This document preserves
> the earlier design record; it is not the active public Client contract.

## 1. Decision

The unreleased `screamingface` package adopts one complete, inspectable Benchmark workflow:

```python
import screamingface as sf

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier_pair = sf.Fusion(
    "frontier-pair",
    members=[opus, gpt],
    reducer=sf.reducers.Synthesis(
        "openrouter/anthropic/claude-opus-4.8",
    ),
)

candidates = [opus, gpt, frontier_pair]

plan = sf.plan(
    candidates,
    benchmark="draco",
    limit=5,
)

plan
report = sf.run(plan)
```

Planning is mandatory. There is no direct `evaluate(...)` shortcut. This preserves a deliberate
inspection and validation point before paid execution without making the researcher orchestrate
Candidate execution, grading, and aggregation.

The two primary verbs have distinct meanings:

- `plan(...)` resolves and validates one complete Evaluation without executing paid work.
- `run(plan)` executes that exact Evaluation and returns one Report.

Module-level functions delegate to one lazy synchronous Client. Applications and advanced callers
may own explicit Clients:

```python
client = sf.Client(
    engine_url="https://engine.screamingface.ai",
)

plan = client.plan(candidates, benchmark="draco", limit=5)
report = client.run(plan)
```

The asynchronous interface has the same domain behavior and return types:

```python
async with sf.AsyncClient(engine_url=engine_url) as client:
    plan = await client.plan(candidates, benchmark="draco", limit=5)
    report = await client.run(plan)
```

There is no module-level asynchronous default.

## 2. Product and ownership boundary

```text
Researcher or SF App
        |
        v
SF Client
  Recipe authoring
  engine-aware planning
  URL4 inspection
  lifecycle consumption
  strict Report decoding
        |
        | SF Engine REST + WebSocket contract
        v
SF Engine
  Benchmark catalogue and manifests
  configured URL4 execution
  Candidate execution
  grading and aggregation
  Tool policy and caching
        |
        v
AI Gateway
  provider credentials and model dispatch
```

The SDK calls only its configured SF Engine. It never calls AI Gateway, model providers, Tavily,
or Benchmark datasets directly.

Local and hosted SF Engines expose the same Client-visible execution contract. In-memory channels,
NATS, deployment topology, and worker selection are Engine implementation details. Only the Engine
origin and, once defined by the SF Engine contract, its primary authentication mechanism vary for
the Client.

The SDK conforms to the published SF Engine OpenAPI and AsyncAPI contracts without importing the
`url4-cloud` server package.

## 3. Public v1 surface

The execution and authoring surface introduced by this contract is:

```python
sf.Client
sf.AsyncClient

sf.Model
sf.Fusion
sf.Recipe
sf.Reducer
sf.reducers.Synthesis

sf.Plan
sf.Candidate
sf.Operation
sf.Event
sf.Report
sf.CandidateResult
sf.MemberResult
sf.Failure
sf.Usage
sf.BenchmarkInfo

sf.plan
sf.run
```

Model and Benchmark discovery are not public until the SF Engine publishes authoritative catalogue
schemas. Researchers may still construct a Model from a known route and pass a known Benchmark
name to `plan(...)`; planning fails with a typed `PlanningError` until the production manifest
adapter exists. The Client never substitutes stale local catalogue data.

Hosted caller authentication and local or hosted provider setup are separate Engine concerns whose
final interfaces are not defined by this contract. In particular:

- there is no mutable `sf.config`;
- there is no public `sf.evaluate`;
- there is no public Candidate-only `query`, `execute`, or `run`;
- there are no public `grade` or `aggregate` stage operations;
- there is no public `Benchmark` constructor or Client-side Benchmark execution;
- there is no `StudyReport` type; and
- there are no compatibility aliases for superseded names.

## 4. Client configuration

The explicit constructors are keyword-only:

```python
sf.Client(
    *,
    engine_url="https://engine.screamingface.ai",
)

sf.AsyncClient(
    *,
    engine_url="https://engine.screamingface.ai",
)
```

The lazy synchronous default resolves configuration in this order:

1. an explicit Client argument;
2. `SCREAMINGFACE_ENGINE_URL`; and
3. `https://engine.screamingface.ai`.

Importing the package and constructing Clients or Recipes are network-free. Network work begins
only with planning or execution.

Primary caller authentication is intentionally not fixed in this Client contract until the SF
Engine owner publishes it. Hosted execution may require a long-lived caller credential; a local
Engine may permit unauthenticated access. Whatever primary mechanism is selected is distinct from
provider credentials, AI Gateway credentials, URL4 capabilities, and WebSocket tickets.

Short-lived URL4 capability minting is a transport implementation detail hidden by the Client.
Capability refresh for an existing disconnected Run remains blocked on the Engine contract.
Provider credentials are never accepted by a Recipe or sent directly to AI Gateway by the SF
Client. A future Engine-proxied provider-connection namespace remains blocked until the SF Engine
publishes that contract; v1 does not guess one.

`Client` is reusable across threads. `AsyncClient` is reusable by concurrent tasks on one event
loop and is not shared across event loops. Both lazily own transport resources and support
deterministic context-manager closure.

## 5. Recipe values

### 5.1 Model

`Model` is immutable, Client-independent, and network-free:

```python
sf.Model(
    model,
    *,
    name=None,
    instructions=None,
    temperature=None,
    reasoning=None,
    max_output_tokens=None,
)
```

The model route is the sole positional argument. The name defaults to the final route component
and may be overridden. Explicit names are trimmed and otherwise preserved exactly; the SDK never
silently lowercases or slugifies them. Empty names and control characters fail locally. V1
provides no arbitrary `params` mapping or provider-specific escape hatch. Unknown keywords fail
locally.

`instructions` are optional reusable behavior. Omission adds no hidden Model instructions.
Requested generation controls are validated against the selected Engine during planning and are
never silently ignored or clamped.

Models do not own Tools, retries, timeouts, judge settings, or response-format policy.

### 5.2 Fusion

`Fusion` is immutable, Client-independent, and requires an explicit name, ordered members, and one
Reducer:

```python
sf.Fusion(
    "frontier-trio",
    members=[opus, gpt, gemini],
    reducer=sf.reducers.Synthesis(model),
)
```

Members may be Models or nested Fusions. A Fusion requires at least two members; a single atomic
operation is a Model. Each member Recipe's name must be unique within that Fusion.
`fusion.members` is the immutable tuple of the original Recipe objects in declared order.
Researchers who need two independent samples give those Models distinct names and include them
normally:

```python
sample_1 = sf.Model(model, name="sample-1", temperature=0.7)
sample_2 = sf.Model(model, name="sample-2", temperature=0.7)

sf.Fusion(
    "opus-self-fusion",
    members=[sample_1, sample_2],
    reducer=sf.reducers.Synthesis(model),
)
```

Once the Engine publishes the manifest and Candidate URL4 contracts, the compiler must generate
opaque URL4-safe binding identifiers inside each Candidate expression, so user-facing names are
never constrained by URL4 struct-key syntax. The Client does not currently emit a substitute
Candidate-spec payload.

Member failure behavior is one generic Fusion invariant, not Benchmark policy:

- every declared member settles independently and remains present in declared order;
- the Reducer receives only successful member outputs, in their original relative order and with
  their member identities;
- failed members remain typed outcomes and are never converted into empty text or injected as
  error prose;
- one successful member is sufficient to run the Reducer; and
- the Fusion fails only when no member succeeds or its Reducer fails.

The same Fusion therefore has the same execution semantics against every Benchmark. A Benchmark
grades the resulting Candidate output but cannot make the Fusion strict or lenient. Nested
Fusions apply this rule recursively.

### 5.3 Synthesis

The model-backed Reducer surface is:

```python
sf.reducers.Synthesis(
    model,
    *,
    instructions=None,
    temperature=None,
    reasoning=None,
    max_output_tokens=None,
)
```

Synthesis has no name because its enclosing Fusion owns the Candidate name. It remains distinct
from Model because it reduces ordered member results rather than processing Benchmark Input.
Its first argument is a model route ID, not a `Model` Recipe instance; reduction is a distinct
operation and is never graph-shared with an answer-producing Model node.

When Synthesis instructions are omitted, planning resolves and pins a documented, versioned
default synthesis policy. Model instruction omission does not select that policy.

### 5.4 Graph identity

Recipe graph sharing inside one Candidate URL4 follows object identity:

- reusing the same Recipe instance shares one graph node per Benchmark case;
- separately constructed equal-looking Recipes remain independent nodes; and
- rendered URL equality never merges deliberately independent samples.

The production compiler must flatten nested Recipe construction into one valid URL4 DAG per
top-level Candidate while preserving these identities and declared ordering. Sharing between
separate Candidate Runs is an Engine cache/scheduling concern, not graph identity. No guessed
production compiler ships in place of the unpublished Engine contract.

Top-level Candidates accept one Recipe or an ordered Recipe sequence. V1 does not provide
Evaluation-local mapping aliases. Candidate names must therefore be unique before planning.

## 6. Benchmarks and planning

Benchmarks are immutable, versioned protocols registered by an SF Engine. They own cases, grading,
aggregation, Tool policy, judge configuration, output-budget policy, and execution constraints.
The Client neither defines nor overrides these fields during an Evaluation.

Researchers select a Benchmark by stable name:

```python
plan = client.plan(candidates, benchmark="draco", limit=5)
```

The Candidate-planning call shape is:

```python
client.plan(
    candidates,
    *,
    benchmark,
    limit=None,
)
```

`candidates` is one Recipe or an ordered Recipe sequence. A complete single-Candidate ScreamingFace
URL4 workflow uses the separate overload `client.plan(url4)`, which accepts no Benchmark or limit
arguments because those choices are already pinned in the expression.

The Engine resolves `draco` to a concrete immutable revision such as `draco@1`, and the Plan pins
that revision. Researchers do not load or bind a Benchmark object before planning. Reproducibility
comes from the pinned ID and versioned routes in each `plan.candidates[name].url4`, not from
requiring version syntax in the ordinary planning call.

`limit=N` selects at most the first N cases in the Benchmark's stable order. Omission selects the
complete Benchmark. `first`, `cases=N`, and `limit="all"` are not accepted.

The target planning flow contacts the configured SF Engine but starts no paid Candidate, Tool,
grading, or aggregation operations. Once the required contracts are published, it:

1. fetches the Engine's read-only capability profile;
2. resolves and fetches the pinned Benchmark manifest;
3. validates Candidate names and graph identity;
4. validates model, Reducer, Tool, connection, and generation-control compatibility;
5. resolves Benchmark defaults, including Synthesis policy and output budgets;
6. selects and pins the stable case prefix;
7. constructs one complete Candidate → grade → aggregate URL4 per Candidate locally;
8. submits each expression to the Engine's no-spend URL4 inspection boundary;
9. receives the Engine's canonical URL4 plus its stable operation map; and
10. returns an immutable `Plan`.

The Client owns typed Recipe validation and construction of the proposed URL4. The Engine owns the
authoritative executable interpretation: it parses, compiles, canonicalizes, and inspects that
URL4, assigns stable operation identities, and returns the actual dependency projection that its
runtime will execute. The Client must not reconstruct dependencies or invent operation IDs.

The exact route spelling for this no-spend inspection is an Engine contract question; it need not
be named `plan`. The Engine independently validates the canonical URL4 again when a Run starts.
Client planning improves safety and UX but never weakens the Engine's trust boundary.

Recipe construction is offline and network-free; planning is the explicit network boundary. If
the capability profile or pinned Benchmark manifest cannot be resolved, planning raises
`AuthenticationError` for rejected caller authentication and `PlanningError` for discovery,
connectivity, validation, or compatibility failure. The Client does not silently compile from a
stale cached manifest or provide an offline fallback. An existing Plan remains inspectable
offline, but before paid execution `run(plan)` verifies that the configured Engine is compatible
with the profile against which the Plan was compiled.

Until the manifest, capability-profile, and Candidate URL4 contracts are published, `plan(...)`
validates only its stable public argument shape and then raises a typed `PlanningError`. It neither
contacts a guessed route nor compiles an opaque fallback graph.

The Plan is the primary inspection surface:

```python
plan
plan.candidates
plan.candidates["frontier-trio"].url4
plan.candidates["frontier-trio"].operations
plan.operation_counts
plan.required_capabilities
```

Its notebook representation renders the Benchmark revision, case selection, ordered Candidate
overview, required capabilities, operation counts, and any Engine-provided estimates. It does not
invent a combined Evaluation DAG: the Evaluation is an orchestration scope, not one executable
URL4 graph.
Unavailable price or usage estimates are shown as unavailable rather than fabricated.

`operation_counts` describes the statically projected node executions across the Candidate URL4s
over the selected case prefix, grouped by kind. It does not promise provider-request counts or
cross-Candidate cache hits: Tool rounds, operational attempts, protocol repair, caching, and other
Engine-internal work may be dynamic. Any projected request count, token usage, duration, or cost
is a separately labeled Engine estimate with its uncertainty preserved.

`plan.candidates` is an immutable ordered collection of `Candidate` values supporting
integer position, Candidate name, and iteration. Each `Candidate.url4` is the complete
canonical Candidate Evaluation for the same pinned Benchmark revision and case selection. It
includes that Candidate's answer graph, grading, and aggregation, so it can be executed, inspected,
and shared independently. It is the only executable URL4 artifact on the Plan. Its notebook
representation renders that actual executable DAG.

`Candidate.operations` is the immutable Engine-derived projection of that compiled DAG. An
`Operation` contains only an opaque `id`, semantic `kind`, human-readable `label`, and
ordered `depends_on` IDs. Dependencies come from URL4 compilation rather than Client-side graph
analysis. The projection covers Candidate generation, explicit Tools/data routes, Synthesis,
grading, and aggregation.

Dynamic iteration rows, model-selected Tool calls, Tool rounds, judge passes, and operational
attempts are runtime occurrences of those planned Operations rather than thousands of pre-expanded
`Operation` values. Runtime Events join each occurrence to its planned Operation through
`operation_id` and retain occurrence coordinates plus trace/span identity. An explicit Tool node
in the URL4 is planned; a Tool call dynamically selected inside a model loop is observed beneath
the owning planned model Operation.

`Plan` deliberately has no `url4`, `operations`, or `graph` property because it is not a
combined executable graph. Programmatic graph data lives on each `Candidate`; the Plan's
rich representation remains an Evaluation overview.

`Plan`, `Candidate`, and `Operation` are public read-only result types, not public constructors.
Only the validated SF Engine planning response creates them. This prevents Client-authored values
from claiming canonical URL4 or operation identities that the Engine never inspected.

Plans have no `run`, `evaluate`, or `execute` methods. The Client owns execution.

Plans are not serialized as a second JSON or YAML workflow format. URL4 is the portable workflow
artifact. A receiving Client may validate one Candidate URL4 and reconstruct a one-Candidate,
Engine-resolved Plan:

```python
plan = client.plan(candidate_url4)
report = client.run(plan)
```

Only URL4 expressions that resolve to a supported complete ScreamingFace Report workflow can
become a Plan. Generic URL4 execution is outside the SF Client's public interface.

A Plan is bound to the pinned capability contract that resolved it, not to one Engine
origin. A different Client may run the same Plan when its Engine supports the pinned Benchmark
revision, referenced routes, required capabilities, and URL4/SF protocol versions. `run(plan)`
performs this compatibility check before starting paid work. It raises `PlanningError` when the
destination Engine is incompatible and directs the caller to re-plan the original Candidates
there. Execution never automatically re-plans, rewrites, or substitutes routes in an inspected
Plan.

## 7. Execution and Events

`run(plan)` coordinates one complete URL4 Run per Candidate:

```python
report = client.run(plan, on_event=handle_event)
```

Candidate Runs may execute concurrently subject to published scheduling limits. Their results
remain in declared Candidate order. Cross-Candidate answer reuse is an explicit Engine
cache/scheduling policy; it is not implemented by wrapping the Candidates in a hidden shared DAG.
Deliberately separate equal-looking Recipe objects inside a Candidate remain separate executions.

Its call shape is:

```python
client.run(
    plan,
    *,
    on_event=None,
    progress=None,
)
```

`progress=None` selects automatic notebook/interactive-terminal behavior; explicit `True` or
`False` forces or disables the built-in observer.

There is no public `retries` argument on `Model`, `Fusion`, `plan()`, or `run()`. Three distinct
behaviors must not be collapsed into one knob:

- Benchmark-owned **passes**, **samples**, and typed invalid-output repair are scientific
  protocol and are pinned by the immutable Benchmark revision;
- operational **attempts** recover a failed Provider, Tool, or data operation and are owned by
  AI Gateway or the responsible Engine adapter; and
- a transport **reconnect** reattaches to the same Run and replays missing Events without
  executing the Candidate again.

The Client never wraps a billable model route in URL4 `;retry=` or adds another Provider retry
layer. AI Gateway already owns Provider-aware overload retry and can distinguish a proven
transport failure from an ambiguous, possibly billed response. Any additional Engine retry around
a billable operation requires a published idempotency or deduplication guarantee.

Running the same Plan again creates a new Engine Run and `run_id` for each Candidate. Cross-run
caching is an Engine policy and must be visible through Events and Report provenance; the Client
does not silently reuse a prior Report. Run is a lifecycle concept, not a public constructible
`sf.Run` object. `Failure.retryable=True` means that an explicit later `run(plan)` may succeed; it
never instructs the Client to start another paid Run automatically.

The synchronous method blocks until a terminal Report or exception. It consumes the SF Engine
REST and WebSocket lifecycle internally. There is no `stream=True` mode and no alternate streaming
return type.

`on_event` is optional. When supplied, it receives typed meaningful Events from every Candidate
Run, including cases, Models, Tools, Fusion reduction, criteria, judge passes, aggregation, usage,
and terminal state. Every Event retains its Engine `run_id` and W3C trace context as distinct
identities; each root `Started` Event carries its Candidate URL4. Heartbeats, replay attachment,
capability refresh, and protocol bookkeeping remain internal.

`Client` accepts a synchronous callback. `AsyncClient` accepts a synchronous or asynchronous
callback and awaits asynchronous callbacks in Event sequence order. One callback is never invoked
concurrently for multiple Events.

Callbacks receive the common `sf.Event` interface. Concrete immutable variants live under
`sf.events`:

| URL4 Cloud CloudEvent | SF Client view |
|---|---|
| `ai.url4.started` | `sf.events.Started` |
| `ai.url4.log` | `sf.events.Log` |
| `ai.url4.span` | `sf.events.Span` |
| `ai.url4.cost.usage` | `sf.events.Usage` |
| `ai.url4.terminated` | `sf.events.Terminated` |

These are typed views over the existing CloudEvents envelope, not a competing ScreamingFace event
protocol. They preserve `run_id`, sequence, timestamp, source, trace context, and their typed
payload. Ordinary callbacks can use the common `kind` property; advanced callers may narrow to a
concrete variant for payload-specific fields such as log message, span, usage, or termination
status.

The real Engine adapter must preserve trace-parent linkage and map runtime URL4 source/span
identity to an opaque stable ScreamingFace `operation_id`. The Client uses the Plan's operation
mapping to attribute Events to Candidates, members, graders, aggregators, and Tools; it never
guesses ownership from model names or log text. `case_id`, criterion, pass, Tool round, and attempt
are occurrence coordinates rather than meanings encoded into the opaque ID. This is the
observation seam tracked by OME-446 and the real executor integration tracked by OME-587.

If a callback raises, the Client immediately attempts to cancel the Evaluation and then re-raises
the original callback exception. Cancellation failure never replaces it. Keyboard interruption
performs the same best-effort cancellation before propagating.

Notebook and interactive-terminal progress is enabled automatically unless `progress=False`.
Noninteractive execution is silent by default. Progress is an Event observer and never changes
execution, scheduling, or results.

### 7.1 Wire lifecycle

Every paid Run uses the Engine's asynchronous execution lifecycle internally:

1. obtain the short-lived execution capability;
2. open the WebSocket with the CloudEvents subprotocol;
3. send an initial `ai.url4.attach` with no replay cursor so the server subscribes the socket;
4. start the canonical URL4 over REST with `Prefer: respond-async`;
5. consume and validate ordered Events through `ai.url4.result` and
   `ai.url4.terminated`;
6. close the WebSocket after terminal state; and
7. pass the generic result body and media type to the ScreamingFace result decoder once that
   versioned Engine contract is published.

This does not make `Client.run()` nonblocking. The synchronous Client blocks while consuming that
lifecycle; `AsyncClient.run()` awaits it. The internal asynchronous Engine mode avoids the bounded
synchronous REST wait and gives both Clients identical progress, long-Run, and cancellation
semantics.

A succeeded termination requires exactly one valid result for the Run. A failed, stopped, or
timed-out termination without a promised valid Report raises the appropriate Client exception.
Partial Candidate, grading, and aggregation failures still travel inside a successfully produced
Report rather than changing the transport terminal state.

The generic URL4 lifecycle permits an optional media type and does not require JSON. The future
ScreamingFace Candidate-result contract may require a particular JSON media type and versioned
document shape at the decoder boundary, but the transport does not impose that unpublished rule.
Missing or duplicate root results remain lifecycle failures.

The Client consumes the Engine's structured CloudEvents lifecycle:

- `ai.url4.started`
- `ai.url4.log`
- `ai.url4.span`
- `ai.url4.cost.usage`
- `ai.url4.heartbeat`
- `ai.url4.result`
- `ai.url4.terminated`
- `ai.url4.error`

It uses monotonic `sequence` for deduplication and gap replay and uses `ai.url4.attach` when
reattaching. It uses `ai.url4.stop` for internal best-effort cancellation.

The public interface does not expose capability JWTs, WebSocket tickets, NATS topics, attach
commands, or heartbeats. `ai.url4.heartbeat` drives liveness internally;
`ai.url4.result` becomes the returned Report; `ai.url4.attach` drives replay; and advisory
protocol errors remain transport diagnostics.

The Client accepts heartbeat Events as liveness evidence but does not invent a dead-connection
interval. The exact heartbeat threshold, capability refresh, and long-disconnection recovery
behavior remain gated on the SF Engine contract. Explicit public resume and cancellation
operations are therefore outside this v1 scope.

Reconnect backoff is transport recovery, not Candidate retry. It preserves the original
`run_id`, URL4, and last contiguous Event sequence. An ambiguous REST start response is never
blindly repeated: without an idempotency guarantee, doing so could start duplicate paid work.

### 7.2 Confirmed implementation boundary

The Client may implement only behavior already published by the Engine execution contract:

- capability minting for a new Run;
- the `cloudevents.json` WebSocket subprotocol;
- initial and replay `ai.url4.attach`;
- asynchronous start using `Prefer: respond-async`;
- ordered CloudEvents decoding, duplicate suppression, and gap detection;
- terminal result/error handling; and
- best-effort `ai.url4.stop` while the current WebSocket remains available.

The Client does not ship guessed production behavior for caller authentication, capability renewal,
heartbeat expiry, discovery, Benchmark manifests, compatibility profiles, provider connections, or
the final Benchmark result schema. The deterministic requirements and their status live in
[`2026-07-26-OME-605-engine-requirements.md`](2026-07-26-OME-605-engine-requirements.md).

## 8. Report

`run(plan)` returns one immutable `sf.Report` for one or many Candidates. There is no
`Report | StudyReport` union.

The Python surface is:

```python
report.ok
report.benchmark
report.case_count
report.candidates
report.candidates[0]
report.candidates["frontier-trio"]
report.candidates["frontier-trio"].run_id
report.candidates["frontier-trio"].url4
report.candidates["frontier-trio"].operations
report.candidates.only
report.failures
report.usage
report.started_at
report.completed_at
report.duration_ms
report.to_dict()
report.to_json()
```

`report.candidates` is an immutable ordered collection supporting integer position, Candidate name,
and iteration. `.only` returns the sole Candidate Result and raises a clear error unless exactly
one exists. The SDK does not expose a universal `best` Candidate: score, cost, latency, reliability,
Fusion gain, and other study objectives are distinct ranking choices.

Each `CandidateResult.url4` is the complete independently runnable Candidate Evaluation preserved
from planning. `CandidateResult.operations` preserves the same immutable Engine-inspected
Operation projection, making member and Failure `operation_id` references interpretable after the
original Plan is no longer available. Its `run_id`, timestamps, and usage come from that
Candidate's Engine lifecycle.
The top-level Report is a Client collection, not an Engine Run, so it has no shared `.run_id` or
`.url4`. Overall timing spans the earliest Candidate start through the latest completion. Overall
usage sums a field only when every Candidate Run reported that field; otherwise that field remains
unavailable.

`report.benchmark` is the same public `BenchmarkInfo` value used by the Plan and retains the
Benchmark's total case count. `report.case_count` is the number of cases selected for this
Evaluation and cannot exceed that total.

A valid Report is returned even when domain work partially fails. `report.ok` is false when any
Candidate execution, grading, or aggregation Failure is present, and `report.failures` contains
one flattened ordered view of the typed evidence owned by its Candidates and their direct members.
If the Client cannot obtain and validate a promised Report because of
authentication, connectivity, incompatibility, protocol failure, or terminal Engine failure, it
raises instead.

Reports are summaries. Raw model answers, judge transcripts, and complete per-case evidence are
not embedded in v1.

### 8.1 Proposed JSON contract

The proposed public Report serializes as one JSON document validated as
`screamingface.report.v1`. JSON is the runtime result and Event interchange format; canonical
Benchmark Manifests are the separate human-authored YAML contract. The SF Engine result schema is
not yet published, so the Client does not currently decode a terminal result into this Report.

The SF Engine does not duplicate generic Run-lifecycle metadata inside each final URL4 aggregator
payload. The Client assembles every Candidate Result from Engine-produced sources:

- the Candidate Run's `ai.url4.result` body supplies validated Benchmark, metric, and Failure data;
- that Run's lifecycle Events supply its Engine-generated identity, timestamps, termination, and
  observed usage; and
- the corresponding `Candidate` supplies the canonical URL4 after it is verified against
  the root `ai.url4.started` Event.

The Client then orders those immutable Candidate Results according to the Plan. It does not compute
scores, grading, or aggregation.

```json
{
  "schema": "screamingface.report.v1",
  "started_at": "2026-07-25T16:00:00Z",
  "completed_at": "2026-07-25T16:00:48Z",
  "benchmark": {
    "id": "draco@1",
    "primary_metric": "normalized_score",
    "score_direction": "maximize",
    "case_count": 2
  },
  "candidates": [
    {
      "run_id": "run_01K...",
      "started_at": "2026-07-25T16:00:00Z",
      "completed_at": "2026-07-25T16:00:48Z",
      "name": "frontier-trio",
      "kind": "fusion",
      "url4": "(...)!/aggregators/draco/1()!'Produce the frontier-trio report'",
      "models": [
        "openrouter/anthropic/claude-opus-4.8",
        "openrouter/openai/gpt-5.5",
        "openrouter/google/gemini-3.1-pro-preview"
      ],
      "operations": [
        {
          "id": "op_01K_opus",
          "kind": "model",
          "label": "claude-opus-4.8 answer",
          "depends_on": []
        },
        {
          "id": "op_01K_gpt",
          "kind": "model",
          "label": "gpt-5.5 answer",
          "depends_on": []
        },
        {
          "id": "op_01K_gemini",
          "kind": "model",
          "label": "gemini-3.1-pro-preview answer",
          "depends_on": []
        },
        {
          "id": "op_01K_synthesis",
          "kind": "synthesis",
          "label": "frontier-trio synthesis",
          "depends_on": ["op_01K_opus", "op_01K_gpt", "op_01K_gemini"]
        },
        {
          "id": "op_01K_grading",
          "kind": "grading",
          "label": "DRACO grading",
          "depends_on": ["op_01K_synthesis"]
        },
        {
          "id": "op_01K_aggregation",
          "kind": "aggregation",
          "label": "DRACO aggregation",
          "depends_on": ["op_01K_grading"]
        }
      ],
      "score": 0.66,
      "metrics": {
        "normalized_score": 0.66,
        "coverage": 1.0
      },
      "members": [
        {
          "operation_id": "op_01K_opus",
          "name": "claude-opus-4.8",
          "kind": "model",
          "models": [
            "openrouter/anthropic/claude-opus-4.8"
          ],
          "failures": [],
          "duration_ms": 12840,
          "usage": {
            "input_tokens": 3200,
            "output_tokens": 710,
            "cost_usd": "0.0721"
          }
        },
        {
          "operation_id": "op_01K_gpt",
          "name": "gpt-5.5",
          "kind": "model",
          "models": [
            "openrouter/openai/gpt-5.5"
          ],
          "failures": [],
          "duration_ms": 11930,
          "usage": {
            "input_tokens": 3100,
            "output_tokens": 680,
            "cost_usd": "0.0614"
          }
        },
        {
          "operation_id": "op_01K_gemini",
          "name": "gemini-3.1-pro-preview",
          "kind": "model",
          "models": [
            "openrouter/google/gemini-3.1-pro-preview"
          ],
          "failures": [],
          "duration_ms": 10812,
          "usage": {
            "input_tokens": 3000,
            "output_tokens": 650,
            "cost_usd": "0.0507"
          }
        }
      ],
      "failures": [],
      "duration_ms": 48321,
      "usage": {
        "input_tokens": 12000,
        "output_tokens": 2400,
        "cost_usd": "0.1842"
      }
    }
  ],
  "usage": {
    "input_tokens": 12000,
    "output_tokens": 2400,
    "cost_usd": "0.1842"
  }
}
```

Candidate order is represented as a JSON array rather than an object keyed by user-controlled
names. Names remain unique lookup keys in the typed Python collection.

Every declared Candidate remains in that array in its declared position. A failed Candidate has
`score: null`, an empty `metrics` object, and typed failure evidence; it is never omitted and never
receives a fabricated zero score. A failed direct member likewise remains present with typed
failure evidence. Under the generic Fusion invariant, that member failure does not erase a valid
Fusion score when at least one member successfully reaches the Reducer and reduction succeeds;
`report.ok` remains false because the failure is still visible. This preserves the independent
outcome of every Candidate Run.

`benchmark.id` is the one canonical Engine-pinned Benchmark identity. The Report does not repeat
separate name and revision fields that could disagree. `primary_metric` and `score_direction`
(`maximize` or `minimize`) are copied from that pinned manifest so the Report remains
interpretable offline; callers cannot override them. In v1, Evaluations always select a stable
prefix of that pinned Benchmark, so
the serialized `benchmark.case_count` is the Report's selected case count and fully identifies the
evaluated case set without serializing every case ID. The Python `BenchmarkInfo.case_count` still
retains the Benchmark's total available count. Failures carry an individual `case_id` when
relevant.

Every Candidate contains an ordered `members` array. It is empty for a Model and contains compact
summaries of the direct members of a Fusion. A member summary contains its opaque root
`operation_id`, name, kind, flattened model routes, failures, duration, and usage, but does not
contain a score or metrics and does not recursively reproduce its own members. Names are display
and lookup labels; `operation_id` is the authoritative join to the Plan, Events, and result.
Fusion membership alone does not request independent grading. To obtain a member's score, the
researcher must also select that Recipe as a top-level Candidate. The canonical URL4 remains the
complete source for nested graph structure.

Every serialized Candidate preserves its ordered Operation projection. All member and Failure
`operation_id` values must resolve inside that projection; an unresolved reference is a malformed
Engine result rather than an opaque dangling identifier.

Failures are stored only at the level that owns them:

- each Candidate's `failures` contains failures attributable to that Candidate; and
- each direct member's `failures` contains failures attributable to that member.

The JSON does not duplicate those objects at the top level. The Python `report.failures` property
flattens both levels in deterministic Candidate order, and `report.ok` is true only when that
flattened collection is empty. `ok` is not serialized because it is derived and could otherwise
contradict the failure evidence.

Every Failure has this JSON-compatible shape:

```json
{
  "stage": "candidate",
  "code": "gateway_timeout",
  "message": "The configured model route timed out.",
  "retryable": true,
  "operation_id": "op_01K...",
  "case_id": "case-002"
}
```

`stage`, `code`, `message`, `retryable`, and `operation_id` are required. `stage` is one of
`candidate`, `grading`, or `aggregation`; `code` is lowercase snake_case. `case_id` is omitted
when the Failure is not owned by one Case. HTTP status, timestamps, attempts, model/provider
names, stack traces, arbitrary details, sensitive provider payloads, credentials, and raw
responses never appear in a Failure. The Candidate Result's Operation projection and lifecycle
Events own that execution evidence.

`cost_usd` is a decimal string, matching the Engine event contract without introducing binary
floating-point money. Unknown usage fields are omitted rather than filled with zero. `baseline`
and `gain` are optional Benchmark-produced metrics, not universal synthesized values. When a
Benchmark defines `baseline` from independently graded member Candidates, the value is computed
over the same paired case set as the Fusion score. The Engine never creates hidden grading work
solely to populate these optional fields.

Candidate `score` is the convenient primary score and must equal
`metrics[benchmark.primary_metric]` whenever it is non-null. Scores and metric values are finite
JSON numbers, but their valid ranges remain Benchmark-defined rather than universally constrained
to zero through one. `baseline` uses the same scale as the primary score. `gain` is
direction-aware: `score - baseline` for `maximize` and `baseline - score` for `minimize`, so a
positive value always means the Candidate improved over its baseline.

`Usage` contains token and monetary accounting only. Candidate and direct-member wall-clock timing
is exposed separately as `duration_ms`; member durations are never summed because graph branches
may execute in parallel. Candidate duration is derived from its Engine lifecycle timestamps. The
Report duration spans the earliest Candidate start through the latest Candidate completion.

Every Candidate `usage` object is the observed total for that independent Run, including its
answer, Fusion reduction, grading, and aggregation work. Direct-member usage covers that member's
answer subtree and therefore overlaps with its Candidate parent. Report usage sums the independent
Candidate Run totals field by field only when every Run reported that field; incomplete fields
remain unavailable. Failed operations retain tokens and cost consumed before failure.

The SF Engine creates each Candidate Run identity and lifecycle timestamps in CloudEvents. The
Client uses that root Event subject as the Candidate Result's `run_id`, the root `started` time as
`started_at`, and the root `terminated` time as `completed_at`, validates their consistency, and
exposes them unchanged. Client request and receipt times never replace those authoritative
lifecycle values.

Each Candidate URL4's final versioned aggregator route determines its result payload schema. URL4
represents how that result is produced and pins that route; it does not duplicate the complete JSON
Schema inline. `Report.to_json()` produces the complete portable comparison after the Client
validates and orders all Candidate results.

Leaderboard authorship, publication state, ownership, privacy, and submission source do not belong
in the Report. Studio derives its leaderboard submission projection from Report data and combines
it with that application metadata.

## 9. Error interface

V1 keeps the public exception hierarchy small:

```python
sf.ScreamingFaceError
sf.AuthenticationError
sf.PlanningError
sf.ExecutionError
```

Ordinary invalid local Python arguments raise `TypeError` or `ValueError`. Standard Python
cancellation and interruption exceptions retain their normal meaning.

Engine Problem Details and terminal URL4 errors are preserved as structured diagnostic fields on
the appropriate exception without exposing transport-specific classes for every status code.

Failures inside a valid Report are data, not exceptions.

## 10. Current-package migration

| Current surface | V1 disposition |
|---|---|
| `sf.config(...)` | remove; configure explicit Client or environment-backed lazy default |
| `sf.benchmarks.load(...)` | remove from execution flow |
| `Benchmark.evaluate(...)` | replace with mandatory `plan = sf.plan(...)`; `sf.run(plan)` |
| `Benchmark.url4(...)` | replace with complete per-Candidate `plan.candidates[name].url4` |
| `Recipe.url4` | remove; executable URL4 appears only after planning and is preserved on the corresponding Report values |
| public `sf.Benchmark` / `sf.Case` construction | remove from Client v1 |
| `sf.Report` and `sf.StudyReport` | replace with one `sf.Report` shape |
| legacy candidate-result mapping | replace with typed `CandidateResult` values in one immutable ordered indexed/name lookup collection |
| temporary SSE evaluator | replace with the SF Engine REST + WebSocket lifecycle |
| `sf.config` default localhost | replace with lazy default `https://engine.screamingface.ai` |
| arbitrary `params` dictionaries | remove; use typed portable Model and Synthesis controls |
| `reducers.Model` | replace with `reducers.Synthesis` |
| Model-owned or provider-specific Tools | exclude; Benchmark/Engine policy owns Tools |
| SDK-local grading and aggregation remnants | remove; complete URL4 executes Engine-side |
| generated quickstart notebooks | regenerate against `plan → run` only |
| existing connection-management namespace | leave outside OME-605 pending the SF Engine contract |

## 11. Explicit non-goals

- modifying URL4, AI Gateway, `url4-cloud`, Studio, or the SF Engine implementation;
- redesigning or removing provider connection management before its Engine contract is approved;
- executing URL4 locally inside the Python package;
- custom Benchmark publication or registration;
- multi-Benchmark suites in one Plan;
- a public Client-side Benchmark constructor;
- direct Candidate inference or an ad-hoc query surface;
- public Candidate execution, grading, or aggregation stage methods;
- intermediate Artifact retrieval;
- Plan JSON or YAML serialization;
- generic URL4 execution;
- public explicit resume or cancellation before the Engine contract settles them;
- raw answers and judge transcripts in Report; and
- leaderboard submission.

## 12. Remaining external gates

The contract-independent Client implementation is approved and complete. Production adapters stay
blocked until their owners publish:

1. the Engine's Benchmark manifest and capability-profile resources;
2. the Engine's per-Candidate Benchmark URL4 compilation contract;
3. the Engine's versioned Candidate-result schema;
4. capability refresh and heartbeat-liveness policy for reconnecting to an existing Evaluation;
5. hosted caller authentication and local-auth behavior;
6. authoritative model, Benchmark, and provider-connection schemas; and
7. stable SF operation identity mapped to executor source/spans for Event attribution and truthful
   per-Candidate DAG display; and
8. Candidate scheduling and cache-reuse semantics for DRACO-compatible runs; and
9. deterministic and live acceptance against one explicitly pinned full-DRACO reference
   protocol.

The deterministic status and executable skipped requirements are maintained in
[`2026-07-26-OME-605-engine-requirements.md`](2026-07-26-OME-605-engine-requirements.md) and
`packages/screamingface/tests/test_external_contract_requirements.py`.
