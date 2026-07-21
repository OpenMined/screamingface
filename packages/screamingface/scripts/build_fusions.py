"""Build the Phase 5E ScreamingFace Fusion construction notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free Fusion construction walkthrough."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · compose Fusions

Build reusable answer recipes without running them. A Fusion can call one model directly or
combine the answers of other Fusions.

Construction and `.url4` compilation are entirely network-free. This notebook needs no Docker,
provider credentials, or benchmark data."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Start with model IDs"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "frontier_fusion = sf.Fusion(\n"
            '    "frontier-trio",\n'
            "    inputs=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini/2.5-flash",\n'
            '        "claude/sonnet-4.6",\n'
            "    ],\n"
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "frontier_fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """Use model-ID strings by default. Each string is shorthand for an anonymous atomic
Fusion using the minimal prompt `Answer the question.`. The list preserves stable input order.

`MajorityVote()` selects the most common exact answer. Ties resolve by stable member order, and the
reducer makes no additional model call."""
        ),
        nbformat.v4.new_markdown_cell("## 2 · Inspect the public authoring values"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "inputs": frontier_fusion.inputs,\n'
            '    "model_ids": frontier_fusion.model_ids,\n'
            '    "reducer": frontier_fusion.reducer,\n'
            '    "url4": frontier_fusion.url4,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """These four values are enough to inspect or share the definition:

- `inputs` preserves the concise strings and explicit input Fusions;
- `model_ids` provides the ordered route IDs alone;
- `reducer` is the immutable reduction strategy; and
- `url4` is the canonical recipe with its `$question` input still unbound.

Reading any of them remains network-free."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Configure an atomic Fusion explicitly"),
        nbformat.v4.new_code_cell(
            "scientist = sf.Fusion(\n"
            '    "gemini-scientist",\n'
            '    model="gemini/2.5-flash",\n'
            '    prompt="Check the scientific reasoning and answer directly.",\n'
            '    params={"temperature": 0.2, "max_tokens": 512},\n'
            ")\n\n"
            "specialist_fusion = sf.Fusion(\n"
            '    "specialist-pair",\n'
            '    inputs=["codex/gpt-5.5", scientist],\n'
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "specialist_fusion.inputs"
        ),
        nbformat.v4.new_markdown_cell(
            """An atomic Fusion owns one model call and may define its own prompt and parameters.
Use it anywhere an input needs more than the string shorthand.

Each parameter value must be a string, integer, finite float, or boolean. `tools` is reserved: tool
requirements belong to the benchmark so ScreamingFace can apply them consistently to every
answer-producing member."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · The same model can be more than one member"),
        nbformat.v4.new_code_cell(
            'SELF_MODEL = "claude/sonnet-4.6"\n\n'
            "sample_1 = sf.Fusion(\n"
            '    "claude-sample-1",\n'
            "    model=SELF_MODEL,\n"
            '    prompt="Solve independently and favor precise evidence.",\n'
            '    params={"temperature": 0.2},\n'
            ")\n"
            "sample_2 = sf.Fusion(\n"
            '    "claude-sample-2",\n'
            "    model=SELF_MODEL,\n"
            '    prompt="Challenge the obvious answer and check alternatives.",\n'
            '    params={"temperature": 0.8},\n'
            ")\n\n"
            "self_fusion = sf.Fusion(\n"
            '    "claude-independent-samples",\n'
            "    inputs=[sample_1, sample_2],\n"
            "    reducer=sf.reducers.Model(\n"
            '        model="codex/gpt-5.5",\n'
            '        prompt="Synthesize the strongest supported answer from the panel.",\n'
            '        params={"temperature": 0.0, "max_tokens": 512},\n'
            "    ),\n"
            ")\n\n"
            "self_fusion.model_ids"
        ),
        nbformat.v4.new_markdown_cell(
            """Members are positions in the panel, not unique model names. Repeating a route is
therefore valid: the two Claude members become separate ordered requests with separate prompts and
parameters.

`reducers.Model(...)` makes one additional model call. It receives the original question plus
every labeled input answer and synthesizes the Fusion answer. Reusing the same atomic Fusion object
elsewhere reuses its answer node; constructing another one creates an independent sample."""
        ),
        nbformat.v4.new_markdown_cell("## 5 · Inspect the self-Fusion recipe"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "inputs": self_fusion.inputs,\n'
            '    "model_ids": self_fusion.model_ids,\n'
            '    "reducer": self_fusion.reducer,\n'
            '    "url4": self_fusion.url4,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The recipe records the ordered member calls and the reducer call, but it still does
nothing until a concrete question is supplied through execution.

## What construction does not prove

Fusion construction validates the local value shape only. It cannot establish that a configured
engine advertises these routes, supports a benchmark's required tools, or has working provider
credentials. That compatibility is checked when execution begins.

## Recap

- prefer model-ID strings for ordinary anonymous inputs;
- use an atomic Fusion for a named prompt or parameters;
- input order is stable and model IDs may repeat;
- `MajorityVote()` is deterministic and adds no model call;
- `Model(...)` makes one additional synthesis call; and
- construction plus `.url4` inspection are network-free.

Continue to the quickstart to evaluate a Fusion or to the custom-benchmark guide to define your own
cases and scoring contract."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"fusions-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "03_fusions.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
