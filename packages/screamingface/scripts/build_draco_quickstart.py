"""Build the minimal executable DRACO Lite notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free DRACO Lite quickstart."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · DRACO Lite

Run two real DRACO research questions through one OpenRouter-backed Fusion, then grade the Fusion
and both members with DRACO's official per-criterion judge prompt.

This uses **`draco-lite@1`**: the first two cases from the pinned DRACO dataset, every rubric
criterion for those cases, and two independent judge passes per criterion. It exercises the real
research, synthesis, grading, and aggregation protocol, but its two-case result is **not comparable
to a production DRACO score**. Production `draco@1` uses all 100 cases and five judge passes.

## Before you run it

```bash
cd packages/screamingface/apps/screamingface-engine
export HF_TOKEN=hf_...  # accepted DRACO dataset access
./dev.sh restart
```

Connect one OpenRouter API key below. The SDK speaks only to the ScreamingFace engine; the engine
calls AI Gateway for inference and uses OpenRouter's managed search/fetch tools."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Connect"),
        nbformat.v4.new_code_cell("import screamingface as sf\n\nsf.connect()"),
        nbformat.v4.new_markdown_cell(
            """Connect **OpenRouter**. The same engine-scoped connection covers all three model
routes below. Dataset access is separate: `HF_TOKEN` belongs in the engine environment.

## 2 · Compose"""
        ),
        nbformat.v4.new_code_cell(
            'ANSWER_PROMPT = "Answer thoroughly. Use web evidence and cite sources."\n'
            'SYNTHESIS_PROMPT = "Combine the panel answers into one stronger answer."\n\n'
            "gpt = sf.Model(\n"
            '    "openrouter/openai/gpt-5.5",\n'
            '    name="gpt",\n'
            "    prompt=ANSWER_PROMPT,\n"
            '    params={"temperature": 0, "max_tokens": 4096},\n'
            ")\n"
            "opus = sf.Model(\n"
            '    "openrouter/anthropic/claude-opus-4.8",\n'
            '    name="opus",\n'
            "    prompt=ANSWER_PROMPT,\n"
            '    params={"temperature": 0, "max_tokens": 4096},\n'
            ")\n\n"
            "fusion = sf.Fusion(\n"
            '    "research-duo",\n'
            "    members=[gpt, opus],\n"
            "    reducer=sf.reducers.Model(\n"
            '        model="openrouter/openai/gpt-5.5",\n'
            "        prompt=SYNTHESIS_PROMPT,\n"
            '        params={"temperature": 0, "max_tokens": 4096},\n'
            "    ),\n"
            ")\n\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """Construction is local and makes no model calls. The benchmark—not the Fusion—adds
`web_search`, `web_fetch`, the twelve-call budget, leak-domain exclusions, grader, and aggregator.

## 3 · Evaluate two real cases

**Spend warning:** a typical DRACO case has roughly forty criteria. Two cases × two passes × the
Fusion plus two distinct member answers is roughly **480 judge requests**, in addition to the
researched answer and synthesis calls. This is intentionally smaller than production, not free."""
        ),
        nbformat.v4.new_code_cell(
            'draco = sf.benchmarks.load("draco-lite@1")\nreport = draco.evaluate(fusion)'
        ),
        nbformat.v4.new_markdown_cell(
            """One SDK call sends one complete URL4 expression to `GET /v1?q=...`. For this
two-member Fusion, each case performs two researched member answers, one synthesis, then two
independent judge passes for every rubric criterion across the Fusion and both member answers.

## 4 · Compare"""
        ),
        nbformat.v4.new_code_cell("report"),
        nbformat.v4.new_markdown_cell(
            """`score`, `baseline`, and `gain` use the same paired case and rubric verdicts.
Inspect the exact transaction with `report.url4`. Switching to `draco@1` changes the benchmark
itself to all 100 cases and five judge passes; the Fusion construction does not change."""
        ),
    ]
    for index, cell in enumerate(cells, 1):
        cell["id"] = f"draco-quickstart-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            }
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parents[1] / "examples" / "05_draco_quickstart.ipynb",
    )
    args = parser.parse_args()
    nbformat.write(notebook(), args.output)


if __name__ == "__main__":
    main()
