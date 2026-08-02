---
title: Link Benchmark and Candidate URL4 expressions
ticket: OME-605
status: approved
date: 2026-08-01
approved: 2026-08-01
---

# Link Benchmark and Candidate URL4 expressions

## Outcome

Replace the SDK's DRACO-shaped compiler and the Candidate-specific Engine planning request with one
Candidate-independent Benchmark GET. The response represents the Benchmark under
`screamingface.benchmark.v1` and includes a canonical, linkable URL4 expression in `url4`. The SDK
compiles each Model or Fusion into a Candidate expression and structurally links the two into one
complete URL4 per Candidate. That URL4 executes through the existing GET lifecycle.

The public Candidate interface stays small: `Model` may override its prompt and generation
parameters, while `Fusion` may additionally override its synthesizer. Defaults are owned and
versioned by the SDK. Benchmark implementations retain immutable invocation, Grading, and
Aggregation policy.

The contract must describe every executable benchmark on
`screamingface-benchmarks@23524fdb60de5a56c7618339cc0423303997f529`: DRACO, HealthBench,
MedXpert, and SciCode. A deployment may publish only installed implementations, but it must never
claim a capability it cannot express and execute.

## Architecture

### Client-owned Candidate expression

- `Model(model, prompt=None, params=None)` resolves answer policy from Candidate override, then a
  versioned SDK default where the Benchmark protocol allows it.
- `Fusion(members, synthesizer=None, prompt=None, params=None)` needs no synthesizer argument; it
  resolves Candidate override, then the versioned SDK default.
- Resolution never substitutes a different available model. An unavailable resolved model is a
  pre-execution compatibility failure.
- Resolved model routes, prompts, and parameters are present in the linked URL4 and Report so an
  Evaluation is reproducible.
- The compiled expression accepts `$input` and returns one answer. It contains no Benchmark route,
  Case, Judge, Grading, or Aggregation knowledge.

### Engine-owned Benchmark expression

- One Benchmark GET contains identity, selected and total Case counts, metric metadata, required
  models and capabilities, and a canonical URL4 expression in `url4`.
- The Engine owns Case shape and selection, Candidate Invocation order, structured state, hidden
  references, Judges, Grading, and Aggregation.
- The expression is independent of a particular Candidate and refers to one external
  `$candidate` binding wherever the Benchmark requires an answer.
- The SDK does not interpret benchmark-specific data, rubric, or grader routes.
- Benchmark authors generate typed URL4 nodes in Engine-side Python. They do not author a Client
  workflow schema, action list, or URL4 string template.

### Candidate Invocation

- `/candidate(input)!$candidate` is the Engine's universal Candidate Invocation interface.
- The route evaluates the supplied Candidate expression in-process with `$input` bound to the
  invocation input and returns its answer.
- It runs against the same URL4 node, routes, credentials, capabilities, cancellation, and
  accounting context. It does not make another SDK or control-plane request.
- A Benchmark invokes the same Candidate one or multiple ordered times. SciCode threads
  earlier Candidate output into later invocation input; DRACO invokes it once per Case.
- The adapter enforces recursion depth and total Candidate Invocation limits.
- Plain-text inputs cross the boundary unchanged. Native multi-turn inputs use the versioned
  `screamingface.candidate-input.v1` chat envelope emitted by the Engine-side
  `chat_input(messages)` helper. The Runner validates and replays those roles; the SDK neither
  parses the envelope nor knows which Benchmark needs it.

### Structural linking

- The SDK parses and validates both expressions with URL4's AST before any paid execution.
- It binds the Candidate expression once as inert text named `candidate`, nests the Benchmark
  expression in that scope, and canonically renders the linked tree.
- If the Benchmark root is an `Iteration`, the SDK first wraps it in an instrumental
  `benchmark_result` passthrough. This disambiguates URL4's reduce-over-iteration surface grammar;
  it does not change execution semantics.
- Linking never uses URL4 string replacement and contains no Benchmark-specific branches.
- “Complete URL4” means the linked expression contains both complete inputs and needs no later
  compilation or definition fetch. It does not mean duplicating an identical Candidate graph at
  every invocation site.

### Protocol families

| Benchmark | Candidate protocol | Grading protocol | Runtime requirements |
| --- | --- | --- | --- |
| DRACO | single-turn prose, optional web tools | repeated per-criterion LLM rubric | hidden weighted rubric |
| HealthBench | native chat, optional repeated answer samples | one LLM call per rubric item | structured messages and metadata slices |
| MedXpert | two-turn chain-of-thought and letter commit | deterministic exact match | structured reasoning and commit artifacts |
| SciCode | stateful sequential sub-step calls | sandboxed code execution per step | Candidate re-entry, private fixtures, strict problem aggregate |
| IFEval | single-turn instruction-constrained answer | programmatic per-instruction Python checks | pinned verifier code and offline NLTK data |

SciCode establishes the required seam: a Benchmark must be able to invoke the supplied Candidate
more than once while carrying structured state. A fixed `Cases -> one answer -> grade -> mean`
compiler is not a universal Benchmark implementation.

## Benchmark resource contract

`GET /v1/benchmarks/{id}?limit=N` returns JSON. The schema names the represented domain resource,
not its executable field; therefore it remains `screamingface.benchmark.v1`, not
`screamingface.benchmark-program.v1`:

```json
{
  "schema": "screamingface.benchmark.v1",
  "object": "benchmark",
  "id": "draco-lite",
  "title": "DRACO Lite",
  "description": "Research-quality rubric evaluation.",
  "case_count": 1,
  "total_case_count": 100,
  "metrics": {
    "primary": "normalized_score",
    "direction": "maximize"
  },
  "required_models": ["openrouter/google/gemini-3.1-pro-preview"],
  "capabilities": {
    "candidate": ["web_search", "web_fetch"],
    "runtime": []
  },
  "candidate_invocations": 1,
  "url4": "/draco/cases*(...)"
}
```

`url4` is the canonical Candidate-independent Benchmark expression, not a template language.
`limit` selects Cases before the expression is returned, so the response remains reusable for
every Candidate in the same Evaluation. The response has an ETag over its exact representation.
Unknown schema versions, malformed expressions, unavailable fixed models, or unavailable runtime
capabilities fail before any paid Candidate Invocation.

`candidate_invocations` is an exact no-spend fact supplied by the author. The resource does not
publish generic `operation_counts`: Case data may determine rubric cardinality, Tool calls and
retries are dynamic, and estimates presented as exact counts are worse than omitting them. Runtime
usage and occurrences come from execution telemetry.

The previous YAML “manifest,” `protocol`, and `plan` endpoint are removed. Protocol-family names
were an SDK dispatch mechanism; the URL4 expression now carries the behavior directly.

## Benchmark authoring

- An installed Benchmark adapter owns its data preparation, hidden materials, fixed prompts,
  Judges, deterministic functions, and URL4 construction.
- Its small external interface is metadata plus `build(selection) -> url4.Node`. Registration is
  explicit; no decorator or naming convention performs hidden discovery.
- Internal Python is unrestricted: unique Benchmarks may inspect prepared data and generate
  explicit ordered dependencies without expanding the Client interface.
- The adapter uses one ScreamingFace-specific builder, `candidate(input)`, rather than knowing
  Model or Fusion topology. Loading, calls, iteration, and references use URL4's existing typed
  builders, not a new Benchmark DSL.
- `chat_input(messages)` is the only additional transport helper. It preserves native chat turns
  for Benchmarks such as HealthBench and MedXpert while still presenting one opaque `$input` to
  every Candidate.
- Private grading material remains behind Engine routes or private files and is never embedded in
  the public Benchmark response when doing so would invalidate the Benchmark.

The implemented author-facing interface is:

```python
DRACO_LITE = Benchmark(
    id="draco-lite",
    title="DRACO Lite",
    description="Research-quality rubric evaluation.",
    case_count=100,
    primary_metric="normalized_score",
    score_direction="maximize",
    required_models=(JUDGE_MODEL,),
    candidate_capabilities=("web_search", "web_fetch"),
    runtime_capabilities=(),
    build=build_draco,
)


def build_draco(case_count: int) -> BenchmarkExpression:
    node = iterate(
        "/draco/cases",
        body=(
            src("$item.input", name="question", weight=0.0),
            src(candidate("$question"), name="answer", weight=0.0),
            # DRACO-owned criteria and fixed Judge nodes follow.
        ),
        # DRACO-owned grading and Aggregation follow.
    )
    return BenchmarkExpression(
        node=node,
        candidate_invocations=case_count,
    )
```

DRACO uses `candidate("$question")` once per Case and then builds its fixed Judge and Aggregation
nodes. SciCode uses an ordinary Python loop over the selected problems and sub-steps to generate
ordered prompt, Candidate Invocation, extraction, sandbox, and grade nodes. That loop runs while
serving the Benchmark GET; the resulting `url4` value is a fixed expression and the SDK sees no
SciCode-specific schema.

For native chat, authors pass ordinary Python messages or a runtime JSON reference through the
same helper:

```python
candidate(
    chat_input(
        [
            {"role": "user", "content": "$question"},
            {"role": "assistant", "content": "$reasoning"},
            {"role": "user", "content": "Return only the answer letter."},
        ]
    )
)
```

IFEval needs no new Client concept: its expression invokes the Candidate once per prompt, calls
an Engine-owned programmatic verifier with that Case's instruction IDs and kwargs, and aggregates
prompt/instruction accuracy under strict and loose readings. Its fixed verifier dependencies are
part of the Benchmark Runner image, not Python Client dependencies. Reproducibility must preserve
the official verifier's known randomized non-ASCII preprocessing rather than silently correcting
it and changing comparability.

## Acceptance

- One Benchmark GET supplies everything needed to link every Candidate in an Evaluation; no
  Candidate-specific POST occurs.
- The SDK Benchmark decoder has no DRACO-specific route, rubric, Judge, synthesis, or Aggregation
  fields and does not dispatch on protocol families.
- SDK defaults and Candidate overrides have deterministic precedence and validation.
- Sync and async Clients use the same fetch, compile, and structural-link implementation.
- The linked result round-trips through `url4.build` and `url4.render` and contains no unresolved
  bindings other than values intentionally resolved at execution.
- `/candidate` executes both Model and nested Fusion expressions, supports two ordered invocations,
  and preserves cancellation, usage, and typed failure attribution.
- HealthBench-style histories preserve native roles, and MedXpert-style second turns replay the
  first Candidate answer as an assistant message before the final commit request.
- SciCode threads extracted code through ordered Candidate Invocations and validates sandbox
  requirements before execution.
- Full DRACO and SciCode expressions stay within the deployed encoded-GET limit, or the design is
  revisited before release.
- DRACO's live vertical slice remains executable.
- Ruff, format, Pyright, package tests, URL4 Cloud tests, distribution checks, and relevant live
  end-to-end tests pass without overwriting user-edited notebooks.
