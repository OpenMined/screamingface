# screamingface

Compose model panels as URL4 recipes and measure whether their deterministic reduction beats the
best individual model.

## Documentation

Choose the smallest useful entry point:

| Guide | Use it for |
|---|---|
| [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb) | Bare compose → run → compare loop |
| [`examples/sf_url4_engine.ipynb`](examples/sf_url4_engine.ipynb) | URL4 recipe, concrete request, node tree, response, Python/YAML, and model reducer |
| [`examples/draco.ipynb`](examples/draco.ipynb) | Open-ended panel, synthesis, rubric judging, and production-engine requirements |
| [`docs/index.html`](docs/index.html) | Complete exported API, architecture, wire envelopes, benchmarks, and runtime modes |

The notebooks are generated from `scripts/build_*.py`; edit their builders rather than the
notebook JSON.

## Quickstart

The quickstart is zero-setup. ScreamingFace defaults to a real URL4 node running in-process, with
deterministic model-route handlers that never contact AI Gateway or a provider:

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

print(fusion.url4)
run = fusion.evaluate("gpqa", first=20, seed=0)
print(run.score, run.baseline, run.gain)
```

`sf.config()` is not required. The default mock engine still parses and executes every complete
expression with `Url4Node`; only its leaf model responses are local fixtures. Engine-graded
benchmarks such as DRACO send their judge expressions through the same in-process node.

Execution and dataset selection are independent:

| Configuration | URL4 execution | Benchmark data |
|---|---|---|
| no configuration | in-process deterministic node | bundled fixture |
| `sf.config(mode="live")` | in-process deterministic node | live dataset |
| `sf.config("http://127.0.0.1:4404")` | HTTP URL4 engine | bundled fixture |
| `sf.config("https://url4.example", mode="live")` | HTTP URL4 engine | live dataset |

`SCREAMINGFACE_ENGINE_URL` selects an HTTP engine without changing notebook code. An explicitly
selected HTTP engine never falls back to the mock if it is unavailable.

The same switch is available explicitly in code:

```python
sf.config(engine="mock")                 # deterministic in-process URL4 node
sf.config("http://127.0.0.1:4404")       # strict HTTP; errors stay visible
```

Every completed `Run` records these independent choices as `run.engine` (`"mock"` or the HTTP
URL) and `run.mode` (`"mock"` fixture data or `"live"` dataset data). The result card displays
both, preventing a live dataset run against deterministic routes from being mistaken for provider
inference.

The deterministic routes return complementary answers, producing a repeatable result:

```text
fusion accuracy: 100.0
best single:      80.0
gain:            +20.0
```

These values demonstrate the ensemble workflow, not real provider quality.

## Execution boundary

ScreamingFace delegates all model execution to the selected URL4 engine:

```text
ScreamingFace SDK
    builds one concrete URL4 expression
             │
             ├── default ──► in-process Url4Node
             │
             └── HTTP ─────► GET URL4_ENGINE/v1?q=<expression>
             │
             ▼
URL4 engine dispatches /provider/model routes
             │
             ▼
engine returns one labeled panel-result struct
             │
             ▼
ScreamingFace votes and scores locally
```

The SDK does not call AI Gateway or model providers. The selected engine is visible in every run;
the mock is never used as a fallback for an unavailable HTTP engine. Production model routes may
contact AI Gateway internally, but that is owned by the URL4 engine application.

## Recipe versus request

`fusion.url4` is the shareable recipe. Its `$question` binding is intentionally unresolved:

```url4
(panel_1=/codex/gpt-5.5()!'$question', ...)
```

During evaluation, ScreamingFace adds a concrete `question='...'` binding and sends the resulting
expression to `/v1`. URL4 resolves `$question` into the model call's intent; its context is empty.
Constructing or displaying a fusion never performs network I/O.

Model-backed reduction uses the same mechanism:

```python
fusion = sf.Fusion(
    "model-reduced",
    models=["codex/gpt-5.5", "gemini-cli/gemini-2.5-pro"],
    reducer=sf.ModelReducer(
        model="anthropic/claude-sonnet-4-6",
        prompt="Synthesize one final answer from $panel_answers for $question",
        params={"temperature": 0.0, "max_tokens": 512},
    ),
)
```

Research benchmarks declare their model capabilities explicitly. For DRACO, `tools` applies to
every panel model and is part of the shareable URL4 recipe; it does not silently apply to the
reducer or judge:

```python
fusion = sf.Fusion(
    "research-trio",
    models=[
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-6",
    ],
    tools=["web_search"],
    reducer=sf.ModelReducer(
        model="codex/gpt-5.5",
        prompt="Synthesize $panel_answers for $question",
    ),
)
```

This compiles `tools=web_search` onto each panel model node. The URL4 engine owns translating that
generic capability into the provider-specific tool configuration. `evaluate("draco")` rejects a
fusion that does not declare web search rather than changing its recipe implicitly.

`Reducer` is the extensible reducer contract. `MajorityVote` and `ModelReducer` are concrete
mechanisms; synthesis, selection, ranking, and adjudication are behaviors expressed by a
`ModelReducer` prompt rather than separate classes.

Plain model IDs are the common case. Use a strict model dictionary only when one model needs its
own name, prompt, or URL4 parameters:

```python
fusion = sf.Fusion(
    "sampled-opus",
    prompt="Answer the benchmark question carefully: $question",
    models=[
        {
            "model": "anthropic/claude-sonnet-4-6",
            "name": "opus-sample-1",
            "params": {"temperature": 0.7},
        },
        {
            "model": "anthropic/claude-sonnet-4-6",
            "name": "opus-sample-2",
            "prompt": "Independently solve and check this question: $question",
            "params": {"temperature": 0.7},
        },
    ],
)
```

A string is shorthand for `{"model": "provider/model"}`. Dictionaries accept only `model`,
`name`, `prompt`, and `params`; unknown fields fail at fusion construction. Private call-slot
identities keep repeated models distinct. `Fusion(prompt=...)` is the shared panel-prompt default;
a model dictionary's `prompt` overrides it for that call, and the default is `$question` when the
fusion prompt is omitted.

Panel entries and `ModelReducer` deliberately have different public shapes: model lists are
compact repeated data, while a reducer is typed executable behavior. Internally they share one
validated model-call representation and compile with identical URL4 route, prompt, and parameter
semantics. Reducers remain concrete objects in Python. YAML uses a strict
`reducer: {kind: ...}` mapping which `Fusion.from_yaml()` converts into the corresponding object.
`fusion.models` round-trips the canonical strings/dictionaries; `fusion.model_ids` is the flat
tuple of underlying model IDs.

## MVP ownership

The URL4 engine owns parsing, dependency execution, model-route dispatch, concurrency, and the
evaluated result. ScreamingFace owns benchmark loading, request compilation, answer normalization,
majority voting, answer-key scoring, best-member baseline, and gain.

The current response schemas are `screamingface.panel-result.v2` and
`screamingface.fusion-result.v2`, with stable `panel_N_id`, `panel_N_model`, and `panel_N_answer`
fields. Private slot IDs identify calls separately from models, preserving association when calls
complete out of order and allowing one model to appear in multiple sampled or role-specific slots.

## Deterministic URL4 engine

The default engine is implemented by a real in-process `Url4Node`. It receives the complete URL4
expression, resolves bindings and dependencies, invokes deterministic model endpoints, and returns
the same result schemas expected from an HTTP engine. This lets Python, YAML, reducer, benchmark,
and DRACO examples run without a background process while still exercising URL4 itself.

The deterministic handlers preserve the curated GPQA and DRACO fixtures and provide stable
fallback responses for custom prompts. Their outputs test orchestration mechanics only; scores are
not provider-quality measurements.

To exercise the identical routes over actual HTTP, run:

```bash
cd packages/screamingface
./scripts/dev-url4.sh
```

[`url4.dev.toml`](url4.dev.toml) registers the three panel routes and the DRACO judge route:

```text
/codex/gpt-5.5
/gemini/2.5
/claude/sonnet-4.6
/gemini/3.1-pro-preview
```

The in-process node and optional command server share the same deterministic handlers. They return
GPQA answers, DRACO research responses, synthesis, and rubric verdicts without contacting
AI Gateway. The URL4 package and engine source are not modified.

The DRACO grader sends the paper-aligned system prompt as URL4 intent, the criterion request as
URL4 context, and `temperature=0.2`, `reasoning=low`, and `max_tokens=4096` as model parameters.
The deterministic routes do not execute provider capabilities or consume request parameters.
Production URL4 routes must preserve the judge request's intent/context as system/user messages,
honor model parameters and `tools=web_search`, and contact AI Gateway internally. Authentication,
hosted deployment, streaming, and usage/cost/tool telemetry remain engine-application contracts.

## Development

```bash
cd packages/screamingface
uv sync --extra notebook
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
# Detailed URL4 request and node walkthrough:
uv run --extra notebook jupyter lab examples/sf_url4_engine.ipynb
# DRACO adapter, synthesis, URL4 judge, and weighted comparison:
uv run --extra notebook jupyter lab examples/draco.ipynb
uv run pytest
uv run ruff check .
uv run pyright
```

No server is required for the notebooks. Run `./scripts/dev-url4.sh` only when testing the optional
HTTP transport, then select it with `sf.config("http://127.0.0.1:4404")`.
