# screamingface

Compose model panels as URL4 recipes and measure whether their deterministic reduction beats the
best individual member.

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
(panel_1=/codex/gpt-5.5($question)!'Answer the multiple-choice question', ...)
```

During evaluation, ScreamingFace adds a concrete `question='...'` binding and sends the resulting
expression to `/v1`. Constructing or displaying a fusion never performs network I/O.

## MVP ownership

The URL4 engine owns parsing, dependency execution, model-route dispatch, concurrency, and the
evaluated result. ScreamingFace owns benchmark loading, request compilation, answer normalization,
majority voting, answer-key scoring, best-member baseline, and gain.

The current response schema is `screamingface.panel-result.v1`, with stable `panel_N_model` and
`panel_N_answer` fields. Stable slots preserve association even when engine calls complete out of
order and allow the same model to appear in more than one slot later.

## Local deterministic engine

[`url4.dev.toml`](url4.dev.toml) registers three command routes:

```text
/codex/gpt-5.5
/gemini/2.5
/claude/sonnet-4.6
```

They invoke [`scripts/url4_mock_model.py`](scripts/url4_mock_model.py), which reads the resolved
question from stdin and returns one `A`–`D` answer. It never contacts AI Gateway. The URL4 package
and engine source are not modified.

The MVP deliberately omits model parameters because the current generic URL4 command adapter does
not forward `Request.params`. Authentication, hosted deployment, real AI-Gateway-backed routes,
streaming, usage/cost metadata, synthesis, and DRACO are additive follow-up contracts.

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
