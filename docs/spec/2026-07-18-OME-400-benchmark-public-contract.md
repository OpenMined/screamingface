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
sf.CaseGrades
sf.Grade
sf.CriterionVerdict
sf.GradeFailure
sf.Report
sf.MemberReport
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

The configured value must be an HTTP(S) origin: scheme and authority only, with no path, query,
or fragment. This keeps discovery resources and `/v1` evaluation on one unambiguous engine
boundary.

Importing ScreamingFace and directly constructing a `Fusion`, `Case`, or `Benchmark` perform no
network request. Model discovery, Fusion execution, and model-backed grading use the configured
HTTP engine. Named benchmark discovery is SDK-local; loading may contact the canonical dataset
source through the researcher's own credentials but never contacts the engine.

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
| `benchmarks.list/load` | none; installed SDK definition and researcher-side source access |
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
  ]
}
```

This registry contains remotely executable capabilities only. Once the engine can execute the
DRACO flow, compatible model records gain `"web_search"` in `supported_tools` and the judge model
is added. Benchmarks never appear here because their definitions, sources, graders, and
aggregators remain local to the SDK.

The registry advertises addressable engine resources, not every SDK abstraction. Benchmarks,
graders, and aggregators do not get registry entries when the ordinary client workflow executes
them locally.

Public discovery returns IDs only:

```python
sf.models.list()
sf.models.list(query="gemini", tools=["web_search"], limit=10)

sf.benchmarks.list()
sf.benchmarks.list(query="draco", tools=["web_search"], limit=10)
```

Both return `list[str]`, but their sources intentionally differ: models come from the configured
engine registry while benchmarks come from the installed SDK catalog. Filters are arguments to
`list()`; there is no separate `search()` in the MVP. The SDK does not expose internal catalog or
registry summary objects.

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

The current profile advertises no tools and therefore cannot execute DRACO. The SDK may install
the local DRACO definition independently, but evaluation preflight fails until a tested named-tool
adapter, compatible worker routes, and the `gemini/3.1-pro-preview` judge route are all published.

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

## 6. SDK-local benchmark loading

Benchmark identities such as `draco@1` and `gpqa@1` are opaque versioned strings. The MVP does
not define semantic-version ranges, `latest`, or a separate `version=` field.

```python
benchmark = sf.benchmarks.load("gpqa@1")
```

`sf.benchmarks.list()` reads a small catalog installed with the SDK. `load()` selects that local
definition, fetches its pinned canonical source through the researcher's ordinary dataset access,
validates and normalizes every row, and returns an immutable `Benchmark`. It performs no engine
registry, manifest, or case-route request and does not execute downloaded Python.

This is deliberately ordinary Python rather than a wire-level ETL or benchmark DSL. The local
definition owns the source pin and conversion to `Case`, plus its `Grader`, `Aggregator`, and
required tools. Researchers can build modified or private benchmarks directly with the same
public constructor without changing the execution stages.

The two canonical publishers are pinned as follows:

| Benchmark | Hugging Face source | Required publication invariants |
|---|---|---|
| `gpqa@1` | `Idavidrein/gpqa`, `gpqa_diamond`, `train`, revision `633f5ee89ab8ad4522a9f850766b73f62147ffdd` | 198 unique source `Record ID` values; fixed SHA-256 option permutation per record; source `High-level domain`/`Subdomain` mapped to `domain`/`subdomain` metadata |
| `draco@1` | `perplexity-ai/draco`, default config, `test`, revision `ce076749809027649ebd331bcb70f42bf720d387` | source JSONL SHA-256 `e35bfe78cd827fa1d541b79fbc7bc7b91966d3227d8742c83e99d26d4ac4679a`; 100 unique UUID cases in source order; 10 domains; four sections per case; 3,934 criteria |

The definitions validate the complete source and normalized schema before returning any cases.
They cache the resulting immutable cases once per researcher process. `first=` therefore selects a
stable source-order prefix; it never reshuffles either publication. GPQA's one deterministic
choice permutation per question is part of the `gpqa@1` identity.

Engine registry, execution, and judge bodies are read through `response.text` and then
parsed/validated by the SDK. Dataset libraries retain their native authenticated transport.

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
Fusion member routes. Reducers, model synthesizers, and graders do not inherit them.

Tool IDs are ordered, unique lowercase identifiers matching `[a-z][a-z0-9_]*`. They are a
first-class benchmark capability contract: the `tools` key is reserved from generic member,
model-reducer, and rubric-grader `params`. A future member-specific capability API must remain
first-class rather than hiding tools in arbitrary model parameters.

For `draco@1`, `web_search` names the engine-owned research capability needed to search and then
open/fetch source content. It subsumes the benchmark pipeline's separate `web_search` and
`web_fetch` tools at the public SDK boundary. The engine translates that capability through a
tested provider-specific adapter; it does not forward the string as an arbitrary Gateway or
provider field. Benchmark rubrics, sealed references, and result sources must be inaccessible to
that adapter.

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
- repeated models remain distinct ordered execution slots (`member_1`, `member_2`, ...);
- model parameters become query parameters on that model route;
- reducers are explicit strategy objects; and
- a DRACO reproduction pins its research-answer prompt in the Fusion.

`member_n` is the canonical machine-facing slot identity across the URL4 recipe, engine result,
`Run`, `Grades`, and `Report`. “Panel” remains descriptive research language for the members
answering together; it is not a second identifier namespace.

`reducers.Model` uses the same conceptual `model`, `prompt`, and `params` fields as a configured
member. `reducers.MajorityVote()` performs deterministic exact-string voting and breaks ties by
stable member order.

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

- context is a JSON object with exactly contiguous `member_1` through `member_n` keys, where
  `n >= 2`;
- each value is a non-blank string;
- object insertion order is irrelevant because stable order is the numeric `member_n` order;
- votes use exact raw-string equality, so `A`, `a`, and `A\n` are distinct answers;
- an exact tie selects the lowest numeric member position;
- intent and query parameters are rejected; and
- malformed input raises a permanent URL4 `malformed_source` error, invalidating the whole
  expression rather than returning a partial Fusion object.

The route's successful body is the winning answer's raw text. URL4 substitutes that resolved text
into the outer expression's final `screamingface.fusion-result.v1` structure; the reducer does not
return a result envelope or a rewritten URL4 expression.

This route is legitimate SF execution behavior. It is distinct from adding an SF-specific output
packager merely to reshape JSON.

## 10. One URL4 request per case

`fusion.url4` is the canonical, shareable URL4 recipe template. It contains stable `member_n`
slots and an intentionally unbound `$question`, but no benchmark case or answer key. The compiler
constructs this template with URL4's public builder/AST facade and renders it with URL4's
certified renderer; it does not concatenate ad-hoc URL4 strings. `run.fusion_url4` preserves this
same template.

For execution, the SDK adds one literal `question` binding to the template. Dollar signs in case
input are escaped as URL4 literal data; dollar references in researcher-authored prompt templates
remain active. It also adds the selected Benchmark's tools only to each answer-producing member.
One capability renders as `tools=web_search`; ordered multiple capabilities render through the
standard query representation `tools=web_search+code_execution` and arrive decoded at the node as
one space-separated scalar. The resulting concrete expression is still one request. Neither the
benchmark-independent stored recipe nor any reducer or judge call inherits this execution overlay.

One selected case produces one complete URL4 expression containing the question binding, panel
fan-out, reducer, and final result structure. Conceptually:

```url4
(
  question='<resolved case input>',

  member_1=/codex/gpt-5.5?tools=web_search&q=($question)!'Answer the question',
  member_2=/gemini/2.5?tools=web_search&q=($question)!'Answer the question',

  member_answers={
    member_1: '$member_1',
    member_2: '$member_2'
  },

  fusion_answer=/reducers/majority-vote($member_answers),

  {
    schema: 'screamingface.fusion-result.v1',
    members: {
      member_1: {
        model: 'codex/gpt-5.5',
        answer: '$member_1'
      },
      member_2: {
        model: 'gemini/2.5',
        answer: '$member_2'
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
    "member_1": {
      "model": "codex/gpt-5.5",
      "answer": "<response>"
    },
    "member_2": {
      "model": "gemini/2.5",
      "answer": "<response>"
    }
  },
  "answer": "<reduced fusion response>"
}
```

The `member_n` object keys are the member/call-slot IDs, so an inner `id` field would be redundant.

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
member/final answers. It reconstructs member order from the expected numeric member slots rather
than trusting JSON object insertion order. It preserves accepted answer text exactly and never
guesses or repairs an invalid engine result.

A model reducer compiles to another ordinary model route. Its context contains the resolved
question and labeled panel answers in the stable format defined in §8; its intent is
`reducers.Model.prompt`, and its declared model parameters become route query parameters. The
final response structure is identical for model and deterministic reducers.

## 11. Preflight

Before any answer or judge call, evaluation:

1. resolves a named benchmark from the installed SDK catalog when needed;
2. loads and validates the selected canonical cases through the caller's dataset access;
3. validates every selected reference;
4. fetches and validates `/.well-known/screamingface`;
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
run.fusion_name
run.fusion_url4
run.members
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
result.members["member_1"].model
result.members["member_1"].answer
result.answer
result.failure
```

`result.members` is an immutable mapping keyed by the `member_n` call-slot ID. The key is the ID, so
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

The `Run` privately captures the exact selected `Case` values used for execution. `run.grade()`
uses that snapshot rather than rematerializing a callable benchmark source, so a mutable loader
cannot change references between execution and grading.

`Fusion.run()` is synchronous and safe to call from a normal script or a notebook with an active
event loop; bounded execution is an internal concern. Grading, aggregation, and `evaluate()` are
the separate Phase 3 stages defined below; `evaluate()` never means “run only.”

## 13. Grading

`run.grade()` grades the fusion and every member by default:

```python
grades = run.grade()

grades.benchmark_id
grades.fusion_name
grades.fusion_url4
grades.members
grades.grader
grades.case_ids
grades.results
grades.failures
grades.complete
grades.to_dict()
```

`grades.results` is a stable tuple in selected-case order. Each entry separates the Fusion grade
from the grades for its ordered member slots:

```python
case = grades.results[0]

case.case_id
case.fusion             # sf.Grade | None
case.members            # Mapping[str, sf.Grade]
case.run_failure        # sf.RunFailure | None

grade = case.fusion
grade.score             # float in [0, 1] | None
grade.metrics
grade.coverage
grade.verdicts
grade.failure           # sf.GradeFailure | None
grade.valid
```

The public inspection types are `sf.Grades`, `sf.CaseGrades`, `sf.Grade`,
`sf.CriterionVerdict`, and `sf.GradeFailure`. They are immutable. Their mappings and tuples are
immutable and preserve stable case, member, criterion, and pass ordering. `to_dict()` returns a
JSON-compatible snapshot.

A successful run case always contains a Fusion `Grade` and one `Grade` for every captured member,
including invalid grades whose `score` is `None`. A failed run case has `fusion=None`, an empty
member mapping, and its original `RunFailure`; it receives no grading work. `Grades.complete` is
true only when every selected run case succeeded and every Fusion/member grade is valid.

There is no public `targets=` option in the MVP. Grading every member is required for the paired
comparison contract in §15. Grading uses the already-captured answers and never reruns a panel or
reducer model.

### 13.1 Exact choice

`sf.graders.ExactChoice()` ports the proven MCQ answer-normalization behavior from the DRACO/GPQA
benchmark harness into ScreamingFace; the SDK does not depend on that repository at runtime. It:

- supports choice labels `A` through `J`, case-insensitively;
- accepts common punctuation, wrappers, and Markdown;
- recognizes explicit `answer`, `final answer`, `choice`, and `option` markers;
- uses the last explicit conclusion when a response contains multiple candidates;
- avoids false matches from the article `a`, the pronoun `I`, and text such as `E. coli`;
- accepts numeric-string reference indices `"0"` through `"9"`; and
- falls back to normalized full-text equality when neither side is a choice label.

A literal integer reference is rejected rather than silently guessing whether it is zero- or
one-based; benchmark publishers normalize references to strings. A non-blank but unparseable
model response is a valid incorrect answer, not a protocol failure. An exact grade therefore has
`score` equal to `0.0` or `1.0`, `coverage=1.0`, empty `metrics`, empty `verdicts`,
`failure=None`, and `valid=True`. A non-string, blank, or otherwise unusable reference is malformed
benchmark data and raises during preflight before model or judge spend.

Exact-choice grading is deterministic local computation and makes no engine request.

### 13.2 Rubric

The `draco@1` benchmark-pipeline configuration is:

```python
sf.graders.Rubric(
    model="gemini/3.1-pro-preview",
    prompt=DRACO_JUDGE_PROMPT,
    passes=3,
    params={
        "temperature": 0.2,
        "reasoning": "low",
        "max_tokens": 4096,
    },
)
```

For `draco@1`, one criterion and one pass produce one model expression:

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
    '<official DRACO Appendix C.5 per-criterion judge prompt>'
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
locally. A 40-criterion rubric with three passes means 120 independent judge model calls per
answer. Because the Fusion and all three members are graded, a three-member DRACO case ordinarily
means 480 judge calls. Those calls may execute concurrently under the SDK's bounded execution
policy.

The system prompt is the official per-criterion text identified as Appendix C.5 by the executable
pipeline and open-source harness. Its pinned UTF-8 bytes are 5,196 bytes with SHA-256
`dbc1ae32e32be6fbc47180b4a246b997d299bb0e25373a8cde87c6461cb2397b`. `draco@1`
deliberately matches the executable benchmark/OpenRouter pipeline's three-pass protocol while
using the public `gemini/3.1-pro-preview` engine identity. The paper's five-pass Gemini 3 run is a
different publication claim; this contract must not describe the pipeline-aligned profile as
byte-for-byte paper reproduction.

The SF model adapter must preserve:

```text
URL4 context -> user message
URL4 intent  -> system message
```

It must forward the configured model parameters and ensure repeated passes are independent rather
than serving a cached completion. The AI Gateway response cache is opt-in, and the engine must not
enable it for judge requests.

Each criterion/pass is an ordinary call to the advertised judge-model route through
`GET /v1?q=<expression>`. There is no separate grader HTTP route. The URL4 model context is the
judge user text containing `<criterion_type>`, `<criterion>`, conditional `<query>`, and
`<response>` blocks; the route intent is the pinned judge system prompt. Criterion weights are
not shown to the judge. Only the positive/negative criterion type is shown.

Every configured pass sends byte-identical context, intent, and parameters. No random salt,
pass marker, or hidden prompt mutation is added. Independence is provided by the model sampling
configuration (`temperature=0.2` for `draco@1`) and by disabling response caching.

The SDK accepts a JSON object with exactly the judge fields `explanation` and
`criterion_status`, where the status is `MET` or `UNMET`. It may remove a Markdown code fence or
short preamble by extracting the first JSON object, then validates the exact schema. On invalid
judge output only, it retries the same byte-identical request up to two times, for three attempts
total. It does not retry connection, timeout, HTTP, URL4, or engine-protocol failures. After three
malformed outputs, that criterion/pass remains unresolved.

## 14. Rubric scoring

Before any judge request, the SDK validates every selected rubric reference together, including
references for cases whose captured run failed. Every rubric must have at least one section;
every section must have at least one criterion and one positive-weight criterion. Section
identities must be non-blank, stable, and unique after conversion to metric keys, and must not
collide with the reserved `pass_rate` metric. Criterion IDs must be globally unique and non-blank;
requirements must be non-blank; and weights must be finite, non-zero numeric values. Any malformed
selected rubric aborts the whole grading stage before judge spend.

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
score. For example, 119 successful verdicts out of 120 produces `coverage=119/120`, `score=None`,
and an `incomplete_verdicts` summary failure. Missing work is never converted to `UNMET`, and the
SDK does not publish a diagnostic partial score in the MVP. Successful verdicts, explanations,
and raw responses remain inspectable.

Each verdict exposes:

```python
verdict.criterion_id
verdict.section
verdict.requirement
verdict.weight
verdict.pass_number       # one-based
verdict.status            # "MET" | "UNMET" | None
verdict.explanation
verdict.raw_response
verdict.failure           # sf.GradeFailure | None
```

One failed criterion does not cancel unrelated criterion, pass, target, or case work. A target
with any unresolved verdict retains all successful evidence but has `valid=False` and
`score=None`.

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

Section metric keys are derived deterministically from section identities by lowercasing and
replacing non-alphanumeric runs with underscores. A collision after normalization is malformed
rubric data rather than an invitation to rename metrics silently.

Rubric scores are continuous. The SDK does not impose an `is_correct` field, pass threshold, or
binary interpretation.

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
report.fusion_name
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
report.to_dict()

member = report.members["member_1"]
member.model
member.score
member.metrics
```

`sf.Report` and `sf.MemberReport` are immutable values. Repeated uses of the same model remain
distinct `member_n` member reports. If multiple members tie for the best score, `baseline` is still
that numeric maximum; no public tie-breaker is needed.

`fusion_name` and the ordered `member_n -> model ID` mapping persist from `Fusion` through `Run`,
`Grades`, and `Report`, including when every selected case fails. Successful case results must
contain exactly those slots and models; failed cases remain atomic with no partial answers.

All SDK scores use `0.0-1.0`. Widgets render them as percentages. Gain is displayed in percentage
points:

```text
report.score == 0.80    -> 80.0%
report.baseline == 0.70 -> 70.0%
report.gain == 0.10     -> +10.0 pp
```

`Mean` averages only the explicitly meanable numeric values in `Grade.metrics`, over the same
common case set. A metric is included in `Report.metrics` only when every included fusion grade
defines it. Member summaries expose their corresponding metrics, also only when every paired
grade for that member defines the value. Exact-choice reports have empty metrics because their
headline score is already accuracy.

`report.failures` preserves the run and grading failures that explain excluded work. A report may
contain a valid partial paired comparison while `complete=False`; completeness describes all
selected work, not merely whether at least one pair was scorable. If no paired case remains,
`score`, `baseline`, `gain`, and every member score are `None`.

Standard deviations, confidence intervals, and bootstrap aggregators are deferred.

## 16. Failure behavior

The general rule is:

```text
Cannot safely begin -> raise
Individual work failed after valid execution began -> record and continue
```

Malformed benchmark/rubric configuration, unsupported grader or aggregator strategies,
unknown/unadvertised judge models, or inability to complete engine preflight raise before judge
spend. The SDK validates the generic URL4 parameter representation; the configured engine owns
model-specific parameter compatibility and must reject invalid parameters before contacting AI
Gateway. Once valid grading work begins, an individual target failure is recorded and unrelated
work continues.

A grading failure exposes:

```python
failure.case_id
failure.target
failure.kind
failure.message
failure.criterion_id   # str | None
failure.pass_number    # int | None
failure.status         # int | None
failure.code           # str | None
```

The grading failure kinds are `connection`, `timeout`, `http`, `url4`, `protocol`,
`invalid_judge_output`, and `incomplete_verdicts`. Detailed criterion failures attach to their
`CriterionVerdict`; the target also receives one `incomplete_verdicts` summary failure.
`grades.failures` exposes run and grading failures in stable case/target order. Failure messages
are safe strings and never retain credentials, provider bodies, arbitrary exception objects, or
mutable state.

A non-success engine response for one valid case becomes a case failure carrying `case_id`,
engine `code`, message, and optional HTTP status. The SDK does not infer a failing panel unless
the engine reports one.

Current URL4 errors logically use:

```json
{
  "error": {
    "code": "resolution_failed",
    "message": "<engine explanation>"
  }
}
```

Malformed judge-model output is a grading failure for that criterion/pass after the validation
retry allowance is exhausted. A malformed rubric reference aborts the complete grading stage
before judge spend. An exact-choice response that is merely wrong or unparseable remains a valid
`0.0` grade rather than a failure.

## 17. Concurrency and retries

Concurrency is execution policy, not strategy configuration. MVP defaults are internal:

- at most four benchmark cases in flight;
- at most 16 rubric-judge requests in flight under the current SDK and engine admission policy;
- stable returned ordering regardless of completion order; and
- no execution-time cancellation of unrelated selected cases.

The Phase 2 run-stage retry policy is deliberately empty:

- do not retry 503, timeout, connection, upstream, URL4, or protocol failures automatically; and
- record the one observed failure at its original case position.

Rubric grading follows the same no-transport-retry rule. Its only SDK retry is up to two
byte-identical repeat requests after a successful model response whose judge output fails schema
validation. This avoids silently duplicating paid work after ambiguous transport failures while
allowing a model two opportunities to repair malformed structured output.

Future execution methods may accept `concurrency=...`; strategy constructors must not.

## 17.1 `Fusion.evaluate()`

`evaluate` is the standard public name because the operation executes a benchmark and returns its
comparison report. It is exactly this facade:

```python
def evaluate(
    self,
    benchmark: str | Benchmark,
    *,
    first: int | None = None,
) -> Report:
    return self.run(benchmark, first=first).grade().aggregate()
```

It is synchronous and notebook-safe like `run()`. It accepts only the benchmark and `first` in
the MVP. The benchmark owns its grader and aggregator; there are no facade parameters for a
grader, aggregator, seed, budget, retry policy, or concurrency, and there is no top-level
`sf.evaluate` function.

Passing an ID does not select a different execution mode. `sf.benchmarks.load("draco@1")` selects
the installed definition, fetches its pinned source through the caller's dataset access, and
builds an in-memory `Benchmark`. Consequently `fusion.evaluate("draco@1")` means load, run, grade,
and aggregate. Passing an existing `Benchmark` skips only the named-benchmark loading step. Panel,
reducer, and rubric-judge model calls still go through the configured URL4 engine; only exact
grading and mean aggregation are local deterministic computations.

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
4. named benchmark loading uses installed SDK definitions and the researcher's dataset access,
   without an engine benchmark endpoint.
5. GPQA and DRACO match their pinned source revisions, counts, identities, order, and normalized
   schemas.
6. every selected case is one complete URL4 Fusion expression.
7. majority vote executes through the advertised SF RDS route using exact-string voting and
   stable numeric member-order tie breaking.
8. references never appear in worker, reducer, tool, or judge-visible source material beyond the
   individual criterion being judged.
9. benchmark tools are compiled only onto answer-producing member routes; reducers, synthesizers,
   and judges do not inherit them.
10. `web_search` demonstrably searches and opens/fetches source content through an allowlisted
    engine adapter.
11. `draco@1` grading uses one URL4 model request per criterion/pass with the pinned three-pass
   official per-criterion configuration.
12. success bodies are parsed from text and validated strictly.
13. missing work never becomes a zero score.
14. headline comparisons use a common paired case set.
15. DRACO appears in the SDK catalog only when its canonical local definition is complete; its
    evaluation preflight fails until the judge and a compatible web-search Fusion are runnable
    through the real engine-to-Gateway path.
16. no runtime mock, in-process engine, direct gateway client, compatibility alias, persistence,
    budget, authentication, or ETL framework is introduced.

The grading and aggregation behavior in §§13–17 was approved as Phase 3A and implemented through
Phase 3D: public grading values, deterministic ExactChoice, complete `Run.grade()` Rubric
orchestration, strict judge parsing, validation-only retries, retained evidence, paired Mean
aggregation, immutable reports, and the exact `Fusion.evaluate()` facade. The current engine
profile cannot execute DRACO. Phase 4A implemented the canonical pinned SDK-local GPQA definition
on 2026-07-19. Phase 4B added the canonical SDK-local DRACO definition and catalog exposure on
2026-07-19. Phase 4C added member-only benchmark-tool compilation and reserved capability
validation on 2026-07-19. The remaining Phase 4 engine slices must add
`gemini/3.1-pro-preview` and working `web_search` capabilities.
