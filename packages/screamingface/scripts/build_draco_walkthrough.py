"""Build the Phase 5A DRACO SDK walkthrough notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free DRACO walkthrough."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# DRACO with ScreamingFace

Use the canonical DRACO benchmark with a small URL4-backed research Fusion, then inspect the
separate run, grade, and aggregate stages.

**This is a real-engine SDK walkthrough, not a full DRACO reproduction.** It uses the pinned
100-case DRACO source and official per-criterion grader configured by `draco@1`, but evaluates one
compatible two-model Fusion rather than the benchmark pipeline's complete comparison. The live
cell is off by default because even one case can require hundreds of independent judge requests.

## Before you run it

Start the tracked development stack from the repository root:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

The stack starts:

- `screamingface-engine` at `http://127.0.0.1:4404`;
- AI Gateway, used only by the engine's model routes; and
- private SearXNG search infrastructure used by the engine's `web_search` capability.

The selected provider credentials and the assumed `gemini-cli/gemini-3.1-pro-preview` judge
registration must already be available to AI Gateway. ScreamingFace never contacts AI Gateway
directly.

DRACO is downloaded and validated by the researcher's Python process through its own Hugging Face
session. Authenticate that environment if the dataset requires it:

```bash
huggingface-cli login
```

The Hugging Face token is not forwarded to the engine containers. This notebook has no fabricated
response or in-process execution fallback."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Configure and inspect the URL4 engine"),
        nbformat.v4.new_code_cell(
            "import os\n\n"
            "import screamingface as sf\n\n"
            'ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404")\n'
            "sf.config(engine=ENGINE_URL)\n\n"
            "{\n"
            '    "web_research_models": sf.models.list(tools=["web_search"]),\n'
            '    "judge_route": sf.models.list(query="gemini/3.1-pro-preview"),\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """`sf.config(...)` selects one HTTP URL4 engine. Model discovery reads that engine's
validated `/.well-known/screamingface` registry; it does not infer provider credentials. In the
development profile, Gemini 2.5 and Claude Sonnet 4.6 advertise `web_search`, while Gemini 3.1 Pro
Preview is the tool-free DRACO judge route.

If either expected worker or the judge is missing, stop here and update the engine deployment. The
SDK will not silently choose a substitute model."""
        ),
        nbformat.v4.new_markdown_cell("## 2 · Load the canonical benchmark locally"),
        nbformat.v4.new_code_cell(
            'benchmark = sf.benchmarks.load("draco@1")\n\n'
            "{\n"
            '    "id": benchmark.id,\n'
            '    "title": benchmark.title,\n'
            '    "tools": benchmark.tools,\n'
            '    "grader": benchmark.grader,\n'
            '    "aggregator": benchmark.aggregator,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """Loading is eager and SDK-local. It fetches the source pinned by the installed SDK,
validates all 100 rows, seals each rubric reference away from the answer-producing model requests,
and returns an immutable `sf.Benchmark`.

This step does **not** contact the URL4 engine, AI Gateway, or SearXNG. The resulting benchmark
uses three independent Gemini judge passes per rubric criterion and deterministic local Python
aggregation."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Compose a compatible research Fusion"),
        nbformat.v4.new_code_cell(
            'RESEARCH_PROMPT = """You are answering a research-quality prompt.\n'
            "Provide a thorough, well-reasoned answer in prose. Address every aspect, preserve\n"
            'specific facts and sources, and use clear structure."""\n\n'
            'SYNTHESIS_PROMPT = """Produce one comprehensive answer by combining the strongest\n'
            "facts, arguments, and citations from every labeled panel answer. Resolve\n"
            "disagreements in favor of the more specific and better-supported claim. Return only\n"
            'the unified prose answer."""\n\n'
            "fusion = sf.Fusion(\n"
            '    "draco-research-duo",\n'
            "    models=[\n"
            '        "gemini/2.5",\n'
            '        "claude/sonnet-4.6",\n'
            "    ],\n"
            "    prompt=RESEARCH_PROMPT,\n"
            "    reducer=sf.reducers.Model(\n"
            '        model="codex/gpt-5.5",\n'
            "        prompt=SYNTHESIS_PROMPT,\n"
            "    ),\n"
            ")\n\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """The two members receive the benchmark's `web_search` capability because DRACO
declares it. The model reducer receives the labeled question and resolved member answers, but it
does not inherit member tools. Reducers synthesize existing answers; they are not research workers.

The prompts live in the Fusion rather than the benchmark. That keeps DRACO responsible for the
questions and grading contract while researchers remain responsible for the system they want to
evaluate."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · Inspect the reusable URL4 recipe"),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            """`fusion.url4` is the parameterized, shareable recipe. It contains `$question` because
no benchmark case has been selected yet. `Fusion.run(...)` binds one concrete case internally and
sends the resulting expression only to the configured engine:

```text
ScreamingFace SDK
  └─ GET /v1?q=<URL-encoded-expression>
       └─ screamingface-engine / Url4Node
            ├─ Gemini member ── web_search ── SearXNG
            ├─ Claude member ── web_search ── SearXNG
            └─ Codex reducer receives the resolved member answers
```

Each model turn is forwarded from `screamingface-engine` to AI Gateway. A successful URL4 response
is plaintext; for this Fusion that text contains a serialized `screamingface.fusion-result.v1`
object with nested `member_1` and `member_2` answers plus the reduced answer. The SDK parses and
validates that text into immutable run values.

The concrete compiler is intentionally private. This walkthrough shows the stable public recipe
and transport boundary without teaching an application to depend on private compiler functions."""
        ),
        nbformat.v4.new_markdown_cell("## 5 · Understand the live-call scale"),
        nbformat.v4.new_code_cell(
            "average_criteria = 3_934 / 100\n"
            "answer_targets = len(fusion.model_ids) + 1  # two members plus their reduced answer\n"
            "judge_passes = benchmark.grader.passes\n\n"
            "{\n"
            '    "answer_model_calls_per_case": answer_targets,\n'
            '    "average_judge_calls_per_case": '
            "(average_criteria * answer_targets * judge_passes),\n"
            '    "note": "The exact criterion count varies by case.",\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """For this two-member Fusion, one successful case makes two research calls and one
synthesis call. Grading then judges the Fusion answer and both member answers against every
criterion, three times independently. DRACO averages 39.34 criteria per case, so a typical case is
about 354 judge calls in addition to the three answer calls.

The SDK does not yet provide enforceable monetary budgets or persistence/resume. Leave the next
cell disabled until you have checked provider access, rate limits, and expected spend. Disabled
means no result is created; it does not fabricate a result."""
        ),
        nbformat.v4.new_markdown_cell("## 6 · Run, grade, and aggregate explicitly"),
        nbformat.v4.new_code_cell(
            "RUN_LIVE = False\n\n"
            "if RUN_LIVE:\n"
            "    run = fusion.run(benchmark, first=1)\n"
            "    grades = run.grade()\n"
            "    report = grades.aggregate()\n"
            "else:\n"
            "    run = None\n"
            "    grades = None\n"
            "    report = None\n\n"
            'report or "Set RUN_LIVE = True after reviewing the call estimate above."'
        ),
        nbformat.v4.new_markdown_cell(
            """The three calls are deliberately separate here:

1. `run` executes the panel and reducer through the configured HTTP URL4 engine.
2. `grade` sends one independent judge request per target, criterion, and pass through that same
   engine. Invalid judge text alone may receive bounded byte-identical retries; transport failures
   remain failures.
3. `aggregate` performs paired mean comparison in deterministic local Python. It makes no model or
   engine request.

For concise application code, the exact convenience equivalent is:

```python
report = fusion.evaluate(benchmark, first=1)
```

Do not run that after the explicit stages unless you intend to pay for the entire workflow again."""
        ),
        nbformat.v4.new_markdown_cell("## 7 · Inspect each boundary"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "run": None if run is None else run.to_dict(),\n'
            '    "grades": None if grades is None else grades.to_dict(),\n'
            '    "report": None if report is None else report.to_dict(),\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The records preserve different evidence:

- `Run` contains the Fusion/member answers or typed execution failures.
- `Grades` contains per-case, per-target criterion verdicts, coverage, raw judge responses, and
  typed grading failures.
- `Report` contains the paired Fusion score, best-member baseline, gain, coverage, section metrics,
  and retained failures.

An unresolved call never becomes an invented zero score. Incomplete rubric coverage retains the
evidence but prevents a valid aggregate score."""
        ),
        nbformat.v4.new_markdown_cell(
            """## What this result can claim

When enabled successfully, this notebook measures one named two-member Fusion against the real
`draco@1` benchmark contract. That is a valid ScreamingFace evaluation.

It does **not** claim a full DRACO reproduction. The benchmark pipeline comparison contains
seven standalone models and nine named fusions, including panel and synthesizer models the current
development engine does not advertise. A future reproduction notebook must pin that complete
lineup and clearly record its execution, persistence, and cost assumptions; it must not silently
substitute the smaller Fusion demonstrated here.

## Recap

- the researcher loads and validates DRACO locally through Hugging Face;
- ScreamingFace compiles panel and reduction work into URL4;
- only the configured `screamingface-engine` contacts AI Gateway and SearXNG;
- grading uses the same engine but independent judge requests;
- aggregation stays local and deterministic; and
- live execution is explicit because DRACO grading is large even for one case."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"draco-walkthrough-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "05_draco.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
