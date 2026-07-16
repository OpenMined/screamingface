"""Build the reviewable OME-400 quickstart notebook and optionally execute it."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    cells = [
        nbformat.v4.new_markdown_cell(
            """# screamingface · Quickstart

Compose several AI models into one **fusion**, run it on a benchmark sample, and see whether the
panel beats its strongest member. Connect → pick → compose → run → compare, in five small cells.

This checked-in run is an explicit **SIMULATION**: it uses 20 synthetic, GPQA-shaped science
questions and deterministic local model adapters, so GitHub can render a safe and reproducible
example. It is not a provider benchmark and it does not use or reveal gated GPQA questions.

For a real run, start AI Gateway and replace the setup call below with `sf.setup()`. Gateway login
unlocks your encrypted credential vault; provider authorization separately enables model calls.
The setup panel shows each loaded provider's supported methods and offers OAuth, an API key, or
both. Real GPQA also requires accepting the dataset's Hugging Face terms. Live mode never silently
falls back to simulation.

When running from a repository checkout, launch this notebook with
`uv run --extra notebook jupyter lab examples/00_quickstart.ipynb`, or select the interpreter at
`packages/screamingface/.venv/bin/python` in your editor."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Connect"),
        nbformat.v4.new_code_cell(
            "import sys\n\n"
            "import screamingface as sf\n\n"
            'if not hasattr(sf, "setup"):\n'
            "    raise RuntimeError(\n"
            '        "Wrong notebook kernel: select packages/screamingface/.venv/bin/python "\n'
            '        "or launch Jupyter with `uv run --extra notebook jupyter lab`. "\n'
            '        f"Current Python: {sys.executable}"\n'
            "    )\n\n"
            'session = sf.setup(mode="mock", static_widgets=True)\n'
            "session"
        ),
        nbformat.v4.new_markdown_cell("## 2 · Pick models"),
        nbformat.v4.new_code_cell("available = sf.models.list(max_price=20)\navailable"),
        nbformat.v4.new_markdown_cell("## 3 · Compose a URL4-backed fusion"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "frontier-trio",\n'
            "    models=available[:3],\n"
            '    reduce="majority_vote",\n'
            "    judge=available[0],\n"
            ")\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            "The normal display keeps the recipe readable. Ask for the canonical, shareable "
            "URL4 explicitly:"
        ),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            """## 4 · Run

Each member answers each question exactly once through an embedded URL4 node — the `url4`
package's node facade running inside this process, with no extra server to start. The fusion vote
and best-member baseline reuse those same answers, so the comparison does not spend twice. In live
mode, evaluation first checks that every required provider is connected and every model is
available. A blocked run fails once with `FusionNotReady` before loading benchmark data or making
model calls."""
        ),
        nbformat.v4.new_code_cell('run = fusion.evaluate("gpqa", first=20, seed=0)\nrun'),
        nbformat.v4.new_markdown_cell("## 5 · Compare"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "mode": run.mode,\n'
            '    "provenance": run.dataset_source,\n'
            '    "sample_size": run.sample_size,\n'
            '    "score": run.score,\n'
            '    "baseline": run.baseline,\n'
            '    "gain": run.gain,\n'
            '    "cost_usd": run.cost_usd,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """> **Interpretation:** gain is the fusion score minus the strongest member score,
using the same panel answers. The number above demonstrates the SDK flow only; because this
checked-in execution is simulated, it is not evidence that these named providers achieve these
scores on GPQA.

**Next:** keep a lineup in a reviewable file with the YAML companion,
[`yaml_quickstart.ipynb`](yaml_quickstart.ipynb) — or share this exact fusion by sending its
`fusion.url4` recipe."""
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
        document = NotebookClient(document, timeout=120, kernel_name="python3").execute()
        for cell in document.cells:
            cell.metadata.pop("execution", None)
        document.metadata["language_info"] = {"name": "python", "version": "3.12"}
    nbformat.write(document, target)


if __name__ == "__main__":
    main()
