"""Build the Phase 5F ScreamingFace custom-benchmark notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free custom-benchmark walkthrough."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · create a custom benchmark

Turn a small set of researcher-owned examples into a benchmark that any Fusion can evaluate. The
boundary is intentionally compact:

1. prepare ordinary `sf.Case` values;
2. choose one grader and one aggregator;
3. construct an immutable `sf.Benchmark`.

The default notebook is entirely local. It needs no Docker, provider credentials, Hugging Face
access, or network connection."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Define the cases"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "cases = [\n"
            "    sf.Case(\n"
            '        "astronomy-1",\n'
            "        (\n"
            '            "Which planet is closest to the Sun?\\n\\n"\n'
            '            "A. Venus\\nB. Mercury\\nC. Mars\\nD. Earth\\n\\n"\n'
            '            "Reply with only A, B, C, or D."\n'
            "        ),\n"
            '        reference="B",\n'
            '        metadata={"topic": "astronomy"},\n'
            "    ),\n"
            "    sf.Case(\n"
            '        "biology-1",\n'
            "        (\n"
            '            "Which organelle produces most cellular ATP?\\n\\n"\n'
            '            "A. Nucleus\\nB. Ribosome\\nC. Mitochondrion\\nD. Lysosome\\n\\n"\n'
            '            "Reply with only A, B, C, or D."\n'
            "        ),\n"
            '        reference="C",\n'
            '        metadata={"topic": "biology"},\n'
            "    ),\n"
            "    sf.Case(\n"
            '        "physics-1",\n'
            "        (\n"
            '            "What is the SI unit of force?\\n\\n"\n'
            '            "A. Newton\\nB. Joule\\nC. Watt\\nD. Pascal\\n\\n"\n'
            '            "Reply with only A, B, C, or D."\n'
            "        ),\n"
            '        reference="A",\n'
            '        metadata={"topic": "physics"},\n'
            "    ),\n"
            "]\n\n"
            "len(cases)"
        ),
        nbformat.v4.new_markdown_cell(
            """Each case has four deliberately small fields:

- `id` is a stable unique identity used to pair results;
- `input` is exactly what every Fusion member receives;
- `reference` is the local grading target; and
- `metadata` is optional researcher-owned annotation.

The reference is sealed from execution: the researcher and local grader can read it, but the
reference never enters a model request."""
        ),
        nbformat.v4.new_markdown_cell("## 2 · Inspect your own case values"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "id": cases[0].id,\n'
            '    "input": cases[0].input,\n'
            '    "reference": cases[0].reference,\n'
            '    "metadata": cases[0].metadata,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """These are your ordinary Python values, so inspect the `cases` list you created.
ScreamingFace does not add a second case browser or iteration DSL."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Assemble the benchmark"),
        nbformat.v4.new_code_cell(
            "benchmark = sf.Benchmark(\n"
            '    "tiny-science@1",\n'
            '    title="Tiny Science",\n'
            "    cases=cases,\n"
            "    grader=sf.graders.ExactChoice(),\n"
            "    aggregator=sf.aggregators.Mean(),\n"
            ")\n\n"
            "benchmark"
        ),
        nbformat.v4.new_markdown_cell(
            """The version is part of the opaque benchmark ID, so changing the cases or scoring
contract can produce a new identity such as `tiny-science@2`.

`ExactChoice()` compares a normalized choice answer with each sealed reference. `Mean()` produces
paired Fusion and member accuracy, then derives the best-member baseline and gain. Both stages are
deterministic and local."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · Inspect the public definition"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "id": benchmark.id,\n'
            '    "title": benchmark.title,\n'
            '    "grader": benchmark.grader,\n'
            '    "aggregator": benchmark.aggregator,\n'
            '    "tools": benchmark.tools,\n'
            '    "case_count": len(cases),\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """## 5 · Keep source loading and cleaning outside ScreamingFace

For a larger source, pass a zero-argument loader instead of an in-memory sequence:

```python
def load_cases():
    rows = read_my_source()  # Researcher-owned loading and cleaning
    return [
        sf.Case(
            row["id"],
            row["rendered_input"],
            reference=row["reference"],
            metadata=row.get("metadata"),
        )
        for row in rows
    ]

benchmark = sf.Benchmark(
    "my-benchmark@1",
    cases=load_cases,
    grader=sf.graders.ExactChoice(),
)
```

The loader, files, schemas, joins, and cleanup remain ordinary research code.
ScreamingFace starts at validated `sf.Case` values; it does not become an ETL framework."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 6 · Declare required tools on the benchmark

If answering every case genuinely requires web research, declare that requirement once:

```python
research_benchmark = sf.Benchmark(
    "my-research-benchmark@1",
    cases=cases,
    grader=sf.graders.ExactChoice(),
    tools=("web_search",),
)
```

ScreamingFace then requires every answer-producing member to support the capability and adds it to
their concrete engine requests. Tools do not belong in individual model parameters."""
        ),
        nbformat.v4.new_markdown_cell("## 7 · Optionally run the local benchmark"),
        nbformat.v4.new_markdown_cell(
            """The benchmark is already complete. The next cell only demonstrates that the same
value can enter the ordinary evaluation path.

It defaults off. Enabling it requires the local Docker stack and working provider access, but no
Hugging Face access because all three cases are local. The live path makes nine provider calls:
three cases × three members. Majority voting, exact-choice grading, and mean aggregation add none.
No substitute report is created while execution is disabled."""
        ),
        nbformat.v4.new_code_cell(
            "import os\n\n"
            "RUN_LIVE = False\n"
            'ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404")\n\n'
            "report = None\n"
            "if RUN_LIVE:\n"
            "    sf.config(engine=ENGINE_URL)\n"
            "    fusion = sf.Fusion(\n"
            '        "tiny-science-panel",\n'
            "        models=[\n"
            '            "codex/gpt-5.5",\n'
            '            "gemini/2.5",\n'
            '            "claude/sonnet-4.6",\n'
            "        ],\n"
            "        reducer=sf.reducers.MajorityVote(),\n"
            "    )\n"
            "    report = fusion.evaluate(benchmark)\n\n"
            "report"
        ),
        nbformat.v4.new_markdown_cell(
            """## Recap

- prepare plain `sf.Case` values with stable IDs;
- keep each `input` exact and each `reference` sealed from model requests;
- choose a grader and aggregator explicitly;
- keep source loading and cleaning in researcher-owned code;
- put shared tool requirements on the benchmark; and
- pass the resulting immutable benchmark to any Fusion.

This is the complete custom-benchmark boundary—small enough for three handwritten cases and
flexible enough for a loader that produces thousands."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"custom-benchmarks-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "04_custom_benchmarks.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
