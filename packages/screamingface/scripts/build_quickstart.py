"""Build the Phase 5B bare-bones ScreamingFace quickstart notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free quickstart."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · quickstart

Connect three model providers, combine their models into one Fusion, evaluate it on five real GPQA
Diamond questions, and compare the Fusion with its strongest member.

This is the shortest supported path: **connect → compose → evaluate → compare**. Its core
evaluation path remains **compose → evaluate → compare**. Evaluation uses real model responses
through the configured ScreamingFace engine; it never substitutes an offline result.

## Before you run it

Start the local development stack from the repository root:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

The local AI Gateway starts with an empty provider profile store. The first cell opens the
ScreamingFace provider panel, which stores provider credentials through the engine. If a selected
provider is disconnected, evaluation raises one actionable `ConnectionRequiredError` before model
calls; provider authentication never becomes repeated per-case failures.

### Gemini compatibility · July 2026

Some newly created Google API projects may receive `model no longer available` for Gemini 2.5
even when their quota dashboard displays Gemini 2.5 limits. The local AI Gateway used by this
notebook does not yet register Google's recommended `gemini-3.5-flash` or
`gemini-3.1-pro-preview` replacements. If that happens, replace the Gemini member below with
another connected model advertised by `sf.models.list()`.

Hugging Face does not provide Gemini through this integration. The forthcoming Hugging Face route
is for open models such as DeepSeek and GLM through pinned inference providers; Gemini 3 still
requires explicit AI Gateway support.

GPQA is fetched through this notebook's Hugging Face session, so accept its dataset terms and
authenticate this Python environment when required:

```bash
huggingface-cli login
```

The five-case example makes 15 model calls: three Fusion members for each question. Majority vote,
answer-key grading, and the final comparison make no additional provider calls."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Connect"),
        nbformat.v4.new_code_cell("import screamingface as sf\n\nsf.connect()"),
        nbformat.v4.new_markdown_cell(
            """Connect each provider used below. The panel sends credentials only to the configured
ScreamingFace engine and shows the engine origin before you act.

## 2 · Compose"""
        ),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "frontier-trio",\n'
            "    members=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini/2.5-flash",\n'
            '        "claude/sonnet-4.6",\n'
            "    ],\n"
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """Each member answers the same multiple-choice question. `MajorityVote` selects the
most common exact answer and breaks a tie by stable member order. Fusion construction is local and
does not call a model.

## 3 · Evaluate"""
        ),
        nbformat.v4.new_code_cell(
            'report = fusion.evaluate("gpqa@1", first=5)\n\n'
            "# Equivalent staged API:\n"
            '# benchmark = sf.benchmarks.load("gpqa@1")\n'
            "# run = fusion.run(benchmark, first=5)\n"
            "# grades = run.grade()\n"
            "# report = grades.aggregate()"
        ),
        nbformat.v4.new_markdown_cell(
            """`evaluate(...)` loads the pinned GPQA Diamond definition through this process,
executes the three-member Fusion for the first five canonical cases, checks the answers against the
sealed answer key, and returns one paired comparison. Missing work remains an explicit failure; it
is never silently scored as zero. In a notebook, one compact live panel shows requirement checks,
case execution, grading, and aggregation before giving way to the final report. Pass
`progress=False` to hide it, or `progress=True` to force the same progress outside notebooks.

## 4 · Compare"""
        ),
        nbformat.v4.new_code_cell("report"),
        nbformat.v4.new_markdown_cell(
            """Read `gain` first:

- `score` is the Fusion's accuracy across the successfully paired cases;
- `baseline` is the best individual member's accuracy on those same cases; and
- `gain` is `score - baseline`.

A positive gain means the combination outperformed every member on the evaluated cases. A strong
score with zero gain means the Fusion matched, but did not improve on, its strongest member."""
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output or Path(__file__).parents[1] / "examples" / "00_quickstart.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
