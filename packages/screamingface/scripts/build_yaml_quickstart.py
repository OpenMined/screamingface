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
run the same evaluation flow as the main quickstart.

This committed copy runs in mock mode, fully offline. For a live run, replace the setup call with
`sf.setup()` and put exact IDs from your live `sf.models.list()` into `fusion.yaml` — see the
going-live checklist in [`00_quickstart.ipynb`](00_quickstart.ipynb).

Model IDs are exact, never aliases: `hf/...` is not expanded to `huggingface/...`."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Start a reproducible session"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "# REMOVE mode and static_widgets to run live: sf.setup()\n"
            'session = sf.setup(mode="mock", static_widgets=True)\n'
            "session"
        ),
        nbformat.v4.new_markdown_cell("## 2 · Check the exact model IDs"),
        nbformat.v4.new_code_cell("available = sf.models.list()\navailable"),
        nbformat.v4.new_markdown_cell(
            f"""## 3 · Review `fusion.yaml`

The file sits beside this notebook; loading it runs nothing.

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
            """Loading a fusion needs no connected providers; live evaluation validates them up
front and fails fast with `FusionNotReady` before any call.

Ask for the shareable URL4 recipe when you need it:"""
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
            """Read `gain` first: positive means the fusion beat its strongest member on the same
answers."""
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
            """**Next:** [`00_quickstart.ipynb`](00_quickstart.ipynb) — the same flow with an
inline Python lineup."""
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
