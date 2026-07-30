# screamingface

Evaluate Models and Fusions against URL4-native research Benchmarks.

> **Development status:** immutable Model/Fusion authoring, Engine-backed discovery, the direct
> evaluation API, and the confirmed `url4-cloud` lifecycle are implemented. Production Benchmark
> manifests, pre-spend capability validation, and Fusion compilation remain explicit Engine
> contract gates; there is no fixture, stale registry, or embedded execution fallback.

## Target v1 workflow

The approved Python workflow is:

```python
import screamingface as sf

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier_pair = sf.Fusion(
    "frontier-pair",
    members=[opus, gpt],
    reducer=sf.reducers.Synthesis(
        "openrouter/anthropic/claude-opus-4.8",
    ),
)

with sf.Client() as client:
    report = client.evaluate(
        [opus, gpt, frontier_pair],
        benchmark="draco",
        limit=5,
    )
```

`evaluate(...)` resolves the Benchmark, validates every Candidate, compiles one complete URL4 per
Candidate, executes those independent Candidate Runs, and returns one immutable `Report`. All
no-spend validation finishes before the first paid Run starts. The complete example becomes
runnable when the SF Engine requirements
listed in
[`../../docs/spec/2026-07-26-OME-605-engine-requirements.md`](../../docs/spec/2026-07-26-OME-605-engine-requirements.md)
are published.

Today, Model Candidates compile against the provisional Benchmark manifest contract. Fusion
compilation and capability validation remain blocked until their Engine contracts are agreed.
Unsupported Candidates fail with typed errors instead of falling back to Client-side execution.

## Install

```bash
pip install screamingface
```

Python 3.12 or newer is required.

## Client configuration

Create one Client for the Engine you want to use:

```python
with sf.Client(engine_url="http://127.0.0.1:9108") as client:
    report = client.evaluate(candidates, benchmark="draco", limit=5)
```

Applications and concurrent workflows can use the matching asynchronous interface:

```python
async with sf.AsyncClient(engine_url=engine_url) as client:
    report = await client.evaluate(candidates, benchmark="draco", limit=5)
```

Both Clients return the same domain values. `Client.evaluate` blocks;
`AsyncClient.evaluate` awaits. Both hide Benchmark resolution, URL4 compilation, REST/WebSocket
transport, Event replay, and Report decoding behind the same interface.

Local and hosted Engines use the same Client contract. Local mode may run the URL4 executor
in-process with an in-memory event bus; hosted mode may use the REST/WebSocket control plane with
NATS and scheduled workers. From the Client's perspective only `engine_url` changes. Generic URL4
execution does not itself provide the still-missing ScreamingFace Benchmark and capability
contracts.

## Progress and Reports

`evaluate` consumes the Engine's REST and WebSocket lifecycle internally. An optional callback
receives typed CloudEvents views in sequence:

```python
def observe(event: sf.Event) -> None:
    print(event.kind)


with sf.Client() as client:
    report = client.evaluate(
        candidates,
        benchmark="draco",
        limit=5,
        on_event=observe,
    )
```

If a callback raises, the Client attempts to cancel all active Candidate Runs and re-raises the
original exception.

One `Report` shape covers one or many Candidates:

```python
report.ok
report.benchmark
report.case_count
report.candidates[0]
report.candidates["frontier-pair"]
report.candidates["frontier-pair"].run_id
report.candidates["frontier-pair"].url4
report.candidates["frontier-pair"].operations
report.candidates.only
report.failures
report.usage
report.started_at
report.completed_at
report.to_dict()
report.to_json()
```

Partial Candidate, grading, or aggregation failures remain typed data in a valid Report.
Authentication, validation, transport, protocol, and missing-Report failures raise typed
exceptions.

## Ownership boundary

```text
Researcher or SF App
        ↓
ScreamingFace Python Client
  Recipe authoring · URL4 compilation · Events · Reports
        ↓  REST + WebSocket
SF Engine
  URL4 execution · Benchmarks · grading · aggregation · Tools
        ↓
AI Gateway
  provider credentials · model dispatch
```

The Client calls only its configured SF Engine. It never calls AI Gateway, model providers,
Tavily, or Benchmark datasets directly. Local and hosted Engines expose the same Client-visible
contract; in-memory channels, NATS, workers, and deployment topology are Engine details.

Models and Fusions are immutable, Client-independent, and network-free. Benchmarks are immutable
versioned Engine protocols that own cases, judge configuration, grading, aggregation, Tools, and
execution policy.

## Discovery

An Engine implementing the provisional catalogue contract exposes typed discovery:

```python
models = sf.models.list()
benchmarks = sf.benchmarks.list()
```

Explicit Clients provide the same interface through `client.models.list()` and
`client.benchmarks.list()`; asynchronous Clients use the same names with `await`. These catalogue
schemas remain provisional until the production SF Engine contracts are finalized.

The returned catalogues are immutable ordered sequences: iteration, indexing, slicing, and
`len()` work normally in scripts and sidecars. Evaluating one in Jupyter automatically renders a
searchable catalogue when the `notebook` extra is installed, with escaped static HTML and compact
terminal representations as fallbacks. Notebook rendering does not change the underlying values
or introduce a separate discovery operation.

## Examples

- [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb): runnable Model/Fusion authoring
  plus the canonical direct evaluation flow.
- [`examples/01_architecture.ipynb`](examples/01_architecture.ipynb): Client, Engine, and Gateway
  boundaries.
- [`examples/03_fusions.ipynb`](examples/03_fusions.ipynb): immutable Model and Fusion authoring.

The notebooks are deterministic outputs of `scripts/build_notebooks.py`.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
uv run --extra notebook python scripts/check_notebooks.py
uv build
uv run python scripts/check_distribution.py
```
