"""Build the bare-bones ScreamingFace quickstart notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    cells = [
        nbformat.v4.new_markdown_cell(
            """# screamingface · Quickstart

Compose three models, evaluate their majority vote, and check whether the fusion beats its best
member.

This quickstart uses deterministic model routes through the real local URL4 engine. Start it from
`packages/screamingface`, then run the notebook:

```bash
./scripts/dev-url4.sh
```

To fetch GPQA Diamond instead of the bundled fixture, first accept its gated dataset terms and be
logged in to Hugging Face, then select the live dataset with `sf.config(mode="live")`. Your URL4
engine must also expose production-backed model routes."""
        ),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "# Optional: point the SDK at a hosted engine instead of the localhost default.\n"
            '# sf.config("https://url4.example")'
        ),
        nbformat.v4.new_markdown_cell("## 1 · Compose"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "frontier-trio",\n'
            "    models=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini-cli/gemini-2.5-pro",\n'
            '        "anthropic/claude-sonnet-4-6",\n'
            "    ],\n"
            '    reducer=sf.MajorityVote(tie_breaker="codex/gpt-5.5"),\n'
            ")\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """Every fusion has a shareable URL4 recipe. Displaying it does not execute it."""
        ),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell("## 2 · Run"),
        nbformat.v4.new_code_cell('run = fusion.evaluate("gpqa", first=20, seed=0)\nrun'),
        nbformat.v4.new_markdown_cell("## 3 · Compare"),
        nbformat.v4.new_code_cell(
            "run.score, run.baseline, run.gain  # fusion, best member, improvement"
        ),
        nbformat.v4.new_markdown_cell(
            """> Positive gain means the fusion outperformed its strongest individual member.

For the exact URL4 HTTP request and compiled-node walkthrough, open
[`sf_url4_engine.ipynb`](sf_url4_engine.ipynb)."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"quickstart-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "00_quickstart.ipynb"
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
