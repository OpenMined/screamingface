"""Build the Phase 1 ScreamingFace engine-profile walkthrough notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace Phase 1 · discover, load, author

Connect the SDK to the temporary `screamingface-engine` development profile, inspect what the engine
advertises, and construct the immutable values used by later execution phases.

**This is the Phase 1 discovery walkthrough—not the product quickstart.** It covers engine
configuration, engine model discovery, SDK benchmark discovery and loading, local benchmark
definitions, and Fusion authoring. It deliberately does not call the model routes. SDK Fusion
execution now exists in Phase 2C, but remains outside this discovery-focused walkthrough.

## Before you run it

From the repository root, start the tracked local stack:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

This starts the URL4 engine at `http://127.0.0.1:4404` and AI Gateway at
`http://127.0.0.1:9105`. Model discovery uses the URL4 engine; only an executable model route
contacts AI Gateway. Only one development stack can own those ports, so
stop any earlier URL4 or AI Gateway containers before running `./dev.sh`.

Canonical datasets are loaded in this Python process, never by the engine. Before loading GPQA,
accept its dataset terms and authenticate this environment:

```bash
huggingface-cli login
```

There is no synthetic or in-process fallback."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Point the SDK at the engine"),
        nbformat.v4.new_code_cell(
            "import json\n"
            "import os\n\n"
            "import httpx\n"
            "\n"
            "import screamingface as sf\n\n"
            'ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404")\n'
            "sf.config(engine=ENGINE_URL)\n\n"
            "# This is currently also the SDK default, so configuration is optional locally.\n"
            'httpx.get(f"{ENGINE_URL}/healthz", timeout=5).text'
        ),
        nbformat.v4.new_markdown_cell(
            """`sf.config(...)` only stores and validates the URL. It does not perform a request.
The health check above is the first network call in this notebook. A future hosted deployment can
be selected with the same API:

```python
sf.config(engine="https://url4.example")
```"""
        ),
        nbformat.v4.new_markdown_cell("## 2 · Inspect the ScreamingFace registry"),
        nbformat.v4.new_code_cell(
            'registry_response = httpx.get(f"{ENGINE_URL}/.well-known/screamingface", timeout=5)\n'
            "registry_response.raise_for_status()\n\n"
            "{\n"
            '    "content_type": registry_response.headers["content-type"],\n'
            '    "plaintext_preview": registry_response.text[:120] + "…",\n'
            "}"
        ),
        nbformat.v4.new_code_cell("registry = json.loads(registry_response.text)\nregistry"),
        nbformat.v4.new_markdown_cell(
            """The URL4 node returns plaintext. The SDK parses that text and validates the complete
`screamingface.registry.v1` shape before exposing IDs. Model entries describe executable route
identities and supported tools; reducer entries describe executable composition routes. The
required `limits.max_request_target_bytes` value tells the SDK how large a fully encoded
`/v1?q=...` request target this deployment accepts. Benchmarks are absent because their
definitions and data remain local to the SDK."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Discover available models and benchmarks"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "all_models": sf.models.list(),\n'
            '    "gemini_models": sf.models.list(query="gemini"),\n'
            '    "web_search_models": sf.models.list(tools=["web_search"]),\n'
            '    "benchmarks": sf.benchmarks.list(),\n'
            '    "research_benchmarks": sf.benchmarks.list(tools=["web_search"]),\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The two lists answer different questions:

- `sf.models.list()` asks the configured engine what it can execute.
- `sf.benchmarks.list()` asks the installed SDK which canonical definitions it can load.

Neither list infers provider authentication. The current Compose profile advertises `web_search`
for Gemini and Claude because its private SearXNG adapter is configured; Codex remains tool-free.
The installed SDK catalog contains `gpqa@1` and `draco@1`, and the research filter selects DRACO
because that benchmark requires `web_search`."""
        ),
        nbformat.v4.new_markdown_cell(
            "## 4 · Load a canonical benchmark when dataset access is ready"
        ),
        nbformat.v4.new_code_cell(
            "# Change this after this Python environment can access the gated dataset.\n"
            "LOAD_CANONICAL_BENCHMARK = False\n\n"
            'benchmark = sf.benchmarks.load("gpqa@1") if LOAD_CANONICAL_BENCHMARK else None\n\n'
            "benchmark or (\n"
            '    "Set LOAD_CANONICAL_BENCHMARK = True to fetch and validate GPQA through "\n'
            '    "this process\'s Hugging Face access."\n'
            ")"
        ),
        nbformat.v4.new_markdown_cell(
            """`sf.benchmarks.load("gpqa@1")` is eager:

1. select the pinned definition installed with this SDK version;
2. fetch the canonical dataset through the caller's Hugging Face session;
3. validate all source rows and normalize them into stable `sf.Case` values; and
4. return one immutable `sf.Benchmark` with its local grader and aggregator.

Invalid source rows and unknown benchmark IDs remain typed errors. Loading never calls the URL4
engine, a panel model, or AI Gateway. Answer keys therefore never need to be published by the
engine."""
        ),
        nbformat.v4.new_markdown_cell("## 5 · Define a small benchmark in ordinary Python"),
        nbformat.v4.new_code_cell(
            "arithmetic = sf.Benchmark(\n"
            '    "arithmetic-smoke-test",\n'
            '    title="Arithmetic smoke test",\n'
            "    cases=[\n"
            "        sf.Case(\n"
            '            "addition",\n'
            '            "What is 2 + 2?\\n\\nA. 3\\nB. 4\\n\\nReply with only A or B.",\n'
            '            reference="B",\n'
            '            metadata={"subject": "arithmetic"},\n'
            "        ),\n"
            "        sf.Case(\n"
            '            "multiplication",\n'
            '            "What is 3 × 3?\\n\\nA. 9\\nB. 6\\n\\nReply with only A or B.",\n'
            '            reference="A",\n'
            '            metadata={"subject": "arithmetic"},\n'
            "        ),\n"
            "    ],\n"
            "    grader=sf.graders.ExactChoice(),\n"
            "    aggregator=sf.aggregators.Mean(),\n"
            ")\n"
            "arithmetic"
        ),
        nbformat.v4.new_markdown_cell(
            """Dataset cleaning stays in ordinary Python. ScreamingFace begins at stable `sf.Case`
values: one input, a sealed JSON reference used only for grading, and optional reporting metadata.
The SDK intentionally does not add an ETL language or case-browser abstraction."""
        ),
        nbformat.v4.new_markdown_cell("## 6 · Author a Fusion without executing it"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "frontier-trio",\n'
            "    models=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini/2.5",\n'
            '        "claude/sonnet-4.6",\n'
            "    ],\n"
            '    prompt="Answer the question carefully: $question",\n'
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "{\n"
            '    "name": fusion.name,\n'
            '    "models": fusion.models,\n'
            '    "model_ids": fusion.model_ids,\n'
            '    "reducer": fusion.reducer,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """Construction is local and network-free. Strings are the concise model form; a model
mapping can add a per-member `prompt` or scalar `params`. Reducers are typed strategies under
`sf.reducers`; graders and aggregators follow the same namespaced convention.

The public values in this notebook are immutable. That makes benchmark definitions and Fusion
recipes safe to inspect and pass between later execution stages."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Phase 1 boundary

You have now exercised everything Phase 1 promises:

- configure one URL4 engine;
- inspect and validate its ScreamingFace registry;
- list engine models and installed SDK benchmarks with filters;
- optionally load canonical benchmark data through the researcher's own access;
- define a local benchmark with the same public types; and
- author an immutable Fusion.

This walkthrough deliberately stops before `fusion.run(...)`. The implemented runtime supplies
persistent model routes, the deterministic majority-vote route, `GET /v1?q=...`, SDK URL4
compilation, plaintext result validation, in-memory runs, grading, aggregation, and
`fusion.evaluate(...)`; those later stages remain outside this discovery-focused notebook.
All model-backed SDK work continues to contact only the URL4 engine; only the engine's model
adapter may contact AI Gateway."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"phase1-profile-{index:02d}"
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
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output or Path(__file__).parents[1] / "examples" / "phase_1_engine_profile.ipynb"
    document = notebook()
    if args.execute:
        document = NotebookClient(
            document,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(target.parent)}},
        ).execute()
        for cell in document.cells:
            cell.metadata.pop("execution", None)
        document.metadata.pop("widgets", None)
        document.metadata["language_info"] = {"name": "python", "version": "3.12"}
    nbformat.write(document, target)


if __name__ == "__main__":
    main()
