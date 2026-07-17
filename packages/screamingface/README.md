# screamingface

Compose model panels as URL4 recipes and measure whether their deterministic reduction beats the
best individual model.

## Quickstart

The committed quickstart is simulated but uses the real URL4 HTTP engine. Start its deterministic
model routes in one terminal:

```bash
cd packages/screamingface
./scripts/dev-url4.sh
```

Then run the SDK:

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

`sf.config()` is not required. By default, evaluation sends one complete URL4 expression per
question to `http://127.0.0.1:4404/v1`. Set `SCREAMINGFACE_ENGINE_URL` or call
`sf.config("http://host:port")` to use another engine address.

The deterministic routes return complementary answers, producing a repeatable result:

```text
fusion accuracy: 100.0
best single:      80.0
gain:            +20.0
```

These values demonstrate the ensemble workflow, not real provider quality.

## Execution boundary

ScreamingFace exclusively contacts the URL4 engine for model execution:

```text
ScreamingFace SDK
    builds one concrete URL4 expression
             │
             ▼
GET URL4_ENGINE/v1?q=<expression>
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

The SDK does not call AI Gateway or model providers, and it has no inference fallback. Real model
routes may contact AI Gateway internally, but that is owned by the URL4 engine application.

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

## Local deterministic engine

[`url4.dev.toml`](url4.dev.toml) registers three command routes:

```text
/codex/gpt-5.5
/gemini/2.5
/claude/sonnet-4.6
```

They invoke [`scripts/url4_mock_model.py`](scripts/url4_mock_model.py), which receives the resolved
URL4 intent and returns one `A`–`D` answer. It never contacts AI Gateway. The URL4 package and
engine source are not modified.

The local command routes do not yet consume `Request.params`; those parameters are nevertheless
part of the canonical URL4 recipe and are available to an in-process URL4 endpoint handler.
Authentication, hosted deployment, real AI-Gateway-backed routes, streaming, usage/cost metadata,
and DRACO are additive follow-up contracts.

## Development

```bash
cd packages/screamingface
uv sync --extra notebook
./scripts/dev-url4.sh
```

In another terminal:

```bash
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
# Detailed URL4 request and node walkthrough:
uv run --extra notebook jupyter lab examples/sf_url4_engine.ipynb
uv run pytest
uv run ruff check .
uv run pyright
```
