"""Build the Phase 5D ScreamingFace discovery notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free discovery walkthrough."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · discover models and benchmarks

Discover what this ScreamingFace setup can run without mixing discovery with execution. Models and
benchmarks intentionally come from different places:

- executable model IDs come from the configured engine;
- canonical benchmark IDs come from the installed SDK.

This notebook shows both lists and their shared filters, then makes the separate benchmark-loading
boundary explicit.

## Before you run it

Start the local development stack from the repository root:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

Docker is the only prerequisite for the default run. Listing models does not call them, so no
provider credentials are needed. Benchmark source loading is shown later but remains disabled."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Configure the engine"),
        nbformat.v4.new_code_cell(
            "import os\n\n"
            "import screamingface as sf\n\n"
            'ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404")\n'
            "sf.config(engine=ENGINE_URL)"
        ),
        nbformat.v4.new_markdown_cell(
            """`sf.config(...)` selects the one engine used by model discovery and later model
execution. It validates and stores the HTTP(S) origin but does not make a request itself."""
        ),
        nbformat.v4.new_markdown_cell("## 2 · List executable models"),
        nbformat.v4.new_code_cell("model_ids = sf.models.list()\nmodel_ids"),
        nbformat.v4.new_markdown_cell(
            """`sf.models.list()` asks the configured engine for its current capability registry
and returns executable model IDs in registry order. These are routes the engine knows how to run.

Discovery does not call a model and does not prove that provider credentials are connected. A
listed route can still fail at execution time if its provider is unavailable or unauthenticated."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Filter the model IDs"),
        nbformat.v4.new_code_cell(
            'gemini_models = sf.models.list(query="gemini")\n'
            'web_search_models = sf.models.list(tools=("web_search",))\n'
            "first_two_models = sf.models.list(limit=2)\n\n"
            "{\n"
            '    "query=gemini": gemini_models,\n'
            '    "tools=web_search": web_search_models,\n'
            '    "limit=2": first_two_models,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The filters are small and predictable:

- `query` is a case-insensitive substring match on the model ID;
- `tools` keeps routes that advertise every requested tool; and
- `limit` returns a stable prefix after filtering.

Here, `web_search` means the engine route advertises that named executable capability. It does not
mean the model learned web content during training, and it does not validate provider access."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · List installed benchmarks"),
        nbformat.v4.new_code_cell("benchmark_ids = sf.benchmarks.list()\nbenchmark_ids"),
        nbformat.v4.new_markdown_cell(
            """`sf.benchmarks.list()` reads the canonical definitions shipped by the installed SDK.
It does not contact the engine or download benchmark rows. Like model discovery, it deliberately
returns plain IDs rather than introducing a second summary or metadata object."""
        ),
        nbformat.v4.new_markdown_cell("## 5 · Filter the benchmark IDs"),
        nbformat.v4.new_code_cell(
            'gpqa_matches = sf.benchmarks.list(query="gpqa")\n'
            'web_research_benchmarks = sf.benchmarks.list(tools=("web_search",))\n'
            "first_benchmark = sf.benchmarks.list(limit=1)\n\n"
            "{\n"
            '    "query=gpqa": gpqa_matches,\n'
            '    "tools=web_search": web_research_benchmarks,\n'
            '    "limit=1": first_benchmark,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The parameter names match model discovery, but `tools` describes a different side
of compatibility. For models it means capabilities the route supports; for benchmarks it means
capabilities the benchmark requires from each answer-producing Fusion member."""
        ),
        nbformat.v4.new_markdown_cell("## 6 · Listing is not loading"),
        nbformat.v4.new_markdown_cell(
            """A benchmark ID is enough to select a definition, but it is not the dataset.
`sf.benchmarks.load("gpqa@1")` asks the installed definition to fetch and validate its pinned
source, then returns an immutable `sf.Benchmark` ready for execution.

GPQA is gated on Hugging Face. Log in in the researcher process before enabling the next cell:

```bash
huggingface-cli login
```

The Hugging Face token stays with the researcher process. Neither screamingface-engine nor AI
Gateway receives it."""
        ),
        nbformat.v4.new_code_cell(
            "LOAD_GPQA = False\n\n"
            "loaded_gpqa = None\n"
            "if LOAD_GPQA:\n"
            '    loaded_gpqa = sf.benchmarks.load("gpqa@1")\n\n'
            "loaded_gpqa"
        ),
        nbformat.v4.new_markdown_cell(
            """The default value performs no dataset request and invents no substitute benchmark.
Set `LOAD_GPQA = True` only after authenticating if you want to materialize and validate all pinned
GPQA cases.

## Recap

- configure one engine with `sf.config(...)`;
- use `sf.models.list(...)` for model routes executable by that deployment;
- use `sf.benchmarks.list(...)` for canonical definitions installed in the SDK;
- both list APIs return plain IDs and accept `query`, `tools`, and `limit`;
- listing a benchmark is local and network-free; loading can fetch its pinned source; and
- discovery performs no Fusion, model, grader, or aggregation work.

Continue to the quickstart to compose and evaluate a Fusion, or the architecture notebook to inspect
the registry and URL4 HTTP boundary."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"discovery-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output or Path(__file__).parents[1] / "examples" / "02_discovery.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
