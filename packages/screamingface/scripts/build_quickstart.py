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
panel beats its strongest member. Connect → pick → compose → run → compare.

This committed copy runs in mock mode — synthetic questions, deterministic local answers — so it
renders reproducibly on GitHub. The scores demonstrate the flow, not provider quality.

**Going live:** replace the setup call with `sf.setup()` and have three things ready:

1. **AI Gateway** running:
   `cd apps/aigateway && uv sync && uv run uvicorn aigateway.main:app --port 9105`.
   `sf.setup()` finds `http://127.0.0.1:9105`; for any other host, pass `gateway="..."` or set
   `SCREAMINGFACE_GATEWAY_URL`.
2. **Providers connected** in the setup panel, with OAuth or an API key. `sf.models.list()` shows
   models from connected providers.
3. **Hugging Face access** for the real GPQA benchmark: `uv sync --extra datasets`, accept the
   terms at `huggingface.co/datasets/Idavidrein/gpqa`, then `huggingface-cli login`."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Connect"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "# REMOVE mode and static_widgets to run live: sf.setup()\n"
            'session = sf.setup(mode="mock", static_widgets=True)\n'
            "session"
        ),
        nbformat.v4.new_markdown_cell("## 2 · Pick models"),
        nbformat.v4.new_code_cell("available = sf.models.list()\navailable"),
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
        nbformat.v4.new_markdown_cell("Ask for the shareable URL4 recipe when you need it:"),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            """## 4 · Run

Each member answers every question once through an embedded URL4 node; the vote and the
best-member baseline reuse the same answers, so nothing is asked twice. Live runs validate
providers and models up front and fail fast with `FusionNotReady` before any call."""
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
            """> Gain = fusion score − best member, on the same answers. Positive means the panel
beat its strongest member.

**Next:** [`yaml_quickstart.ipynb`](yaml_quickstart.ipynb) keeps the lineup in a file — or share
this fusion by sending `fusion.url4`."""
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
