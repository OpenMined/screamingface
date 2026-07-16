"""Build and optionally execute the declarative Fusion YAML quickstart."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    yaml_text = (Path(__file__).parents[1] / "examples" / "fusion.yaml").read_text(encoding="utf-8")
    cells = [
        nbformat.v4.new_markdown_cell(
            """# screamingface · YAML quickstart

Keep a fusion lineup in a small, reviewable YAML file, load it without making model calls, and
run the same URL4-backed evaluation flow as the main quickstart.

This checked-in execution is an explicit **SIMULATION**. It uses the bundled synthetic science
fixture and deterministic local model answers, so it runs offline and makes no provider claims.
For a live run, replace the setup call with `sf.setup()` and update `fusion.yaml` with exact model
IDs returned by that live session's `sf.models.list()`.

Model IDs are not aliases: `hf/...` is not silently expanded to `huggingface/...`, and an
`open_router/...` model is valid only when the connected gateway reports that exact ID."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Start a reproducible session"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            'session = sf.setup(mode="mock", static_widgets=True)\n'
            "session"
        ),
        nbformat.v4.new_markdown_cell("## 2 · Check the exact model IDs"),
        nbformat.v4.new_code_cell("available = sf.models.list()\navailable"),
        nbformat.v4.new_markdown_cell(
            f"""## 3 · Review `fusion.yaml`

The YAML file sits beside this notebook. Loading it is local and safe: it does not execute the
fusion, contact AI Gateway, or reveal the URL4 recipe.

```yaml
{yaml_text.rstrip()}
```"""
        ),
        nbformat.v4.new_markdown_cell("## 4 · Load the fusion and inspect its lineup"),
        nbformat.v4.new_code_cell(
            'fusion = sf.Fusion.from_yaml("fusion.yaml")\n'
            "fusion  # rich lineup table; the URL4 stays hidden"
        ),
        nbformat.v4.new_markdown_cell(
            """Loading and inspecting a fusion does not require connected providers. In live mode,
`evaluate(...)` checks every required provider and model before loading benchmark data. If anything
is missing, it raises one `FusionNotReady` error and makes no model calls.

Ask for the canonical, shareable URL4 only when you need it:"""
        ),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            "The same schema can be supplied as an inline Python mapping:"
        ),
        nbformat.v4.new_code_cell(
            "fusion_config = {\n"
            '    "name": "yaml-trio",\n'
            '    "models": available[:3],\n'
            '    "reduce": "majority_vote",\n'
            '    "judge": available[0],\n'
            "}\n"
            "inline_fusion = sf.Fusion(**fusion_config)\n"
            "inline_fusion.url4 == fusion.url4"
        ),
        nbformat.v4.new_markdown_cell("## 5 · Evaluate and read the result"),
        nbformat.v4.new_code_cell('run = fusion.evaluate("gpqa", first=20, seed=0)\nrun'),
        nbformat.v4.new_markdown_cell(
            """The result card is explicitly simulated. For both simulated and live runs, read
`gain` first: positive means the fusion beat its strongest member using the same panel answers."""
        ),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "score": run.score,\n'
            '    "baseline": run.baseline,\n'
            '    "gain": run.gain,\n'
            '    "mode": run.mode,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """**Next:** [`00_quickstart.ipynb`](00_quickstart.ipynb) walks the same flow with an
inline Python lineup and explains how to switch this notebook to a live run."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"yaml-quickstart-{index:02d}"
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
    package_root = Path(__file__).parents[1]
    examples = package_root / "examples"
    target = args.output or examples / "yaml_quickstart.ipynb"
    document = notebook()
    if args.execute:
        document = NotebookClient(
            document,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(examples)}},
        ).execute()
        for cell in document.cells:
            cell.metadata.pop("execution", None)
        document.metadata["language_info"] = {"name": "python", "version": "3.12"}
    nbformat.write(document, target)


if __name__ == "__main__":
    main()
