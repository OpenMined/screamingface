---
title: ScreamingFace URL4-native quickstart SDK
ticket: OME-400
status: approved
date: 2026-07-15
updated: 2026-07-17
---

# ScreamingFace URL4-native quickstart SDK

## 1. Purpose and current status

OME-400 provides an importable Python SDK for composing model fusions as URL4, running them on
registered benchmarks, and comparing the fused answer with the same individual model answers.

This revision records the implemented contract after the owner-directed URL4-engine pivot. It
supersedes the earlier OME-400 draft in this file that described `sf.setup()`, provider-auth
widgets, and direct SDK → AI Gateway completion calls. Those surfaces are not part of the current
package.

The current invariant is:

> ScreamingFace sends complete URL4 expressions only to a URL4 engine. It never calls AI Gateway
> or a model provider directly.

The zero-configuration experience is runnable because the default engine is a real in-process
`Url4Node` whose registered model-route handlers return deterministic local responses. URL4 still
parses and executes the graph. Only the provider-backed behavior of the leaf routes is replaced.

## 2. User story

```python
import screamingface as sf

fusion = sf.Fusion(
    "frontier-trio",
    models=[
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-6",
    ],
    reducer=sf.MajorityVote(tie_breaker="codex/gpt-5.5"),
)

fusion.url4
run = fusion.evaluate("gpqa", first=20, seed=0)
run.score, run.baseline, run.gain
```

No setup call or background process is required for this example. The deterministic score is an
orchestration demonstration and must not be presented as provider-quality benchmark evidence.

An HTTP engine is an explicit replacement:

```python
sf.config("http://127.0.0.1:4404")
```

If that engine is unavailable, the SDK raises `EngineUnavailable`; it never silently falls back to
the in-process deterministic engine.

## 3. Architecture and ownership

```text
Notebook / script
        |
        v
ScreamingFace Fusion + benchmark layer
        |
        | one concrete URL4 expression per benchmark case
        +-------------------------------+
        |                               |
        v                               v
default in-process Url4Node       explicit HTTP URL4 engine
deterministic model routes        GET /v1?q=<expression>
        |                               |
        +---------------+---------------+
                        v
                URL4 result envelope
                        |
                        v
             reduction / grading / Run

Production leaf boundary only:
URL4 model route -> AI Gateway -> provider
```

### ScreamingFace owns

- model-call and reducer configuration;
- compilation with public URL4 builders and rendering;
- benchmark loading and normalized evaluation cases;
- deterministic local reducers;
- benchmark graders, including URL4-routed model judging;
- score, baseline, gain, metrics, failure, and provenance aggregation;
- the default deterministic route handlers used by examples; and
- the engine client port and strict HTTP adapter.

### URL4 owns

- grammar, AST, canonical rendering, and parsing;
- binding and dependency resolution;
- graph scheduling and route dispatch;
- evaluated struct construction;
- `Url4Node.evaluate()` and `GET /v1?q=<expression>` semantics; and
- production route adapters, including any adapter that calls AI Gateway.

### AI Gateway owns

- provider credentials and authentication;
- provider-specific inference, retries, and normalization; and
- whatever stable completion contract a production URL4 leaf adapter uses.

ScreamingFace has no gateway URL, token, credential, provider adapter, or direct gateway client.

## 4. Configuration: engine and data are independent

```python
sf.config(
    engine: str | None = None,
    *,
    mode: Literal["live", "mock"] = "mock",
    static_widgets: bool = False,
    engine_client: EnginePort | None = None,
) -> Session
```

The two selection axes must never be conflated:

| Configuration | URL4 execution | Benchmark data |
|---|---|---|
| no configuration | in-process deterministic node | bundled fixture |
| `sf.config(mode="live")` | in-process deterministic node | live dataset |
| `sf.config("http://127.0.0.1:4404")` | strict HTTP URL4 engine | bundled fixture |
| `sf.config("https://url4.example", mode="live")` | strict HTTP URL4 engine | live dataset |

`SCREAMINGFACE_ENGINE_URL` may supply the engine URL. `engine="mock"` explicitly selects the
in-process deterministic node. Other engine strings must be HTTP(S) URLs.

`Fusion.evaluate()` lazily creates the default Session. `sf.config()` is optional. Replacing,
resetting, or shutting down a session closes the previous process-local state. `run.engine`
records engine provenance; `run.mode` records dataset provenance.

Authentication and hosted-engine discovery are deferred until the relevant engine owner defines
those contracts. They must not be invented in the SDK first.

## 5. Model catalog and call configuration

`sf.models.list(max_price=None)` returns the currently listed SDK model IDs. The catalog maps each
public ID to one URL4 route. It is intentionally small until engine-owned discovery exists.

The current panel routes are:

| Model ID | URL4 route |
|---|---|
| `codex/gpt-5.5` | `/codex/gpt-5.5` |
| `gemini-cli/gemini-2.5-pro` | `/gemini/2.5` |
| `anthropic/claude-sonnet-4-6` | `/claude/sonnet-4.6` |

The unlisted `google/gemini-3.1-pro-preview` maps to `/gemini/3.1-pro-preview` for the DRACO judge.

A model string is shorthand for `{"model": model_id}`. A strict `ModelConfig` may additionally
set:

- `name`: stable call-slot identity, required to distinguish repeated calls to one model;
- `prompt`: per-call prompt override; and
- `params`: URL4 request parameters containing strings, finite numbers, or booleans.

Unknown model fields fail at construction. Fusion-level `prompt` is the panel default and the
per-model prompt overrides it. The default prompt is `$question`.

## 6. Fusion and reducer contract

```python
sf.Fusion(
    name: str,
    models: Sequence[str | ModelConfig],
    reducer: Reducer | None = None,
    *,
    prompt: str = "$question",
    tools: Sequence[str] = (),
)
```

Invariants:

- names and prompts are non-empty;
- at least two panel calls are required;
- model IDs must exist in the SDK route catalog;
- configured call-slot names are unique;
- tools are explicit, non-empty capability names and are attached to every panel call;
- construction performs no network or model execution; and
- `url4` is canonical, credential-free URL4 source text.

`Fusion.from_yaml(path)` uses safe YAML parsing and validates the same contract. Portable YAML uses
a strict `reducer: {kind: ...}` mapping.

### Reducers

`Reducer` is the public mechanism category.

- `MajorityVote(tie_breaker=None)` executes locally after URL4 returns panel answers. A tie breaker
  selects an existing member answer and never creates another model call.
- `ModelReducer(model=..., prompt=..., params=...)` adds a reducer model call to the URL4 graph.
  `$panel_answers` contains labeled call-slot IDs, model IDs, and resolved answers.

Synthesis, selection, ranking, merging, and adjudication are prompt behaviors of `ModelReducer`,
not separate classes with identical constructor fields.

Multi-round debate, critique/revision loops, stacked fusions, and arbitrary local callbacks are
future orchestration features. They must preserve the distinction between orchestration order and
final reduction.

## 7. URL4 recipe, request, and response contract

### Shareable recipe

`fusion.url4` keeps `$question` unresolved:

```url4
(
  panel_1=/codex/gpt-5.5()!'$question',
  panel_2=/gemini/2.5()!'$question',
  {
    schema: 'screamingface.panel-result.v2',
    panel_1_id: 'codex/gpt-5.5',
    panel_1_model: 'codex/gpt-5.5',
    panel_1_answer: '$panel_1',
    panel_2_id: 'gemini-cli/gemini-2.5-pro',
    panel_2_model: 'gemini-cli/gemini-2.5-pro',
    panel_2_answer: '$panel_2'
  }
)
```

This is URL4 source text. It need not begin with `http://`, `https://`, or `url4://` to be a URL4
expression.

### Concrete request

For each case, `Fusion.request_for(prompt)` adds a `question='...'` binding. The in-process engine
evaluates that string directly. The HTTP adapter sends exactly one transactional request:

```http
GET /v1?q=<percent-encoded-concrete-expression>
```

The SDK never calls `/claude/...`, `/gemini/...`, or `/codex/...` directly over HTTP. Those are
relative nodes inside the expression and are dispatched by URL4.

### Panel result

```json
{
  "schema": "screamingface.panel-result.v2",
  "panel_1_id": "codex/gpt-5.5",
  "panel_1_model": "codex/gpt-5.5",
  "panel_1_answer": "A",
  "panel_2_id": "gemini-cli/gemini-2.5-pro",
  "panel_2_model": "gemini-cli/gemini-2.5-pro",
  "panel_2_answer": "B"
}
```

### Model-reducer result

`screamingface.fusion-result.v2` retains every panel field and adds:

```json
{
  "reducer": "model",
  "reducer_model": "codex/gpt-5.5",
  "answer": "A"
}
```

The parser validates schema, text answers, call-slot identity, underlying model association, and
reducer model association. Invalid envelopes become typed `EngineError` failures.

## 8. Deterministic model-route engine

The default `MockUrl4Engine` is an `EnginePort` implemented with a real in-process `Url4Node`.
Every complete expression passes through `node.evaluate(expression)`.

Its registered leaf handlers:

- preserve curated GPQA-shaped and DRACO-shaped deterministic fixtures;
- provide stable SHA-256-based fallback text for custom prompts;
- return A–D for generic multiple-choice prompts;
- return deterministic model-reducer output; and
- return valid DRACO criterion JSON.

The engine records received expressions for contract tests. It does not create fake `Run` objects,
bypass URL4 parsing, or bypass the benchmark grader.

`scripts/dev-url4.sh` exposes the same deterministic handlers through the URL4 CLI for optional
HTTP transport testing. It is not required by the notebooks.

## 9. Benchmarks and graders

### GPQA

- default: 20 bundled GPQA-shaped synthetic science cases;
- live: gated `Idavidrein/gpqa`, `gpqa_diamond`, after Hugging Face authorization;
- panel protocol: answer A, B, C, or D;
- grader: local exact-choice accuracy;
- primary metric: accuracy;
- baseline: best member accuracy using the same panel answers; and
- gain: fusion accuracy minus baseline.

Real GPQA text is not bundled or committed.

### DRACO

- default: 2 bundled DRACO-shaped research cases with one judge pass;
- live: `perplexity-ai/draco`, test split, with five judge passes;
- required fusion capability: `tools=["web_search"]` on panel calls;
- reducer: experiment-defined, commonly `ModelReducer`;
- grader: benchmark-owned per-criterion URL4 judge requests;
- judge route: `/gemini/3.1-pro-preview`;
- judge parameters: `temperature=0.2`, `reasoning=low`, `max_tokens=4096`;
- judge intent: pinned paper-aligned system prompt;
- judge context: criterion type, criterion, original query, and response;
- response: JSON with `explanation` and `criterion_status` (`MET` or `UNMET`); and
- primary metric: normalized positive/negative weighted rubric score.

Production DRACO claims additionally require provider-backed routes, web-search execution, exact
request semantics, independent judge samples, and telemetry. The deterministic run proves the SDK
and URL4 contract only.

## 10. Evaluation and Run contract

`Fusion.evaluate(benchmark, first=20, seed=0, progress=None)`:

1. resolves the benchmark and required capabilities;
2. loads the selected data mode;
3. compiles one concrete expression per case;
4. evaluates it through the selected URL4 engine;
5. validates and normalizes labeled answers;
6. reduces panel answers locally or reads the model-reducer answer;
7. invokes benchmark-owned grader calls through the same engine when required;
8. scores fusion and members from the same answers; and
9. returns an immutable `Run`.

`Run` records benchmark, dataset, data mode, engine, models, recipe, sample size, seed, score,
baseline, gain, reducer, per-model results, failures, incomplete cases, primary metric, metrics,
usage/cost placeholders, and creation time.

Until engine telemetry exists, token usage is zero and pricing is labeled unavailable/estimated.
The default result card states `local URL4 mock`, `no provider-quality claim`, and `no provider
spend` without using a generic simulation badge that could obscure which layer is deterministic.

## 11. Documentation and notebook contract

The documentation has three deliberate levels:

1. `examples/00_quickstart.ipynb`: no architecture detail; compose → run → compare only.
2. `examples/screamingface-engine.ipynb`: Python/YAML composition, recipe, concrete expression,
   approximate node tree, response envelopes, and model-backed reduction.
3. `examples/draco.ipynb`: benchmark adapter, experiment prompts, tools, model reduction, judge
   request/response, scoring, and production route requirements.

`packages/screamingface/docs/index.html` is the complete current public API and execution guide.
It must enumerate every `screamingface.__all__` export, use the ScreamingFace design system, work in
light and dark themes, and link to the generated notebooks.

Notebook files are generated from `scripts/build_*.py`; edit generators rather than hand-editing
JSON. CI executes every notebook from a clean kernel and checks for drift. Committed deterministic
outputs must disclose engine/data provenance and make no provider-quality claim.

## 12. Failure, security, and ownership boundaries

Public errors are typed:

- `EngineUnavailable`: HTTP engine could not be reached;
- `EngineError`: engine rejection or invalid response; and
- `DatasetUnavailable`: live/gated data cannot be loaded.

No credential appears in Fusion configuration, URL4, results, examples, errors, or logs. The
current SDK accepts no provider credential or AI Gateway credential at all.

Command-backed deterministic routes are a localhost development tool. The URL4 engine owns any
future hardening of command execution, hosted authentication, request authorization, streaming,
concurrency, caching, and telemetry.

## 13. Non-goals and owner consultation gates

The current slice does not decide:

- hosted-engine authentication or authorization;
- provider credential UX;
- engine-owned scalable model discovery;
- hosted URL4 deployment URL;
- streaming and recursive telemetry;
- usage/cost schema;
- leaderboard publishing;
- multi-round orchestration or arbitrary custom scripts; or
- URL4 import/preview/rebuild UX from OME-408.

These require owner consultation before implementation. The SDK must not reintroduce direct AI
Gateway access to work around missing engine infrastructure.

## 14. Acceptance criteria

- The bare quickstart imports and runs with no credentials or background service.
- Every model or judge request goes through a real URL4 node or strict URL4 HTTP client.
- ScreamingFace never contacts AI Gateway or providers directly.
- Explicit HTTP engine failures never fall back to deterministic execution.
- Engine and dataset provenance are separate in Session and Run.
- Fusion recipes round-trip through the URL4 parser and contain no runtime prompt or credential.
- Panel and model-reducer envelopes preserve stable call-slot/model association.
- GPQA and DRACO deterministic notebooks execute cleanly and disclose their limits.
- The static docs enumerate the complete public API and explain representative request/response
  shapes.
- Ruff, formatting, Pyright, Pytest, 95% coverage, notebook drift, and package build gates pass.
- The user-owned `packages/url4` branch overlay remains untouched by OME-400 SDK work.
