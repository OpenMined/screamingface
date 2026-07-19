# screamingface

Compose model panels and benchmark them through a configured URL4 engine.

## Current implementation: Phase 2C

The SDK currently supports:

- `sf.config(engine=...)`, defaulting temporarily to `http://127.0.0.1:4404`;
- immutable `sf.Case`, `sf.Benchmark`, and `sf.Fusion` authoring;
- namespaced reducers, graders, and aggregators;
- `sf.models.list(...)` and `sf.benchmarks.list(...)` against the engine registry; and
- eager, validated `sf.benchmarks.load(...)` from engine manifests and NDJSON case routes;
- canonical, shareable `fusion.url4` recipe compilation; and
- synchronous `fusion.run(...)` through only the configured URL4 engine, returning immutable
  in-memory result records.

The development `screamingface-engine` additionally runs three tool-free model routes through one
persistent `Url4Node` and a shared AI Gateway client. It accepts direct endpoint requests and
complete expressions through `GET /v1?q=...`, with no subprocess route adapter. Its
`/reducers/majority-vote` endpoint executes the same SDK-owned exact-string selection logic,
without contacting AI Gateway.

Each selected benchmark case becomes one complete URL4 expression sent as
`GET /v1?q=<expression>`. Successful plaintext JSON is validated strictly as
`screamingface.fusion-result.v1`; connection, timeout, HTTP, URL4, and protocol failures are
recorded atomically at the case's original position. Phase 2C performs no retries and never calls
AI Gateway directly. Grading, aggregation, and the `fusion.evaluate(...)` facade arrive in Phase
3. There is no mock, simulated, or in-process engine fallback.

## Phase 1 walkthrough

[`examples/phase_1_engine_profile.ipynb`](examples/phase_1_engine_profile.ipynb) is the current
executable setup and API guide. It shows the registry plaintext, discovery filters, opt-in remote
benchmark loading, local benchmark construction, and network-free Fusion authoring.

The older quickstart, architecture, and DRACO notebooks predate the approved greenfield contract
and are not current API documentation. They will be regenerated in the planned notebook phase.

## Start the development engine

The screamingface-engine app is temporarily kept under this package while its deployment ownership is
resolved:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

Only one development stack can own ports 4404 and 9105. Stop any earlier URL4 or AI Gateway
containers before starting this one.

This starts:

```text
URL4 engine  http://127.0.0.1:4404
AI Gateway   http://127.0.0.1:9105
```

Discovery and benchmark loading do not contact AI Gateway. Model routes contact AI Gateway only
through `screamingface-engine`. Published benchmark routes load real Hugging Face datasets.
Authenticate before requesting gated datasets and expose the token to Compose:

```bash
huggingface-cli login
export HF_TOKEN=hf_...
```

No synthetic dataset fallback exists.

The deterministic reducer and SDK run path can be smoke-tested without provider credentials:

```bash
uv run python apps/screamingface-engine/scripts/smoke_phase2b.py
uv run python apps/screamingface-engine/scripts/smoke_phase2c.py
```

Run those commands from `packages/screamingface` while the Compose stack is running. The Phase 2B
smoke evaluates a complete literal reducer expression. The Phase 2C smoke uses the public SDK to
compile and submit a complete model-backed Fusion expression. A provider-backed success is
validated when credentials exist; otherwise the expected atomic URL4 failure proves the
engine-to-Gateway topology without pretending a provider answered.

## Run the walkthrough

From `packages/screamingface` in another terminal:

```bash
uv sync --extra notebook
uv run --extra notebook jupyter lab examples/phase_1_engine_profile.ipynb
```

The notebook is generated from `scripts/build_phase1_engine_profile.py`; edit the generator rather
than the notebook JSON.

## Current API example

```python
import screamingface as sf

# Optional locally: this URL is currently the default.
sf.config(engine="http://127.0.0.1:4404")

models = sf.models.list()
benchmarks = sf.benchmarks.list()

fusion = sf.Fusion(
    "frontier-trio",
    models=[
        "codex/gpt-5.5",
        "gemini/2.5",
        "claude/sonnet-4.6",
    ],
    reducer=sf.reducers.MajorityVote(),
)

# Canonical recipe template: contains $question, but no case or answer key.
fusion.url4

benchmark = sf.Benchmark(
    "arithmetic@1",
    cases=[sf.Case("addition", "What is 2 + 2?", reference="4")],
    grader=sf.graders.ExactChoice(),
)

run = fusion.run(benchmark)
run.results[0].members["panel_1"].answer
run.results[0].answer
run.failures
run.to_dict()
```

Construction and `fusion.url4` are network-free. Discovery, loading, and execution contact only
the configured URL4 engine. `fusion.run("gpqa@1", first=20)` is the named-benchmark shorthand for
loading and running a stable prefix. The current model registry deliberately advertises no tools:
`web_search` returns only after a real named-tool adapter exists and has been tested.

## Validation

```bash
uv run ruff check src tests apps/screamingface-engine/src apps/screamingface-engine/tests scripts
uv run ruff format --check src tests apps/screamingface-engine/src apps/screamingface-engine/tests scripts
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/screamingface-engine/src uv run pytest apps/screamingface-engine/tests \
  --cov=screamingface_engine --cov-fail-under=95 -q
```
