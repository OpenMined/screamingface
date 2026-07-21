# screamingface

Compose URL4-native model Recipes and evaluate them against engine-advertised benchmarks.

## Current architecture

The researcher-facing SDK talks only to the configured ScreamingFace engine. It never calls AI
Gateway, model providers, or Tavily directly.

```text
ScreamingFace SDK
  └─ GET /v1?q=<complete benchmark-run URL4>
       └─ screamingface-engine / Url4Node
            ├─ benchmark case data route
            ├─ model routes → AI Gateway → providers
            ├─ Tavily tools for verified Hugging Face routes
            ├─ reducer and grader routes
            └─ aggregator route → plaintext report
```

`fusion.url4` is a reusable answer recipe with an unresolved `$question`. Evaluation wraps that
recipe with the benchmark case route, stable slice, grader, and aggregator. The resulting
`report.url4` expresses the complete reproducible run.

The SDK sends exactly one `GET /v1?q=...` request per evaluation. The engine executes all cases,
model calls, grading, and aggregation represented by that URL4, then returns plaintext JSON using
`screamingface.report.v1`. The SDK strictly validates it into an immutable `sf.Report`.

There is no mock, in-process execution fallback, client-side case loop, or public
`Run → Grades → aggregate` compatibility path.

## Quickstart

Start the local development engine first:

```bash
cd packages/screamingface/apps/screamingface-engine
export HF_TOKEN=hf_...  # required when the engine loads gated benchmark data
./dev.sh restart
```

Then, from the SDK environment:

```python
import screamingface as sf

sf.connect()

fusion = sf.Fusion(
    "frontier-trio",
    members=[
        "codex/gpt-5.5",
        "gemini/2.5-flash",
        "claude/sonnet-4.6",
    ],
    reducer=sf.reducers.MajorityVote(),
)

gpqa = sf.benchmarks.load("gpqa@1")
report = gpqa.evaluate(fusion, first=5)

report.score, report.baseline, report.gain
report.url4
```

The SDK temporarily defaults to `http://127.0.0.1:4404`. Override it with an origin-only URL:

```python
sf.config(engine="https://screamingface.example")
```

## Public concepts

- `sf.Model` is one configured model-backed answer Recipe.
- `sf.Fusion` combines Models or nested Fusions through an explicit reducer.
- `sf.Recipe` is their non-constructible umbrella type.
- `sf.benchmarks.list(...)` returns benchmark IDs advertised by the configured engine.
- `sf.benchmarks.load(id)` loads and validates an engine manifest, not dataset cases.
- `benchmark.evaluate(recipe, first=...)` executes one complete URL4 run.
- `sf.Report` contains paired Recipe/member metrics, typed failures, and the complete run URL4.

Models and Fusions are network-free to construct. `sf.models.list(...)`, benchmark discovery,
connections, and evaluation contact only the configured engine.

## Connections and dataset access

`sf.connect()` renders the engine-scoped connection panel. Script APIs are explicit:

```python
sf.connections.list()
sf.connect("gemini", api_key="...")
sf.connect("codex", method="oauth")
sf.connect("tavily", api_key="tvly-...")
sf.disconnect("gemini")
```

Model-provider credentials are managed through the engine's AI Gateway integration. Tavily is an
engine-owned service connection and does not pass through AI Gateway.

Dataset access is separate. In the local MVP, the engine reads `HF_TOKEN` from its environment
when a benchmark data route loads a gated Hugging Face source. `sf.connect("huggingface")` is an
inference-provider connection and is not the dataset token.

Before sending the run URL4, the SDK checks the Recipe's member, reducer, grader, and tool-service
requirements against fresh registry and connection state. Missing credentials raise one
`sf.ConnectionRequiredError` before model spend.

## Discovery

Both discovery surfaces reflect the configured engine registry and return plain IDs:

```python
sf.models.list()
sf.models.list(query="gemini", tools=("web_search",), limit=10)

sf.benchmarks.list()
sf.benchmarks.list(query="gpqa", limit=10)
```

Loading a benchmark returns its immutable manifest. The engine does not load cases until it
evaluates the URL4 data route.

## Custom benchmark authoring

`sf.Case` and `sf.Benchmark` remain compact authoring values. They intentionally stop after
validated cases plus strategy selection; ScreamingFace is not an ETL DSL.

```python
definition = sf.Benchmark(
    "tiny-science@1",
    cases=[sf.Case("q1", "Choose A or B", reference="A")],
    grader=sf.graders.ExactChoice(),
    aggregator=sf.aggregators.Mean(),
)
```

This object is input for an engine deployment, not a client-side upload or execution fallback.
Register its cases, grader, aggregator, and manifest on an engine; consumers then load it using
the same `sf.benchmarks.load(...)` API without changing evaluation syntax.

## Current benchmark scope

The development engine advertises `gpqa@1`. It loads the pinned GPQA Diamond source through its
`HF_TOKEN`, exposes cases as NDJSON, grades with `/graders/exact-choice/1`, and aggregates with
`/aggregators/mean/1`.

DRACO source definitions remain useful engine-building references, but DRACO is not currently
advertised as executable. A complete multi-system DRACO URL4 still needs a documented URL4
composition (or generic all-settled primitive) that preserves independent named-system results,
typed per-system failures, and shared dependency execution. The SDK does not pretend otherwise.

## Walkthrough notebooks

- [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb): minimal supported GPQA flow.
- [`examples/01_architecture.ipynb`](examples/01_architecture.ipynb): registry, URL4, and ownership.
- [`examples/02_discovery.ipynb`](examples/02_discovery.ipynb): engine model/benchmark discovery.
- [`examples/03_fusions.ipynb`](examples/03_fusions.ipynb): network-free Recipe authoring.
- [`examples/04_custom_benchmarks.ipynb`](examples/04_custom_benchmarks.ipynb): authoring boundary.
- [`examples/06_connections.ipynb`](examples/06_connections.ipynb): provider/tool connections.

Notebooks are deterministic outputs of `scripts/build_quickstart.py`,
`scripts/build_architecture.py`, `scripts/build_discovery.py`, `scripts/build_fusions.py`,
`scripts/build_custom_benchmarks.py`, and `scripts/build_connections.py`. Edit the builders, then
regenerate the notebooks.

## Validation

```bash
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/screamingface-engine/src uv run pytest apps/screamingface-engine/tests \
  --cov=screamingface_engine --cov-fail-under=95 -q
uv run --extra notebook python scripts/check_notebooks.py
uv build
```
