---
title: ScreamingFace benchmark public contract
ticket: OME-400
status: approved
date: 2026-07-18
---

# ScreamingFace benchmark public contract

## 1. Decision

ScreamingFace is an unreleased SDK with no compatibility requirement. This document is the
approved greenfield contract for its first benchmark implementation. Existing SDK code and
notebooks are implementation material, not a public surface to preserve.

The short path is:

```python
import screamingface as sf

fusion = sf.Fusion(
    "frontier-trio",
    models=[
        "codex/gpt-5.5",
        "gemini/2.5",
        "claude/sonnet-4.6",
    ],
    reducer=sf.reducers.MajorityVote(),
)

report = fusion.evaluate("gpqa@1", first=20)
```

The research form exposes the same four stages:

```python
benchmark = sf.benchmarks.load("draco@1")
run = fusion.run(benchmark, first=5)
grades = run.grade()
report = grades.aggregate()
```

The semantic seams are:

```text
LOAD -> RUN -> GRADE -> AGGREGATE
```

`Fusion.evaluate()` is exactly the one-call facade over those stages. Both `run()` and
`evaluate()` accept `str | Benchmark`; passing a string calls `sf.benchmarks.load(...)`
internally.

## 2. Public surface

Phase 0 establishes:

```python
sf.config
sf.Fusion
sf.Benchmark
sf.Case
sf.Reducer
sf.Grader
sf.Aggregator
sf.Run
sf.CaseResult
sf.MemberResult
sf.RunFailure
sf.Grades
sf.Report
sf.models
sf.benchmarks
sf.reducers
sf.graders
sf.aggregators
```

Abstract extension interfaces remain top-level. Concrete strategies live only in plural
namespaces:

```python
sf.reducers.Model(...)
sf.reducers.MajorityVote()
sf.graders.ExactChoice()
sf.graders.Rubric(...)
sf.aggregators.Mean()
```

There are no duplicate aliases such as `sf.ModelReducer`, `sf.MajorityVote`, or
`sf.RubricJudge`. There is no public `sf.judges` namespace.

Low-level result records are immutable values surfaced through `Run` and `Grades`. `CaseResult`,
`MemberResult`, and `RunFailure` are exported for inspection and type checking, but users receive
them from `Fusion.run()` rather than constructing them as configuration.

Not included in the MVP:

- a public `Engine`, `Client`, `Runner`, `Loader`, `Row`, or `Task`;
- an ETL, dataset-mapping, or benchmark-building DSL;
- `fork()`, `with_changes()`, automatic Python-path execution, or a benchmark CLI;
- `sf.runs`, persistence, resume, cost, budgets, hashes, or publication;
- `primary_metric`, a public `Score` wrapper, or a benchmark-level generation seed;
- an in-process URL4 engine, simulated responses, or mock runtime mode;
- authentication/provider-key UX; or
- direct SDK access to AI Gateway or a model provider.

## 3. Engine configuration and boundary

The SDK has one effective URL4 engine:

```python
# Temporary default while no hosted deployment exists.
# http://127.0.0.1:4404

sf.config(engine="https://url4.example.org")
```

Importing ScreamingFace and directly constructing a `Fusion`, `Case`, or `Benchmark` perform no
network request. Registry discovery, named benchmark loading, fusion execution, and model-backed
grading use the configured HTTP engine.

The architecture is:

```text
ScreamingFace SDK
  -> screamingface-engine       GET /v1?q=<URL4 expression>
     -> one persistent Url4Node evaluator
     -> startup-registered, in-process SF model/RDS handlers
        -> AI Gateway     POST /v1/chat/completions
           -> provider
```

Only screamingface-engine contacts AI Gateway. Generic `packages/url4` remains unaware of
ScreamingFace benchmarks, reducers, registries, or gateway details.

`screamingface-engine` is one long-running Python/ASGI process. It constructs a `Url4Node`,
registers its data and endpoint handlers once at startup, and serves `node.asgi()` with Uvicorn.
It does not use the native `url4 serve` TOML `[commands]` adapter for model or reducer routes, and
it never launches the `screamingface-engine` executable again while evaluating a request.

This keeps the complete URL4 protocol surface: parsing, parameters, bindings, structs,
collections, iteration, broadcast, quorum, holdings, identities, outbound resolution, error
mapping, and `GET /v1?q=...` all remain owned by the same public `Url4Node`. FastAPI and Hono are
not part of the engine core.

The SDK and engine profile mirror only remotely executable vocabulary. This is an execution
profile, not one HTTP endpoint per SDK class:

| SDK concept | Engine counterpart |
|---|---|
| model ID | model route |
| `reducers.MajorityVote()` | deterministic RDS reducer route |
| `benchmarks.list/load` | SF discovery, manifest, and cases resources |
| `graders.Rubric(model=...)` | ordinary calls to the advertised judge-model route |
| `graders.ExactChoice()` | none; deterministic SDK computation |
| `aggregators.Mean()` | none; deterministic SDK computation |

## 4. SF engine discovery

screamingface-engine exposes an application-owned discovery document:

```http
GET /.well-known/screamingface
```

It is not part of generic URL4 core. The MVP shape is:

```json
{
  "schema": "screamingface.registry.v1",
  "response_schemas": ["screamingface.fusion-result.v1"],
  "models": [
    {
      "id": "codex/gpt-5.5",
      "supported_tools": []
    },
    {
      "id": "gemini/2.5",
      "supported_tools": []
    },
    {
      "id": "claude/sonnet-4.6",
      "supported_tools": []
    }
  ],
  "reducers": [
    {
      "id": "majority_vote",
      "route": "/reducers/majority-vote"
    }
  ],
  "benchmarks": [
    {
      "id": "gpqa@1",
      "manifest": "/benchmarks/gpqa@1",
      "tools": []
    },
    {
      "id": "draco@1",
      "manifest": "/benchmarks/draco@1",
      "tools": ["web_search"]
    }
  ]
}
```

The registry advertises addressable engine resources, not every SDK abstraction. Graders and
aggregators are serialized in benchmark manifests but do not get separate registry entries when
the ordinary client workflow executes them locally.

Public discovery returns IDs only:

```python
sf.models.list()
sf.models.list(query="gemini", tools=["web_search"], limit=10)

sf.benchmarks.list()
sf.benchmarks.list(query="draco", tools=["web_search"], limit=10)
```

Both return `list[str]`. Filters are arguments to `list()`; there is no separate `search()` in
the MVP. The SDK does not expose internal registry summary objects.

## 5. Model identity

The invariant is:

```text
public model ID = URL4 relative route without its leading slash
```

Examples:

```text
codex/gpt-5.5          -> /codex/gpt-5.5
gemini/2.5             -> /gemini/2.5
claude/sonnet-4.6      -> /claude/sonnet-4.6
```

The engine privately maps these routes to AI Gateway identifiers. For example,
`/gemini/2.5` may map to `gemini-cli/gemini-2.5-pro`. That provider mapping never appears in a
Fusion recipe or result.

One canonical engine catalog owns the public ID, relative route, supported tools, and private AI
Gateway model ID. The engine derives both startup route registration and
`/.well-known/screamingface` from that catalog so an advertised model cannot drift from its
handler.

Making the public ID equal to the route identity allows local Fusion construction and URL4
rendering without registry I/O. Evaluation still performs registry preflight.

### 5.1 Persistent model endpoint contract

Every advertised model route is registered once on the persistent node with
`node.endpoint(route)(handler)`. The decorator form and the explicit registration form are the
same public URL4 API; the engine uses explicit registration so the catalog can support many models
without handwritten decorators.

The handler receives URL4's decoded request:

```python
Request(
    path="/codex/gpt-5.5",
    context="<resolved question>",
    intent="<model instructions>",
    params={
        "temperature": "0.2",
        "max_tokens": "512",
        "reasoning": "low",
    },
)
```

The engine translates it to AI Gateway's existing chat-completions contract:

```json
{
  "model": "<private gateway model ID>",
  "messages": [
    {"role": "system", "content": "<request.intent>"},
    {"role": "user", "content": "<request.context>"}
  ],
  "temperature": 0.2,
  "max_tokens": 512,
  "reasoning_effort": "low"
}
```

The mapping is deliberately typed and allowlisted:

- `temperature` parses as a finite float;
- `max_tokens` parses as a positive integer;
- `reasoning` maps to AI Gateway's `reasoning_effort` field;
- `tools=web_search` names an engine-owned capability adapter rather than being forwarded as an
  arbitrary provider payload; and
- unknown parameters, malformed values, and unsupported tools fail before Gateway traffic.

The registry may advertise `web_search` for a model only when that route has a working named-tool
adapter. Otherwise SDK preflight must reject a benchmark that requires it.

Phase 2A therefore advertises no tools. The DRACO manifest remains discoverable and truthfully
declares `web_search`; loading or running it must fail SDK preflight until a tested named-tool
adapter and its compatible model routes are published. Its `gemini/3.1-pro-preview` judge route is
likewise not advertised until AI Gateway registers an exact private model mapping.

For a successful non-streaming response, the handler validates
`choices[0].message.content`, requires string content, and returns that string only. URL4 therefore
sees an ordinary plaintext endpoint result. AI Gateway transport errors, non-success statuses, and
malformed success envelopes become transient URL4 `ResolutionError`s and surface through the
engine's normal URL4 error-to-HTTP mapping.

The process owns one reusable asynchronous AI Gateway client. Route handlers do not construct a
new client, launch a subprocess, or start another server. The application closes the Gateway
client and node resources during ASGI shutdown.

### 5.2 Application-owned ASGI lifecycle

The engine serves a thin application-owned wrapper around `node.asgi()`. The wrapper owns only
deployment lifecycle concerns that `Url4Node` deliberately does not:

- create one reusable AI Gateway client during startup;
- reject work above the configured global in-flight limit with HTTP 503;
- bound one complete `/v1` evaluation with a configured deadline and return HTTP 504 on expiry;
- close the Gateway client and call `node.aclose()` during graceful shutdown; and
- delegate every accepted request to the unchanged URL4 ASGI application.

It contains no route matching, URL4 parsing, expression execution, model mapping, benchmark
behavior, or response reshaping. It does not use FastAPI, Hono, or URL4's private `_serve` module.
This preserves one URL4 dispatch path while giving the production application explicit resource
ownership.

## 6. Benchmark loading and manifests

Benchmark identities such as `draco@1` and `gpqa@1` are opaque versioned strings. Phase 0 does
not define semantic-version ranges, `latest`, or a separate `version=` field.

```python
benchmark = sf.benchmarks.load("draco@1")
```

`load()` resolves the registry record and fetches its manifest. It does not look for a matching
benchmark implementation installed locally and does not download or execute Python.

Example manifest:

```json
{
  "schema": "screamingface.benchmark.v1",
  "id": "draco@1",
  "title": "DRACO",
  "tools": ["web_search"],
  "cases": {
    "url": "/benchmarks/draco@1/cases",
    "format": "ndjson"
  },
  "grader": {
    "type": "rubric",
    "model": "gemini/3.1-pro-preview",
    "prompt": "<pinned official judge prompt>",
    "passes": 5,
    "params": {
      "temperature": 0.2,
      "reasoning": "low",
      "max_tokens": 4096
    }
  },
  "aggregator": {
    "type": "mean"
  }
}
```

The case resource contains already-normalized NDJSON:

```json
{"id":"q1","input":"<research question>","reference":{"sections":[...]},"metadata":{"domain":"Finance"}}
{"id":"q2","input":"<research question>","reference":{"sections":[...]},"metadata":{"domain":"Medicine"}}
```

This wire schema is not ETL. Engine-side benchmark authors fetch, clean, and normalize source
datasets in ordinary Python before publishing canonical `Case` records.

All discovery, manifest, cases, execution, and judge bodies are read through `response.text` and
then parsed/validated by the SDK.

## 7. Universal `Case` and `Benchmark`

Every benchmark uses:

```python
sf.Case(
    id: str,
    input: str,
    reference: JsonValue = None,
    metadata: Mapping[str, JsonValue] = {},
)
```

Rules:

- `input` is the only case content available to workers.
- `reference` is sealed from every worker and reducer expression and is available only to the
  grader.
- `metadata` supports slicing/reporting and is never silently inserted into a prompt.
- duplicate case IDs and malformed references fail preflight before paid calls.
- `input` is string-only in the MVP; richer multimodal inputs can be added deliberately later.

Direct benchmark authoring is ordinary Python:

```python
sf.Benchmark(
    "draco@1",
    title="DRACO",
    cases=load_cases,
    grader=sf.graders.Rubric(...),
    aggregator=sf.aggregators.Mean(),
    tools=("web_search",),
)
```

Constructor contract:

```python
Benchmark(
    id: str,
    *,
    cases: Sequence[Case] | Callable[[], Iterable[Case]],
    grader: Grader,
    title: str | None = None,
    aggregator: Aggregator = aggregators.Mean(),
    tools: tuple[str, ...] = (),
)
```

`cases=` is a private authoring seam. `Benchmark` does not expose dataset browsing,
`iter_cases()`, indexing, source-column mappings, or transformation hooks. A local custom
Benchmark is network-free to construct, but running it still requires the configured engine for
model work.

Benchmark `tools` are concrete model-usable actions. They are added only to answer-producing
panel routes. Reducers and graders do not inherit them.

## 8. Fusion authoring

The final model-input shape is:

```python
fusion = sf.Fusion(
    "frontier-trio",
    models=[
        "codex/gpt-5.5",
        "gemini/2.5",
        {
            "model": "claude/sonnet-4.6",
            "prompt": CLAUDE_PROMPT,
            "params": {"temperature": 0.3},
        },
    ],
    prompt=DEFAULT_PANEL_PROMPT,
    reducer=sf.reducers.Model(
        model="codex/gpt-5.5",
        prompt=SYNTHESIS_PROMPT,
        params={"temperature": 0.0},
    ),
)
```

Rules:

- a string is the common member shorthand;
- a mapping configures only that member's model, prompt, or model parameters;
- `Fusion.prompt` is the default panel intent and a member prompt overrides it;
- omitted prompts use the minimal SDK default `"Answer the question."`;
- repeated models remain distinct ordered execution slots (`panel_1`, `panel_2`, ...);
- model parameters become query parameters on that model route;
- reducers are explicit strategy objects; and
- a DRACO reproduction pins its research-answer prompt in the Fusion.

`reducers.Model` uses the same conceptual `model`, `prompt`, and `params` fields as a configured
member. `reducers.MajorityVote()` performs deterministic exact-string voting and breaks ties by
stable panel order.

URL4 interpolates embedded references in prompt templates. Researchers may therefore reference
`$question` deliberately, but they do not need to repeat the question in the prompt: every panel
route already receives it as URL4 context. The prompt is normally just the model's system-level
instruction.

For `reducers.Model`, the compiler—not the researcher—constructs the reducer's user context from
the resolved question and every labeled panel answer:

```text
Question:
<resolved question>

Panel answers:
Panel 1 [codex/gpt-5.5]:
<resolved answer>

Panel 2 [gemini/2.5]:
<resolved answer>
```

`reducers.Model.prompt` is the synthesis instruction sent as the model route's intent. It may
still contain URL4 references when a researcher intentionally wants a custom template, but a
simple instruction such as `"Synthesize the panel answers into one final answer."` is complete.

## 9. Reducer execution

Everything that contributes to producing the fusion answer belongs in the URL4 graph.

A model reducer is another model node. Deterministic majority vote uses the screamingface-engine
RDS route:

```text
/reducers/majority-vote
```

It receives a resolved panel-answer object, makes no AI Gateway call, and returns only the winning
answer as text. The implementation should reuse the same ScreamingFace reducer logic rather than
reimplementing it independently in the engine app.

The Phase 2B request contract is deliberately narrow:

- context is a JSON object with exactly contiguous `panel_1` through `panel_n` keys, where
  `n >= 2`;
- each value is a non-blank string;
- object insertion order is irrelevant because stable order is the numeric `panel_n` order;
- votes use exact raw-string equality, so `A`, `a`, and `A\n` are distinct answers;
- an exact tie selects the lowest numeric panel position;
- intent and query parameters are rejected; and
- malformed input raises a permanent URL4 `malformed_source` error, invalidating the whole
  expression rather than returning a partial Fusion object.

The route's successful body is the winning answer's raw text. URL4 substitutes that resolved text
into the outer expression's final `screamingface.fusion-result.v1` structure; the reducer does not
return a result envelope or a rewritten URL4 expression.

This route is legitimate SF execution behavior. It is distinct from adding an SF-specific output
packager merely to reshape JSON.

## 10. One URL4 request per case

`fusion.url4` is the canonical, shareable URL4 recipe template. It contains stable `panel_n`
slots and an intentionally unbound `$question`, but no benchmark case or answer key. The compiler
constructs this template with URL4's public builder/AST facade and renders it with URL4's
certified renderer; it does not concatenate ad-hoc URL4 strings. `run.fusion_url4` preserves this
same template.

For execution, the SDK adds one literal `question` binding to the template. Dollar signs in case
input are escaped as URL4 literal data; dollar references in researcher-authored prompt templates
remain active. The resulting concrete expression is still one request.

One selected case produces one complete URL4 expression containing the question binding, panel
fan-out, reducer, and final result structure. Conceptually:

```url4
(
  question='<resolved case input>',

  panel_1=/codex/gpt-5.5($question)!'Answer the question',
  panel_2=/gemini/2.5($question)!'Answer the question',

  panel_answers={
    panel_1: '$panel_1',
    panel_2: '$panel_2'
  },

  fusion_answer=/reducers/majority-vote($panel_answers),

  {
    schema: 'screamingface.fusion-result.v1',
    members: {
      panel_1: {
        model: 'codex/gpt-5.5',
        answer: '$panel_1'
      },
      panel_2: {
        model: 'gemini/2.5',
        answer: '$panel_2'
      }
    },
    answer: '$fusion_answer'
  }
)
```

The SDK sends:

```http
GET <engine>/v1?q=<percent-encoded-complete-expression>
```

The engine evaluates internal nodes and returns canonical JSON text:

```json
{
  "schema": "screamingface.fusion-result.v1",
  "members": {
    "panel_1": {
      "model": "codex/gpt-5.5",
      "answer": "<response>"
    },
    "panel_2": {
      "model": "gemini/2.5",
      "answer": "<response>"
    }
  },
  "answer": "<reduced fusion response>"
}
```

The `panel_n` object keys are the member/call-slot IDs, so an inner `id` field would be redundant.

Current URL4 structured-object fields support strings, bare scalars, and nested objects, but not
embedded arrays. The nested `members` object is therefore the native representation. An array
would require a separate SF result-packaging operation or future response-envelope functionality,
neither of which is needed.

The HTTP success body is consumed as text:

```python
payload = json.loads(response.text)
```

The SDK validates the schema, expected member slots, model IDs, member answers, and final answer.
It rejects missing or additional fields, missing or unexpected slots, wrong model IDs, and blank
member/final answers. It reconstructs member order from the expected numeric panel slots rather
than trusting JSON object insertion order. It preserves accepted answer text exactly and never
guesses or repairs an invalid engine result.

A model reducer compiles to another ordinary model route. Its context contains the resolved
question and labeled panel answers in the stable format defined in §8; its intent is
`reducers.Model.prompt`, and its declared model parameters become route query parameters. The
final response structure is identical for model and deterministic reducers.

## 11. Preflight

Before any answer or judge call, evaluation:

1. fetches and validates `/.well-known/screamingface`;
2. resolves the benchmark manifest;
3. loads and validates the selected canonical cases;
4. validates every selected reference;
5. confirms every panel, reducer, and judge model exists;
6. confirms every panel model supports all benchmark tools;
7. confirms required deterministic reducer routes are advertised; and
8. confirms the fusion response schema is supported.

Representative typed failures are:

```python
sf.UnknownBenchmarkError
sf.UnknownModelError
sf.UnsupportedToolError
sf.UnsupportedReducerError
sf.InvalidBenchmarkError
sf.EngineProfileError
sf.EngineConnectionError
sf.EngineProtocolError
```

For the MVP, a model advertised by the registry is one the engine claims is available. User- or
credential-specific availability belongs to a future engine authentication contract.

## 12. `Run`

`Fusion.run()` executes the selected cases and returns an immutable, serializable, in-memory
artifact:

```python
run = fusion.run("draco@1", first=5)

run.benchmark_id
run.fusion_url4
run.case_ids
run.results
run.failures
run.complete
```

Both forms are supported:

```python
fusion.run("gpqa@1", first=20)  # loads the advertised benchmark
fusion.run(benchmark, first=20) # uses an existing local/loaded definition
```

`first` is either `None` (all cases) or a positive integer selecting the canonical prefix. It does
not reshuffle cases, and values larger than the benchmark simply select all available cases. There
is no generation seed in the MVP.

Each result preserves its selected case position:

```python
result.case_id
result.members["panel_1"].model
result.members["panel_1"].answer
result.answer
result.failure
```

`result.members` is an immutable mapping keyed by the `panel_n` call-slot ID. The key is the ID, so
`MemberResult` contains only `model` and `answer`; it does not repeat an `id` field. A successful
`CaseResult` has the complete expected member mapping, a non-blank final answer, and
`failure=None`. A failed result has `answer=None`, an empty member mapping, and one `RunFailure`.

`run.failures` is the stable tuple of those `RunFailure` values. Each exposes:

```python
failure.case_id
failure.kind       # connection | timeout | http | url4 | protocol
failure.message
failure.status     # int | None
failure.code       # str | None
```

`connection` means that the configured engine could not be reached. `timeout` includes a client
deadline or the engine's structured 504 timeout. `url4` means a recognized structured execution
error. `http` is an otherwise unrecognized non-success response. `protocol` means that a 200 body
was not the exact plaintext `screamingface.fusion-result.v1` contract.

Required panel/reducer failures invalidate the whole case. The SDK does not construct a partial
fusion answer. URL4-native optional/quorum behavior can be added explicitly later.

One case request is atomic but the selected benchmark run is not fail-fast. A failed case remains
at its original selected position while every unrelated selected case is allowed to finish under
the bounded concurrency policy. Stable input order, not completion order, determines
`run.results`. Failures preserve safe messages and, when available, the HTTP status and URL4 error
code; they never retain credentials, provider payloads, or mutable exception objects.

Phase 2 performs no automatic SDK retry. This avoids silently duplicating paid model calls when a
connection is interrupted after the engine or provider has already accepted work. A future retry
policy must be explicit and idempotency-aware.

Failed cases have `answer=None`, an empty member mapping, and no grading work. They are never repaired
with an empty string, converted to a zero score, or included in a partial success envelope.
`run.complete` is true only when every selected case succeeds.

`run.to_dict()` returns a JSON-compatible snapshot of the public run identity, ordered results,
members, and failures. It excludes private benchmark references and live Python exceptions. The
MVP does not add `save`, `load`, persistence, or resume behavior.

`Fusion.run()` is synchronous and safe to call from a normal script or a notebook with an active
event loop; bounded execution is an internal concern. Phase 2C does not implement
`Fusion.evaluate()`, `Run.grade()`, or aggregation. Those arrive together in Phase 3 so
`evaluate()` never temporarily means “run only.”

## 13. Grading

`run.grade()` grades the fusion and every member by default:

```python
grades = run.grade()

grades.benchmark_id
grades.items
grades.failures
grades.complete
```

Each grade exposes:

```python
grade.case_id
grade.target       # "fusion", "panel_1", ...
grade.score        # float in [0, 1] or None
grade.metrics
grade.coverage
grade.verdicts
grade.failure
```

Failed run cases are not sent to a grader. Missing or invalid grading evidence never becomes a
zero or an `UNMET` verdict.

### 13.1 Exact choice

`sf.graders.ExactChoice()` parses the answer choice, compares it with `Case.reference`, produces
`0.0` or `1.0`, and makes no engine request.

### 13.2 Rubric

The official DRACO configuration is:

```python
sf.graders.Rubric(
    model="gemini/3.1-pro-preview",
    prompt=DRACO_JUDGE_PROMPT,
    passes=5,
    params={
        "temperature": 0.2,
        "reasoning": "low",
        "max_tokens": 4096,
    },
)
```

For official DRACO mode, one criterion and one pass produce one model expression:

```url4
(
  /gemini/3.1-pro-preview
    ?temperature=0.2
    &reasoning=low
    &max_tokens=4096
    &q=(
      <criterion_type>positive</criterion_type>
      <criterion>...</criterion>
      <query>...</query>
      <response>...</response>
    )!
    '<pinned official DRACO judge prompt>'
)
```

The judge returns its model output directly as response text:

```json
{
  "explanation": "The response contains the required fact.",
  "criterion_status": "MET"
}
```

The SDK already knows the case, target, criterion, weight, and pass and attaches that metadata
locally. A 40-criterion rubric with five passes means 200 independent judge model calls per
answer. Those calls may execute concurrently under the SDK's bounded execution policy.

The SF model adapter must preserve:

```text
URL4 context -> user message
URL4 intent  -> system message
```

It must forward the configured model parameters and ensure repeated passes are independent rather
than serving a cached completion. The current Phase 1 engine profile does not yet implement model
handlers; that is a Phase 2 application gap, not a URL4 grammar change.

## 14. Rubric scoring

After judge responses return, scoring is deterministic SDK computation. For each pass:

```text
numerator   = sum(weight for every MET criterion)
denominator = sum(all positive criterion weights)
pass score  = clamp(numerator / denominator, 0, 1)
```

Positive MET criteria add reward. Negative MET criteria subtract because their weights are
negative. Negative UNMET criteria add no penalty.

The final grade score is the mean of the configured pass scores. `pass_rate` is the unweighted
fraction handled correctly: positive+MET and negative+UNMET.

The strict MVP requires full verdict coverage for a valid rubric grade:

```text
coverage = successful verdicts / expected verdicts
score is valid only when coverage == 1.0
```

This is stricter than partial-score behavior in some executable DRACO reference paths, but it is
identical on successful publishable runs and prevents missing negative criteria from inflating a
score. Raw verdicts and failures remain inspectable.

`Grade.metrics` is narrowly defined as additional case-level scores that are valid to average:

```python
{
    "pass_rate": 0.84,
    "factual_accuracy": 0.91,
    "breadth_and_depth": 0.78,
    "presentation_quality": 0.88,
    "citation_quality": 0.72,
}
```

Arbitrary metadata, counts, cost, latency, coverage, and raw responses do not belong in
`metrics`.

## 15. Aggregation and `Report`

`sf.aggregators.Mean()` performs deterministic local aggregation and makes no engine call.

It uses the common paired case set where the fusion and every member have valid grades:

```text
fusion score = mean(fusion grades)
member score = mean(that member's grades)
baseline     = maximum member score
gain         = fusion score - baseline
coverage     = common valid cases / selected cases
```

If one member is missing a grade for a case, that case is excluded from the fusion and every
member headline score. If no common valid cases remain, `score`, `baseline`, and `gain` are
`None`.

```python
report = grades.aggregate()

report.benchmark_id
report.fusion_url4
report.n_cases
report.n_scored
report.coverage
report.score
report.baseline
report.gain
report.members
report.metrics
report.failures
report.complete
```

All SDK scores use `0.0-1.0`. Widgets render them as percentages. Gain is displayed in percentage
points:

```text
report.score == 0.80    -> 80.0%
report.baseline == 0.70 -> 70.0%
report.gain == 0.10     -> +10.0 pp
```

`Mean` averages only the explicitly meanable numeric values in `Grade.metrics`, over the same
common case set. A metric is included in `Report.metrics` only when every included fusion grade
defines it. Member summaries expose their corresponding metrics.

Standard deviations, confidence intervals, and bootstrap aggregators are deferred.

## 16. Failure behavior

The general rule is:

```text
Cannot begin or cannot trust the protocol -> raise
One case failed during valid engine execution -> record and continue
```

Preflight, engine-connection, and response-schema failures raise. A non-success engine response
for one valid case becomes a case failure carrying `case_id`, engine `code`, message, and optional
HTTP status. The SDK does not infer a failing panel unless the engine reports one.

Current URL4 errors logically use:

```json
{
  "error": {
    "code": "resolution_failed",
    "message": "<engine explanation>"
  }
}
```

Malformed judge-model output is a grading failure for that criterion/pass. A malformed rubric or
zero-criterion reference aborts grading before judge spend.

## 17. Concurrency and retries

Concurrency is execution policy, not strategy configuration. MVP defaults are internal:

- at most four benchmark cases in flight;
- at most 32 rubric-judge requests in flight;
- stable returned ordering regardless of completion order; and
- no execution-time cancellation of unrelated selected cases.

The Phase 2 run-stage retry policy is deliberately empty:

- do not retry 503, timeout, connection, upstream, URL4, or protocol failures automatically; and
- record the one observed failure at its original case position.

This avoids silently duplicating paid work and keeps Phase 2 behavior predictable. Any future
retry policy must be explicit and idempotency-aware. Rubric-judge retry behavior is reviewed with
Phase 3 rather than being implied by the run stage.

Future execution methods may accept `concurrency=...`; strategy constructors must not.

## 18. Verification boundary

Client-orchestrated results are reproducible research results, not verified official results. The
client can inspect downloaded references and can modify local computation.

A future verified workflow must execute case selection, sealed-reference handling, model calls,
grading, aggregation, and attestation inside a trusted engine-hosted workflow. It may import the
same ScreamingFace grader and aggregator implementations, but it needs an explicit server-side
contract and must not be selected implicitly because a benchmark was passed as a string.

## 19. Implementation acceptance

The first implementation is accepted when:

1. GPQA, DRACO, and an in-memory example use the same `Case` and `Benchmark` contracts.
2. `Fusion.evaluate()` equals `run -> grade -> aggregate`.
3. model IDs map mechanically to URL4 routes.
4. named benchmark loading uses the SF engine registry, manifests, and normalized case resources.
5. every selected case is one complete URL4 Fusion expression.
6. majority vote executes through the advertised SF RDS route using exact-string voting and
   stable numeric panel-order tie breaking.
7. references never appear in worker or reducer expressions.
8. official DRACO grading uses one URL4 model request per criterion/pass.
9. success bodies are parsed from text and validated strictly.
10. missing work never becomes a zero score.
11. headline comparisons use a common paired case set.
12. no runtime mock, in-process engine, direct gateway client, compatibility alias, persistence,
    budget, authentication, or ETL framework is introduced.

The next unit after this document is implementation planning and contract tests; this Phase 0
unit changes documentation and syntax fixtures only.
