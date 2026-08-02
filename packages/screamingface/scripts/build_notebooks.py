"""Build the public v1 notebooks deterministically."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat import NotebookNode


def notebooks() -> dict[str, NotebookNode]:
    return {
        "00_quickstart.ipynb": _quickstart(),
        "05_draco_e2e.ipynb": _draco_e2e(),
        "06_draco_full_e2e.ipynb": _draco_full_e2e(),
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
            """# ScreamingFace quickstart

Connect the configured SF Engine, define Candidates, and evaluate them."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Connect OpenRouter

`sf.connect()` renders the Engine-backed provider panel. Entering an API key sends it to the SF
Engine for AI Gateway validation and encrypted storage; the notebook does not retain it."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define Candidates"),
        nbformat.v4.new_code_cell(
            """opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier = sf.Fusion([opus, gpt])"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate

The Engine defaults to DRACO. `limit=1` selects one of its 100 cases, but still evaluates every
criterion in that case with the paper-aligned five Judge passes. The Benchmark owns Judge and
aggregation policy."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    [opus, gpt, frontier],
    limit=1,
    on_event=print,
    progress=False,
)
report"""
        ),
    )


def _draco_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# DRACO smoke run: Client → URL4 Engine → AI Gateway

This notebook exercises the complete pipeline through the public ScreamingFace SDK. The Engine
owns the dataset, judge, grading, and aggregation; the SDK Candidate owns answer policy.

> **Cost warning:** the evaluation cell performs one Candidate call plus five Judge calls for
> every criterion in the selected case. Discovery makes no model calls."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Before running

The local AI Gateway must be running on `127.0.0.1:9105`, and the isolated Engine demo must be
running on `127.0.0.1:9108`. The connection panel sends the OpenRouter key through the Engine to
AI Gateway; the Client never calls AI Gateway directly."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define a Candidate"),
        nbformat.v4.new_code_cell('haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")'),
        nbformat.v4.new_markdown_cell(
            """## Evaluate the benchmark

Running the next cell evaluates one Candidate answer against every rubric criterion, with five
independent Judge calls per criterion."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    haiku,
    benchmark="draco",
    limit=1,
)
report"""
        ),
        nbformat.v4.new_markdown_cell("## Inspect the Report"),
        nbformat.v4.new_code_cell("report.candidates"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("report.to_json()"),
    )


def _draco_full_e2e() -> NotebookNode:
    notebook = _notebook(
        nbformat.v4.new_markdown_cell(
            """# Full DRACO pipeline through the ScreamingFace SDK

This is the SDK-native port of the full `pipeline_walkthrough.ipynb` in
`screamingface-benchmarks/notebooks/general/`.
It preserves the published Candidate surface—**7 solo Models and 9 Fusions**—using only the public
SDK. The Engine owns DRACO's dataset, judge, grading, and aggregation. Each SDK Candidate owns its
answer and synthesis policy.

> **Spend warning:** the evaluation cell is paid. It uses one case per Candidate; remove `limit=1`
> only when you intend to run the complete dataset."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## 1. Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## 2. Define the full solo lineup

These are the seven solo Candidates from the original full-pipelines notebook. Qwen is also
defined because it participates in the open-source Fusion."""
        ),
        nbformat.v4.new_code_cell(
            """fable = sf.Model("openrouter/anthropic/claude-fable-5")
opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")
gemini_pro = sf.Model("openrouter/google/gemini-3.1-pro-preview")
gemini_flash = sf.Model("openrouter/google/gemini-3-flash-preview")
kimi = sf.Model("openrouter/moonshotai/kimi-k2.6")
deepseek = sf.Model("openrouter/deepseek/deepseek-v4-pro")
qwen = sf.Model("openrouter/qwen/qwen3.6-plus")"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 3. Define the nine Fusion Candidates

The Benchmark supplies the synthesizer automatically. Equivalent Models deduplicate across the
graph. The self-Fusion uses explicit sample identities so its two Opus calls remain independent."""
        ),
        nbformat.v4.new_code_cell(
            """fable_plus_gpt = sf.Fusion([fable, gpt])
frontier = sf.Fusion([opus, gpt, gemini_pro])
opus_plus_gpt = sf.Fusion([opus, gpt])
opus_self_fusion = sf.Fusion(
    [
        sf.Model("openrouter/anthropic/claude-opus-4.8", name="opus-sample-1"),
        sf.Model("openrouter/anthropic/claude-opus-4.8", name="opus-sample-2"),
    ]
)
budget = sf.Fusion([gemini_flash, kimi, deepseek])
beat_runner_up = sf.Fusion([opus, gpt, deepseek])
pareto = sf.Fusion([deepseek, kimi, gpt])
pareto_lean = sf.Fusion([deepseek, kimi])
best_open_source = sf.Fusion([deepseek, kimi, qwen])"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 4. Evaluate every Candidate

One lazy SDK call evaluates the complete Candidate lineup against DRACO. Candidates run
concurrently under the Client's internal scheduler; the Benchmark supplies all other execution
policy."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    [
        fable,
        opus,
        gpt,
        gemini_pro,
        gemini_flash,
        kimi,
        deepseek,
        fable_plus_gpt,
        frontier,
        opus_plus_gpt,
        opus_self_fusion,
        budget,
        beat_runner_up,
        pareto,
        pareto_lean,
        best_open_source,
    ],
    benchmark="draco",
    limit=1,
)
report"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 5. Inspect the Report

The Report presents Candidate scores, failures, operation graphs, timing, and usage."""
        ),
        nbformat.v4.new_code_cell("report.candidates"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("report.failures"),
        nbformat.v4.new_code_cell("report.to_json()"),
    )
    notebook.metadata["kernelspec"] = {
        "display_name": "screamingface (SDK)",
        "language": "python",
        "name": "screamingface-sdk",
    }
    return notebook


def main() -> None:
    examples = Path(__file__).parents[1] / "examples"
    for name, value in notebooks().items():
        nbformat.write(value, examples / name)


if __name__ == "__main__":
    main()
