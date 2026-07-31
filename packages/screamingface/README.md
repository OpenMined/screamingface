# screamingface

Evaluate Models and Fusions against URL4-native research Benchmarks.

> **Development status:** immutable Model/Fusion authoring, Engine-backed discovery, the direct
> evaluation API, Model/Fusion URL4 compilation, and the confirmed `url4-cloud` lifecycle are
> implemented. The current Engine installs real-model `draco-smoke` as its safe default and
> exposes `draco-lite` as an explicit higher-fidelity tier. Broader production Benchmark manifests
> remain Engine contract gates. There is no fixture, stale registry, or embedded execution
> fallback.

## Target v1 workflow

The approved Python workflow is:

```python
import screamingface as sf

sf.connect()  # notebook panel; connect the Engine's OpenRouter account once

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier_pair = sf.Fusion(
    [opus, gpt],
    name="frontier-pair",
)

report = sf.evaluate(
    [opus, gpt, frontier_pair],
    limit=1,
)
```

`evaluate(...)` uses the Engine's explicitly declared default Benchmark, validates every
Candidate, compiles one complete URL4 per Candidate, executes those independent Candidates
concurrently, and returns one immutable `Report` in declared order. Pass
`benchmark="draco-lite"` only when overriding the safe smoke default. All no-spend validation
finishes before the first paid Run starts. The complete example becomes runnable when the SF
Engine requirements
listed in
[`../../docs/spec/2026-07-26-OME-605-engine-requirements.md`](../../docs/spec/2026-07-26-OME-605-engine-requirements.md)
are published.

Model and Fusion Candidates compile against the provisional Benchmark manifest contract.
Unsupported Candidates fail with typed errors instead of falling back to Client-side execution.

## Install

```bash
pip install screamingface
```

Python 3.12 or newer is required.

## Engine configuration

The module-level interface constructs one process-wide Client lazily. Set the Engine URL before
the first catalogue, connection, or evaluation operation only when overriding the local default:

```python
import os

os.environ["SCREAMINGFACE_ENGINE_URL"] = "https://engine.screamingface.ai"

import screamingface as sf

report = sf.evaluate(candidates, limit=1)
```

The Client hides Benchmark resolution, URL4 compilation, REST/WebSocket transport, Event replay,
and Report decoding behind `sf.evaluate(...)`.

In a notebook, `sf.connect()` displays the provider panel bound to the lazy default Client. The
current Engine advertises one OpenRouter API-key row. The key is sent only to the SF Engine, which
asks AI Gateway to validate and store it; the Python Client does not persist it and never calls AI
Gateway or OpenRouter directly.

```python
sf.connect()
sf.connections.list()
sf.connections.get("openrouter")
sf.disconnect("openrouter")
```

The same panel retains the OAuth, pending, authorization, cancellation, and reauthentication UI
states for Engines that advertise those methods later. They do not add a second connection path:
the Engine catalogue remains authoritative.

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


report = sf.evaluate(
    candidates,
    limit=1,
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

Models and Fusions are immutable, Client-independent, and network-free. Models select routes;
Fusions declare topology. Benchmarks are immutable Engine protocols that own answer policy,
synthesis, cases, judge configuration, grading, aggregation, Tools, and execution policy.

Equivalent resolved Model calls deduplicate by content inside a compiled Candidate graph.
Explicit Model names identify intentional independent samples. Durable reuse across Candidates,
retries, and resumed Evaluations belongs to the Engine's provenance-aware response cache.

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
- [`examples/05_draco_lite_e2e.ipynb`](examples/05_draco_lite_e2e.ipynb): one-case local
  DRACO-Lite vertical slice.
- [`examples/06_draco_full_e2e.ipynb`](examples/06_draco_full_e2e.ipynb): the complete seven-solo,
  nine-Fusion DRACO experiment ported from `screamingface-benchmarks` to the Client SDK.

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
