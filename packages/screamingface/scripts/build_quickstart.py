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

Combine three models into one Fusion, evaluate it on five real GPQA Diamond questions, and compare
the Fusion with its strongest member.

This is the shortest supported path: **configure → compose → evaluate → compare**. The live cell is
disabled initially because it makes provider-backed calls. Enabling it uses real model responses;
disabled mode does not create a report or substitute an offline result.

## Before you run it

Start the local development stack from the repository root:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

The selected model provider credentials must already be available to the stack's AI Gateway.
GPQA is fetched through this notebook's Hugging Face session, so accept its dataset terms and
authenticate this Python environment when required:

```bash
huggingface-cli login
```

The five-case example makes 15 model calls: three Fusion members for each question. Majority vote,
answer-key grading, and the final comparison make no additional provider calls."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Configure"),
        nbformat.v4.new_code_cell(
            "import os\n\n"
            "import screamingface as sf\n\n"
            'ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404")\n'
            "sf.config(engine=ENGINE_URL)"
        ),
        nbformat.v4.new_markdown_cell(
            """Configuration selects the ScreamingFace engine used for model-backed work. The
localhost value is also the temporary SDK default, while `sf.config(...)` makes it easy to select
another deployment later."""
        ),
        nbformat.v4.new_markdown_cell("## 2 · Compose"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "frontier-trio",\n'
            "    models=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini/2.5",\n'
            '        "claude/sonnet-4.6",\n'
            "    ],\n"
            '    prompt="Return only the answer letter: A, B, C, or D.",\n'
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """Each member answers the same multiple-choice question. `MajorityVote` selects the
most common exact answer and breaks a tie by stable member order. Fusion construction is local and
does not call a model."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Evaluate"),
        nbformat.v4.new_code_cell(
            "RUN_LIVE = False\n\n"
            "if RUN_LIVE:\n"
            '    report = fusion.evaluate("gpqa@1", first=5)\n'
            "else:\n"
            "    report = None\n\n"
            'report or "Set RUN_LIVE = True when the engine and provider access are ready."'
        ),
        nbformat.v4.new_markdown_cell(
            """`evaluate(...)` loads the pinned GPQA Diamond definition through this process,
executes the three-member Fusion for the first five canonical cases, checks the answers against the
sealed answer key, and returns one paired comparison. Missing work remains an explicit failure; it
is never silently scored as zero."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · Compare"),
        nbformat.v4.new_code_cell(
            "comparison = (\n"
            "    {\n"
            '        "score": report.score,\n'
            '        "baseline": report.baseline,\n'
            '        "gain": report.gain,\n'
            "    }\n"
            "    if report is not None\n"
            '    else "Run the live evaluation to produce comparison values."\n'
            ")\n\n"
            "comparison"
        ),
        nbformat.v4.new_markdown_cell(
            """Read `gain` first:

- `score` is the Fusion's accuracy across the successfully paired cases;
- `baseline` is the best individual member's accuracy on those same cases; and
- `gain` is `score - baseline`.

A positive gain means the combination outperformed every member on the evaluated cases. A strong
score with zero gain means the Fusion matched, but did not improve on, its strongest member.

## Recap

```python
sf.config(engine=ENGINE_URL)
fusion = sf.Fusion(..., reducer=sf.reducers.MajorityVote())
report = fusion.evaluate("gpqa@1", first=5)
report.score, report.baseline, report.gain
```

That is the core ScreamingFace workflow. Continue to the engine-profile walkthrough for discovery
and configuration details, or the DRACO walkthrough for model synthesis and rubric judging."""
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
