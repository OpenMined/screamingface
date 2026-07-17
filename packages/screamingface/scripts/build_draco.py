"""Build the ScreamingFace-native DRACO benchmark notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    cells = [
        nbformat.v4.new_markdown_cell(
            """# DRACO with the ScreamingFace SDK

Build an open-ended research fusion, execute every model through URL4, and compare its weighted
DRACO rubric score with the same panel members scored individually.

The saved run uses two bundled DRACO-shaped cases and deterministic URL4 routes. Start the local
engine from `packages/screamingface` before running:

```bash
./scripts/dev-url4.sh
```

This notebook locks down the SDK workflow, not a publishable DRACO reproduction. The final section
spells out what production evaluation additionally requires."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Import and configure"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "# Optional: point every model and judge call at another URL4 engine.\n"
            '# sf.config("https://url4.example")'
        ),
        nbformat.v4.new_markdown_cell(
            """## 2 · Define the research behavior

These prompts belong to the experiment, not the DRACO dataset adapter. `$question` is resolved for
each case. The reducer additionally receives the labeled `$panel_answers` produced by URL4."""
        ),
        nbformat.v4.new_code_cell(
            'DRACO_PANEL_PROMPT = """\n'
            "You are answering a research-quality prompt. Provide a thorough, "
            "well-reasoned answer\n"
            "in prose. Address every aspect, preserve specific facts and sources, and use clear\n"
            "structure.\n\n"
            "Research prompt:\n"
            '$question\n""".strip()\n\n'
            'DRACO_REDUCER_PROMPT = """\n'
            "Produce one comprehensive answer to the research prompt by combining the strongest\n"
            "facts, arguments, and citations from every labeled panel answer. Resolve "
            "disagreements\n"
            "in favor of the more specific and better-supported claim. Return only the "
            "unified prose\n"
            "answer.\n\n"
            "Research prompt:\n"
            "$question\n\n"
            "Panel answers:\n"
            '$panel_answers\n""".strip()'
        ),
        nbformat.v4.new_markdown_cell("## 3 · Compose the fusion"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "draco-frontier-trio",\n'
            "    models=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini-cli/gemini-2.5-pro",\n'
            '        "anthropic/claude-sonnet-4-6",\n'
            "    ],\n"
            "    prompt=DRACO_PANEL_PROMPT,\n"
            "    reducer=sf.ModelReducer(\n"
            '        model="codex/gpt-5.5",\n'
            "        prompt=DRACO_REDUCER_PROMPT,\n"
            '        params={"temperature": 0.0, "max_tokens": 8192},\n'
            "    ),\n"
            ")\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """The shareable fusion URL4 contains the unresolved panel and reducer graph. It does
not contain the DRACO dataset or rubric, and displaying it executes nothing."""
        ),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            """## 4 · Evaluate

For each case, ScreamingFace sends one fusion expression to `/v1`. After receiving the panel and
synthesized answers, the DRACO grader sends one additional URL4 model request for every
answer × rubric criterion × judge pass. No SDK code calls AI Gateway or a provider directly."""
        ),
        nbformat.v4.new_code_cell('run = fusion.evaluate("draco", first=2, seed=0)\nrun'),
        nbformat.v4.new_markdown_cell("## 5 · Read the comparison"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "primary_metric": run.primary_metric,\n'
            '    "fusion_score": run.score,\n'
            '    "best_member": run.baseline,\n'
            '    "gain": run.gain,\n'
            '    "rubric_metrics": dict(run.metrics),\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """`normalized_score` is DRACO's weighted score: positive criteria add their weights,
MET negative criteria subtract their weights, and the result is divided by total positive weight
and clamped to 0–100. `gain` compares the synthesis with the best panel member on the same cases
and judge protocol.

## 6 · Moving from this repeatable example to a DRACO reproduction

Use `sf.config(mode="live")` to load the public `perplexity-ai/draco` test split (install the
`datasets` extra first). A publishable run also needs:

- production URL4 model routes backed by the same AI Gateway configuration;
- research tools and tool budgets comparable across every panel member;
- the pinned production judge and five independent per-criterion judge passes;
- final byte-level agreement on the paper's judge prompt and model parameters;
- usage, cost, failure, and judge-coverage telemetry from the engine.

The SDK-side shape remains the same: user-authored `Fusion` prompts plus
`fusion.evaluate("draco", ...)`."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"draco-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "draco.ipynb"
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
            if "outputs" in cell:
                cell.outputs = [
                    output
                    for output in cell.outputs
                    if "application/vnd.jupyter.widget-view+json" not in output.get("data", {})
                ]
        document.metadata.pop("widgets", None)
        document.metadata["language_info"] = {"name": "python", "version": "3.12"}
    nbformat.write(document, target)


if __name__ == "__main__":
    main()
