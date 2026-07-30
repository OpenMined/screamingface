"""Build the public v1 notebooks deterministically."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat import NotebookNode


def notebooks() -> dict[str, NotebookNode]:
    return {
        "00_quickstart.ipynb": _quickstart(),
        "01_architecture.ipynb": _architecture(),
        "03_fusions.ipynb": _fusions(),
        "05_draco_lite_e2e.ipynb": _draco_lite_e2e(),
    }


def _notebook(*cells: NotebookNode) -> NotebookNode:
    for index, cell in enumerate(cells, 1):
        cell["id"] = f"cell-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=list(cells),
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
    )


def _quickstart() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace Candidate authoring

Build immutable Model and Fusion Candidates without network access."""
        ),
        nbformat.v4.new_code_cell(
            """import screamingface as sf

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier_pair = sf.Fusion(
    "frontier-pair",
    members=[opus, gpt],
    reducer=sf.reducers.Synthesis(
        "openrouter/anthropic/claude-opus-4.8",
    ),
)

candidates = [opus, gpt, frontier_pair]"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluation status

The approved target workflow is:

```python
with sf.Client() as client:
    report = client.evaluate(candidates, benchmark="draco", limit=1)
```

It is deliberately not executed in this authoring notebook. The Client performs Benchmark
resolution, validation, URL4 compilation, execution, and Report decoding behind this one
operation. The Client provides no fixture-backed or legacy fallback."""
        ),
    )


def _architecture() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# Client architecture

```text
Researcher or SF App
        ↓
ScreamingFace Python Client
  Recipes · URL4 compilation · Events · Reports
        ↓  REST + WebSocket
SF Engine
  URL4 execution · Benchmarks · grading · aggregation · Tools
        ↓
AI Gateway
  provider credentials · model dispatch
```

The Client talks only to its configured SF Engine. Local and hosted Engines expose the same
Client-visible contract; their internal transport and deployment topology are not Client APIs.

The code below shows the approved direct evaluation interface. Engine contract gates are listed in
the package README."""
        ),
        nbformat.v4.new_code_cell(
            """import screamingface as sf

client = sf.Client(
    engine_url="https://engine.screamingface.ai",
)

client.engine_url"""
        ),
        nbformat.v4.new_markdown_cell(
            """`Client` and `AsyncClient` own transport resources and support deterministic
context-manager cleanup. Paid evaluation always uses an explicit Client."""
        ),
        nbformat.v4.new_code_cell(
            """async def run_draco(candidates):
    async with sf.AsyncClient() as client:
        return await client.evaluate(candidates, benchmark="draco", limit=1)"""
        ),
    )


def _fusions() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# Models and Fusions

Models and Fusions are immutable, network-free Recipe values. Reusing the same Recipe object
shares its graph node; separately constructed equal-looking Models remain independent samples."""
        ),
        nbformat.v4.new_code_cell(
            """import screamingface as sf

opus = sf.Model(
    "openrouter/anthropic/claude-opus-4.8",
    temperature=0.2,
    reasoning="low",
    max_output_tokens=8192,
)
gpt = sf.Model("openrouter/openai/gpt-5.5")

pair = sf.Fusion(
    "frontier-pair",
    members=[opus, gpt],
    reducer=sf.reducers.Synthesis(
        "openrouter/anthropic/claude-opus-4.8",
        instructions="Combine the strongest supported claims into one answer.",
    ),
)

pair"""
        ),
        nbformat.v4.new_markdown_cell(
            """Tools, judge policy, retries, output policy, and aggregation belong to the Engine's
versioned Benchmark protocol—not to a Model or Fusion."""
        ),
    )


def _draco_lite_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# DRACO-Lite: Client → URL4 Engine → AI Gateway

This notebook exercises the complete local vertical slice:

1. The lazy Client discovers the Engine's Models and Benchmarks.
2. `Client.evaluate(...)` fetches and verifies the DRACO-Lite YAML manifest and constructs one
   flat Candidate URL4 before spending.
3. The Client uses the url4-cloud token and WebSocket lifecycle.
4. The configured URL4 node loads one pinned DRACO case, calls AI Gateway for the answer, runs ten
   rubric judges, aggregates the grades, and returns an `sf.Report`.

> **Cost warning:** the evaluation cell performs one answer call and ten judge calls. Discovery
> makes no model calls."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Before running

The local AI Gateway must be running on `127.0.0.1:9105`, and the isolated Engine demo must be
running on `127.0.0.1:9108`. See `apps/url4-cloud/DRACO_LITE_DEMO.md` in the Engine demo branch for
the exact commands."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell(
            """## Discover the local Engine

These catalogue calls are read-only and make no model requests."""
        ),
        nbformat.v4.new_code_cell("sf.benchmarks.list()"),
        nbformat.v4.new_code_cell("sf.models.list()"),
        nbformat.v4.new_markdown_cell(
            """## Define one Candidate

The demo uses the provider-prefixed Anthropic route currently accepted by the local AI Gateway."""
        ),
        nbformat.v4.new_code_cell(
            '''ANSWER_INSTRUCTIONS = """Answer the research question completely.
Compare the estimators and their assumptions precisely, address pre-trend testing, and cite
specific papers and evidence where useful."""

candidate = sf.Model(
    "anthropic/claude-haiku-4-5",
    instructions=ANSWER_INSTRUCTIONS,
    max_output_tokens=4096,
)

candidate'''
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate the benchmark

Running the next cell makes **11 model calls**: one Candidate answer and ten concurrent
rubric-judge calls. Manifest verification and URL4 compilation happen first; the Client starts no
Candidate Run if that validation fails."""
        ),
        nbformat.v4.new_code_cell(
            """events = []


def on_event(event: sf.Event) -> None:
    events.append(event)
    print(f"{event.sequence:02d} {event.kind}")


with sf.Client() as client:
    report = client.evaluate(
        candidate,
        benchmark="draco-lite",
        limit=1,
        on_event=on_event,
    )
report"""
        ),
        nbformat.v4.new_code_cell("print(report.candidates.only.url4)"),
        nbformat.v4.new_code_cell("report.candidates.only.metrics"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("print(report.to_json())"),
    )


def main() -> None:
    examples = Path(__file__).parents[1] / "examples"
    for name, value in notebooks().items():
        nbformat.write(value, examples / name)


if __name__ == "__main__":
    main()
