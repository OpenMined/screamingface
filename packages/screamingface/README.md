# screamingface

Compose URL4-native model Recipes and evaluate them against engine-advertised benchmarks.

## Current architecture

The researcher-facing SDK talks only to the configured ScreamingFace engine. It never calls AI
Gateway, model providers, or Tavily directly.

```text
ScreamingFace SDK
  └─ GET /v1?q=<complete benchmark-run URL4>
       Accept: text/event-stream
       └─ screamingface-engine / Url4Node
            ├─ benchmark case data route
            ├─ model routes → AI Gateway → providers
            ├─ OpenRouter-managed tools for OpenRouter routes
            ├─ Tavily loop for verified Hugging Face routes
            ├─ reducer and grader routes
            └─ aggregator route → plaintext report
```

`fusion.url4` is a reusable answer recipe with an unresolved `$question`. Evaluation wraps that
recipe with the benchmark case route, stable slice, grader, and aggregator. The resulting
`report.url4` expresses the complete reproducible run.

The SDK sends exactly one `GET /v1?q=...` request per evaluation. It requests a strict SSE stream
so notebooks show engine-owned dataset loading, model activity, completed case grading, and
aggregation. The terminal `complete` event contains the same plaintext URL4 value returned by a
normal request. The SDK validates that JSON as `screamingface.report.v1` and builds an immutable
`sf.Report`. Idle keep-alives preserve the connection without replacing meaningful progress.
These events report ScreamingFace route milestones, not model tokens or hidden URL4 internals.

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

- `sf.Model` is one configured model-backed answer Recipe; its name defaults to the final segment
  of its model route.
- `sf.Fusion` combines Models or nested Fusions through an explicit reducer.
- `sf.Recipe` is their non-constructible umbrella type.
- `sf.benchmarks.list(...)` returns benchmark IDs advertised by the configured engine.
- `sf.benchmarks.load(id)` loads and validates an engine manifest, not dataset cases.
- `benchmark.evaluate(candidate, first=...)` executes one complete single-candidate URL4 run.
- Candidate-enabled benchmarks also accept an ordered sequence and return `sf.StudyReport`.
- `sf.Report` contains paired Recipe/member metrics, typed failures, and the complete run URL4.
- `sf.StudyReport` compares independently scored candidate roots over one shared case set.

Models and Fusions are network-free to construct. `sf.models.list(...)`, benchmark discovery,
connections, and evaluation contact only the configured engine.

## Connections and dataset access

`sf.connect()` renders the engine-scoped connection panel. Script APIs are explicit:

```python
sf.connections.list()
sf.connect("gemini", api_key="...")
sf.connect("codex", method="oauth")
sf.connect("openrouter", api_key="sk-or-...")
sf.connect("tavily", api_key="tvly-...")
sf.disconnect("gemini")
```

Model-provider credentials are managed through the engine's AI Gateway integration. Tavily is an
additional engine-owned service connection only for models whose registry record requires it;
OpenRouter-managed web tools use the OpenRouter connection. Tavily never passes through AI Gateway.

Dataset access is separate. In the local MVP, the engine reads `HF_TOKEN` from its environment
when a benchmark data route loads a gated Hugging Face source. `sf.connect("huggingface")` is an
inference-provider connection and is not the dataset token.

Before sending the run URL4, the SDK checks the candidate Recipe's member, reducer, grader, and
tool-service requirements against fresh registry and connection state. Missing credentials raise one
`sf.ConnectionRequiredError` before model spend.

For an official tool-enabled benchmark, its engine manifest points to one immutable versioned
tool-policy data route. The complete run URL4 resolves that policy once per case and shares it with
answer-producing members; it contains capability names and limits, never Tavily/OpenRouter
credentials or backend selection. A custom local Benchmark instead serializes the same portable
policy inline because it has no engine-owned route. In both forms, the engine privately chooses the
registered model route's OpenRouter-managed or Tavily implementation.

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

The development engine advertises `gpqa@1` plus DRACO when its pinned OpenRouter judge appears in
the AI Gateway startup catalog. `draco-preview@1` uses real pinned DRACO cases, one positive
criterion, and one judge pass for inexpensive integration checks. `draco-lite@1` fixes execution
to the first pinned case, keeps five deterministic criteria spanning all four rubric sections, and
makes one judge pass per criterion. `draco@1` keeps all 100 complete rubrics and five independent per-criterion
judge passes. All three use the immutable provider-neutral research-tool policy route.

DRACO Lite accepts all sixteen candidates as one complete URL4 transaction. The URL4 contains an
ordered flat candidate DAG: reused Recipe objects execute once, independent sampled objects remain
independent, and a failed dependency affects only candidate roots that need it. Only final
candidate answers are graded. Use `benchmark.url4(candidates)` to inspect or share the complete
study before executing it. The single-candidate form remains available for every benchmark.

## Walkthrough notebooks

- [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb): minimal supported GPQA flow.
- [`examples/01_architecture.ipynb`](examples/01_architecture.ipynb): registry, URL4, and ownership.
- [`examples/02_discovery.ipynb`](examples/02_discovery.ipynb): engine model/benchmark discovery.
- [`examples/03_fusions.ipynb`](examples/03_fusions.ipynb): network-free Recipe authoring.
- [`examples/04_custom_benchmarks.ipynb`](examples/04_custom_benchmarks.ipynb): authoring boundary.
- [`examples/05_draco_quickstart.ipynb`](examples/05_draco_quickstart.ipynb): complete 7-solo and
  9-Fusion DRACO topology over one case, five section-diverse criteria, and one judge pass.
- [`examples/06_connections.ipynb`](examples/06_connections.ipynb): provider/tool connections.
- [`examples/07_full_draco_url4.ipynb`](examples/07_full_draco_url4.ipynb): non-runnable production
  DRACO handoff showing one flat, complete benchmark URL4 per candidate.
- [`examples/08_draco_explained.ipynb`](examples/08_draco_explained.ipynb): the same executable
  DRACO Lite study with candidate DAG, benchmark creation, URL4, tools, grading, and response details.

Notebooks are deterministic outputs of `scripts/build_quickstart.py`,
`scripts/build_architecture.py`, `scripts/build_discovery.py`, `scripts/build_fusions.py`,
`scripts/build_custom_benchmarks.py`, `scripts/build_connections.py`, and
`scripts/build_draco_quickstart.py`, `scripts/build_full_draco_url4_contract.py`, and
`scripts/build_draco_explained.py`. Edit the builders, then regenerate the notebooks.

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
