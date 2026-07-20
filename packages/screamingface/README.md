# screamingface

Compose model panels and benchmark them through a configured URL4 engine.

## Current implementation

The SDK currently supports:

- `sf.config(engine=...)`, defaulting temporarily to `http://127.0.0.1:4404`;
- `sf.connect()` for the engine-scoped notebook panel, plus explicit
  `sf.connect(provider, ...)`, `sf.disconnect(provider)`, and `sf.connections.list()` flows;
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

Before model-backed work, the SDK reads fresh provider status from the configured engine.
`fusion.run(...)` checks member and model-reducer requirements, `run.grade()` checks a model
judge when present, and `fusion.evaluate(...)` checks their union once. Missing credentials raise
one structured `sf.ConnectionRequiredError` before model spend instead of producing one failure
per case. Deterministic grading, aggregation, benchmark loading, and discovery remain independent
of provider connections.

`Fusion.run(...)`, `Run.grade(...)`, and `Fusion.evaluate(...)` accept `progress=True | False |
None`. The default `None` shows one live progress surface in Jupyter and remains silent in ordinary
scripts; `True` forces progress and `False` disables it. `evaluate(...)` follows requirement checks,
case completion, individual rubric judge responses, and aggregation, then yields to the final
`Report`. Progress is presentation-only and never changes scheduling, retries, spend, or results.

The development `screamingface-engine` runs four model routes through one persistent `Url4Node`
and a shared AI Gateway client. It accepts direct endpoint requests and complete expressions
through `GET /v1?q=...`, with no subprocess route adapter. Its
`/reducers/majority-vote` endpoint executes the same SDK-owned exact-string selection logic,
without contacting AI Gateway.

When the engine is configured with its internal SearXNG service, the Claude route advertises
`web_search`. The engine translates that named capability into a bounded standard
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

The registry advertises the engine's exact encoded request-target limit. Before opening an HTTP
client, the SDK measures every selected `/v1?q=...` target using the same percent encoding as the
request library. An oversize case or rubric-judge expression raises
`sf.EngineRequestTooLargeError` with its actual and allowed byte sizes, before any model or judge
spend. Literal judge context is carried in a quoted URL4 binding, so model answers containing
parentheses, quotes, backslashes, newlines, or dollar signs remain data rather than URL4 syntax.
The development profile allows 61440-byte request targets and independently returns HTTP 414 to
direct callers that exceed it.

## Walkthrough notebooks

[`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb) is the shortest public path. It
opens the engine-scoped provider panel, constructs one three-member majority-vote Fusion, evaluates
five canonical GPQA cases, and compares `score`, `baseline`, and `gain`. The evaluation makes the
documented 15 provider calls only after connection preflight succeeds.

[`examples/01_architecture.ipynb`](examples/01_architecture.ipynb) is the executable configuration
and architecture guide. It shows the SDK/engine boundary, raw registry plaintext, validated model
discovery, `fusion.url4` recipe semantics, and one real provider-free deterministic URL4 request.

[`examples/02_discovery.ipynb`](examples/02_discovery.ipynb) separates engine-backed model
discovery from SDK-local benchmark discovery. It demonstrates the shared `query`, `tools`, and
`limit` filters, returns only IDs, and keeps the Hugging Face-backed GPQA load disabled by default.

[`examples/03_fusions.ipynb`](examples/03_fusions.ipynb) is the network-free Fusion authoring
guide. It covers concise model IDs, per-member prompt and parameter overrides, repeated models,
deterministic majority voting, model-backed synthesis, and public `.url4` inspection.

[`examples/04_custom_benchmarks.ipynb`](examples/04_custom_benchmarks.ipynb) constructs a local
benchmark from ordinary `sf.Case` values. It explains sealed references, researcher-owned loading,
grader and aggregator selection, benchmark tools, and an optional default-off live evaluation.

[`examples/05_draco.ipynb`](examples/05_draco.ipynb) is the concise real-engine DRACO Preview
walkthrough. It connects providers, composes two independently prompted Claude research members
with a Codex reducer, evaluates one `draco-preview@1` case, and reads the resulting comparison.
Preview keeps every real DRACO question but retains one positive criterion and one Gemini 3.5
Flash judge pass. The equivalent explicit `load -> run -> grade -> aggregate` stages remain as a
commented learning aid; the notebook neither runs nor fabricates canonical `draco@1` results.

[`examples/06_connections.ipynb`](examples/06_connections.ipynb) explains the provider connection
control plane in isolation: interactive panel use, script-oriented OAuth and API-key calls,
connection status, disconnect, preflight errors, and the separate Hugging Face dataset session.
It makes no paid model call.

No superseded notebook is retained as API documentation.

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
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
# or
uv run --extra notebook jupyter lab examples/01_architecture.ipynb
# or
uv run --extra notebook jupyter lab examples/02_discovery.ipynb
# or
uv run --extra notebook jupyter lab examples/03_fusions.ipynb
# or
uv run --extra notebook jupyter lab examples/04_custom_benchmarks.ipynb
# or
uv run --extra notebook jupyter lab examples/05_draco.ipynb
# or
uv run --extra notebook jupyter lab examples/06_connections.ipynb
```

The notebooks are generated from `scripts/build_quickstart.py`, `scripts/build_architecture.py`,
`scripts/build_discovery.py`, `scripts/build_fusions.py`, `scripts/build_custom_benchmarks.py`, and
`scripts/build_draco_walkthrough.py`, and `scripts/build_connections.py`; edit the generators
rather than notebook JSON.

## Current API example

```python
import screamingface as sf

# Optional locally: this URL is currently the default.
sf.config(engine="http://127.0.0.1:4404")  # HTTP(S) origin only

# Notebook panel for every provider advertised by that engine.
sf.connect()

# Plain status for scripts and applications.
sf.connections.list()

models = sf.models.list()
benchmarks = sf.benchmarks.list()

fusion = sf.Fusion(
    "frontier-trio",
    models=[
        "codex/gpt-5.5",
        "gemini/3.5-flash",
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
report  # rich complete / partial / failed comparison in notebooks
report.score, report.baseline, report.gain
report.members["member_1"].score
report.to_dict()

# Exact shorthand for run -> grade -> aggregate:
report = fusion.evaluate(benchmark)
```

Construction and `fusion.url4` are network-free. Model discovery and execution contact only the
configured URL4 engine. Provider connection calls also contact only that engine; the SDK never
contacts AI Gateway directly. Benchmark discovery is package-local; loading `gpqa@1` uses the caller's
Hugging Face session and returns ordinary immutable SDK values. `fusion.run("gpqa@1", first=20)`
is shorthand for local load followed by engine execution over a stable prefix. The SDK now
installs `gpqa@1`, canonical `draco@1`, and the explicitly non-comparable `draco-preview@1` development
profile; all can be loaded and inspected locally. The development
engine can execute `tools=web_search` members through its internal SearXNG adapter on the Claude
route. It exposes the tool-free `gemini/3.5-flash` route used for bounded DRACO Preview judging.
Gemini research is deliberately not advertised: Gemini 3 requires an encrypted thought signature
on function-calling continuations, and the current AI Gateway normalization does not preserve it.
The engine also exposes the provisional tool-free
`gemini/3.1-pro-preview` judge route required by the SDK's generic Rubric implementation, under
the explicit assumption that AI Gateway will register
`gemini-cli/gemini-3.1-pro-preview`. Successful provider-backed grading still requires that
external registration and provider authentication; no substitute judge or runtime fallback is
used.

`sf.connect()`, live evaluation progress, and `Report` use one shared square, shadow-free,
light/dark-safe visual foundation. Notebook reports show complete, partial, and zero-scored runs
with paired coverage and structured failure summaries; they never render unavailable numeric
metrics as empty cards. Plain Python `repr(report)` carries the same status concisely, while
`report.score`, `report.baseline`, and `report.gain` remain correctly typed as `None` when no case
was scorable. Ordinary values and `models.list()`/`benchmarks.list()` remain plain Python rather
than being turned into decorative widgets.

## Validation

```bash
uv run ruff check src tests apps/screamingface-engine/src apps/screamingface-engine/tests scripts
uv run ruff format --check src tests apps/screamingface-engine/src apps/screamingface-engine/tests scripts
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/screamingface-engine/src uv run pytest apps/screamingface-engine/tests \
  --cov=screamingface_engine --cov-fail-under=95 -q
```
