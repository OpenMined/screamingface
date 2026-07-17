"""Build the detailed ScreamingFace-to-URL4-engine notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace ↔ URL4 engine

Combine three model routes into one URL4-backed fusion, run it on deterministic benchmark
questions, and measure whether the majority beats the best individual model.

This uses deterministic model routes through the **real URL4 HTTP engine**. Before running the
notebook, start them from `packages/screamingface`:

```bash
./scripts/dev-url4.sh
```

To fetch GPQA Diamond instead of the bundled fixture, first accept its gated dataset terms and be
logged in to Hugging Face, then select the live dataset with `sf.config(mode="live")`. Your URL4
engine must also expose production-backed model routes.

The saved run uses deterministic routes, so its result is reproducible and makes no
provider-quality claim."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Import the SDK"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "# Optional: point the SDK at a hosted engine instead of the localhost default.\n"
            '# sf.config("https://url4.example")'
        ),
        nbformat.v4.new_markdown_cell(
            """## 2 · Compose a fusion — Python or YAML

These are two representations of the same fusion. Use Python while exploring; use YAML when you
want a small configuration file to review or share."""
        ),
        nbformat.v4.new_markdown_cell("### Option A · Python"),
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
            """A plain string is shorthand for `{"model": "provider/model"}`. Mix in a strict
dictionary only when one model needs its own `name`, `prompt`, or URL4 `params`:

```python
models=[
    "openai/gpt-5.5",
    {
        "model": "anthropic/claude-opus-4.8",
        "name": "opus-sample-1",
        "params": {"temperature": 0.7},
    },
]
```

ScreamingFace validates these dictionaries and assigns private call-slot identities. There is no
public `Member` or `Source` wrapper."""
        ),
        nbformat.v4.new_markdown_cell(
            """### Option B · YAML

The equivalent [`fusion.yaml`](fusion.yaml) is:

```yaml
name: frontier-trio
models:
  - codex/gpt-5.5
  - gemini-cli/gemini-2.5-pro
  - anthropic/claude-sonnet-4-6
reducer:
  kind: majority_vote
  tie_breaker: codex/gpt-5.5
```"""
        ),
        nbformat.v4.new_code_cell(
            'fusion_from_yaml = sf.Fusion.from_yaml("fusion.yaml")\n'
            "fusion_from_yaml.url4 == fusion.url4"
        ),
        nbformat.v4.new_markdown_cell(
            """## 3 · Inspect the shareable recipe

The recipe contains model routes and an unresolved `$question`. Constructing or displaying it
sends nothing. Evaluation binds each concrete question later."""
        ),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            """## 4 · Run through the URL4 engine

For each question, ScreamingFace sends one complete expression to
`http://127.0.0.1:4404/v1`. The engine executes all three model routes and returns their labeled
answers. ScreamingFace never calls those routes, AI Gateway, or providers directly."""
        ),
        nbformat.v4.new_code_cell(
            "# For each question: GET http://127.0.0.1:4404/v1?q=<URL-encoded fusion expression>\n"
            "# Decoded q expression:\n"
            "# (question='<resolved GPQA prompt>',\n"
            "#  panel_1=/codex/gpt-5.5()!'$question',\n"
            "#  panel_2=/gemini/2.5()!'$question',\n"
            "#  panel_3=/claude/sonnet-4.6()!'$question',\n"
            "#  {schema: 'screamingface.panel-result.v2',\n"
            "#   panel_1_id: 'codex/gpt-5.5', panel_1_model: 'codex/gpt-5.5',\n"
            "#   panel_1_answer: '$panel_1',\n"
            "#   panel_2_id: 'gemini-cli/gemini-2.5-pro',\n"
            "#   panel_2_model: 'gemini-cli/gemini-2.5-pro', panel_2_answer: '$panel_2',\n"
            "#   panel_3_id: 'anthropic/claude-sonnet-4-6',\n"
            "#   panel_3_model: 'anthropic/claude-sonnet-4-6', panel_3_answer: '$panel_3'})\n"
            "#\n"
            "# Compiled URL4 request node (↖ shared = the same binding, not another request):\n"
            "# GatherNode\n"
            "# ├─ question: BindingNode → TextNode '<resolved GPQA prompt>'\n"
            "# ├─ panel_1: BindingNode → RelUrlNode /codex/gpt-5.5\n"
            "# │  ├─ context → empty\n"
            "# │  └─ intent → question ↖ shared\n"
            "# ├─ panel_2: BindingNode → RelUrlNode /gemini/2.5\n"
            "# │  ├─ context → empty\n"
            "# │  └─ intent → question ↖ shared\n"
            "# ├─ panel_3: BindingNode → RelUrlNode /claude/sonnet-4.6\n"
            "# │  ├─ context → empty\n"
            "# │  └─ intent → question ↖ shared\n"
            "# └─ response: StructNode\n"
            "#    ├─ schema → screamingface.panel-result.v2\n"
            "#    ├─ panel_1_id → codex/gpt-5.5\n"
            "#    ├─ panel_1_model → codex/gpt-5.5\n"
            "#    ├─ panel_1_answer → panel_1 ↖ shared\n"
            "#    ├─ panel_2_id → gemini-cli/gemini-2.5-pro\n"
            "#    ├─ panel_2_model → gemini-cli/gemini-2.5-pro\n"
            "#    ├─ panel_2_answer → panel_2 ↖ shared\n"
            "#    ├─ panel_3_id → anthropic/claude-sonnet-4-6\n"
            "#    ├─ panel_3_model → anthropic/claude-sonnet-4-6\n"
            "#    └─ panel_3_answer → panel_3 ↖ shared\n"
            'run = fusion.evaluate("gpqa", first=20, seed=0)\n'
            "run"
        ),
        nbformat.v4.new_markdown_cell("## 5 · Compare"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "sample_size": run.sample_size,\n'
            '    "score": run.score,\n'
            '    "baseline": run.baseline,\n'
            '    "gain": run.gain,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """> `gain = fusion score − best model score` on the same answers. Positive gain
means the combination corrected mistakes made by every individual panel model.

The URL4 engine owns model execution. ScreamingFace owns majority vote, answer-key scoring,
baseline, and gain. Real AI-Gateway-backed model routes can replace the deterministic commands
later without changing this SDK flow."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 6 · Replace voting with one model-backed reducer

`Reducer` is the common contract; users construct concrete mechanisms. `MajorityVote` runs
deterministically in the SDK. `ModelReducer` adds one later URL4 model call whose prompt can
synthesize, select, rank, merge, or adjudicate the resolved panel answers.

The `$panel_answers` binding contains stable private slot IDs, model IDs, and resolved answers. The
reducer receives it in its URL4 intent, with empty context."""
        ),
        nbformat.v4.new_code_cell(
            "model_reduced = sf.Fusion(\n"
            '    "frontier-trio-model-reduced",\n'
            "    models=fusion.models,\n"
            "    reducer=sf.ModelReducer(\n"
            '        model="codex/gpt-5.5",\n'
            '        prompt="Synthesize one final answer for $question from $panel_answers",\n'
            '        params={"temperature": 0.0, "max_tokens": 512},\n'
            "    ),\n"
            ")\n"
            "model_reduced.url4"
        ),
        nbformat.v4.new_code_cell(
            'model_run = model_reduced.evaluate("gpqa", first=3, seed=0)\nmodel_run'
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
    target = args.output or Path(__file__).parents[1] / "examples" / "sf_url4_engine.ipynb"
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
