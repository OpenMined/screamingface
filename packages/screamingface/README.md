# screamingface

Compose model panels and benchmark them through a configured URL4 engine.

## Current implementation: Phase 4D

The SDK currently supports:

- `sf.config(engine=...)`, defaulting temporarily to `http://127.0.0.1:4404`;
- immutable `sf.Case`, `sf.Benchmark`, and `sf.Fusion` authoring;
- namespaced reducers, graders, and aggregators;
- `sf.models.list(...)` against the configured engine's executable capability registry;
- `sf.benchmarks.list(...)` against the SDK's installed canonical benchmark catalog;
- eager, validated `sf.benchmarks.load(...)` through the researcher's ordinary dataset access;
- canonical, shareable `fusion.url4` recipe compilation; and
- automatic benchmark-tool compilation onto concrete answer-producing member requests only;
- synchronous `fusion.run(...)` through only the configured URL4 engine, returning immutable
  in-memory result records;
- immutable grading record types (`Grades`, `CaseGrades`, `Grade`, `CriterionVerdict`, and
  `GradeFailure`); and
- `run.grade()` with deterministic local ExactChoice grading and URL4-backed Rubric judging,
  strict evidence coverage, validation-only retries, and weighted DRACO-compatible scoring; and
- strict paired `sf.aggregators.Mean()` reports plus the exact `fusion.evaluate(...)` facade.

The development `screamingface-engine` runs three model routes through one persistent `Url4Node`
and a shared AI Gateway client. It accepts direct endpoint requests and complete expressions
through `GET /v1?q=...`, with no subprocess route adapter. Its
`/reducers/majority-vote` endpoint executes the same SDK-owned exact-string selection logic,
without contacting AI Gateway.

When the engine is configured with its internal SearXNG service, the Gemini and Claude routes
advertise `web_search`. The engine translates that named capability into a bounded standard
model-tool loop: search and public-page reads happen inside the engine, while every model turn
still goes through AI Gateway. Codex remains tool-free. SearXNG is keyless and private to the
Compose network; it is not an offline search index and still queries its configured public search
engines.

Benchmark definitions, source loading, references, grading, and aggregation are SDK concerns.
The engine does not publish benchmark manifests or cases and never needs the researcher's
Hugging Face token. This keeps gated datasets in the researcher's process while all model-backed
work still crosses the configured URL4 engine.

Each selected benchmark case becomes one complete URL4 expression sent as
`GET /v1?q=<expression>`. Successful plaintext JSON is validated strictly as
`screamingface.fusion-result.v1`; connection, timeout, HTTP, URL4, and protocol failures are
recorded atomically at the case's original position. Execution performs no retries and never calls
AI Gateway directly. `run.grade()` grades those captured Fusion/member answers without rerunning
them. ExactChoice stays local; Rubric sends one ordinary URL4 judge-model expression per target,
criterion, and pass, with at most 16 requests in flight. Aggregation and
`fusion.evaluate(...)` remain ordinary local SDK stages after model-backed work. There is no mock,
simulated, or in-process engine fallback.

## Phase 1 walkthrough

[`examples/phase_1_engine_profile.ipynb`](examples/phase_1_engine_profile.ipynb) is the current
executable setup and API guide. It shows the registry plaintext, the separate model and benchmark
catalogs, local canonical benchmark loading, local benchmark construction, and network-free
Fusion authoring.

The public quickstart, architecture guide, and DRACO tutorial will be generated from the reviewed
contract in the planned notebook phase; no superseded notebook is retained as API documentation.

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
SearXNG      internal Compose service only
```

Model routes contact AI Gateway only through `screamingface-engine`. Loading GPQA happens in the
notebook or SDK process, not in either container. Authenticate in that process before requesting
gated datasets:

```bash
huggingface-cli login
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
sf.config(engine="http://127.0.0.1:4404")  # HTTP(S) origin only

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
run.fusion_name
run.members
run.results[0].members["member_1"].answer
run.results[0].answer
run.failures
run.to_dict()

grades = run.grade()
grades.fusion_name
grades.members
grades.results[0].fusion.score
grades.results[0].members["member_1"].score
grades.failures
grades.to_dict()

report = grades.aggregate()
report.score, report.baseline, report.gain
report.members["member_1"].score
report.to_dict()

# Exact shorthand for run -> grade -> aggregate:
report = fusion.evaluate(benchmark)
```

Construction and `fusion.url4` are network-free. Model discovery and execution contact only the
configured URL4 engine. Benchmark discovery is package-local; loading `gpqa@1` uses the caller's
Hugging Face session and returns ordinary immutable SDK values. `fusion.run("gpqa@1", first=20)`
is shorthand for local load followed by engine execution over a stable prefix. The SDK now
installs both `gpqa@1` and `draco@1`; DRACO can be loaded and inspected locally. The development
engine can execute `tools=web_search` members through its internal SearXNG adapter on the
compatible Gemini and Claude routes. A complete DRACO evaluation is still blocked by the missing
`gemini/3.1-pro-preview` judge route and the separately tracked long judge-expression transport
review. The SDK's generic Rubric implementation is already complete.

## Validation

```bash
uv run ruff check src tests apps/screamingface-engine/src apps/screamingface-engine/tests scripts
uv run ruff format --check src tests apps/screamingface-engine/src apps/screamingface-engine/tests scripts
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/screamingface-engine/src uv run pytest apps/screamingface-engine/tests \
  --cov=screamingface_engine --cov-fail-under=95 -q
```
