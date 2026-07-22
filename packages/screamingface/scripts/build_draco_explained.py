"""Build the executable DRACO Lite and URL4 architecture deep dive."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free verbose DRACO Lite notebook."""

    namespace = runpy.run_path(str(Path(__file__).with_name("build_draco_quickstart.py")))
    quickstart = namespace["notebook"]()
    composition = quickstart.cells[4].source
    cells = [
        nbformat.v4.new_markdown_cell(
            """# DRACO Lite through ScreamingFace and URL4 · fully explained

This is the architecture companion to `05_draco_quickstart.ipynb`. It constructs the same **7 solo
+ 9 Fusion** comparison and explains what is local, what becomes URL4, what the ScreamingFace
engine executes, and what returns to the SDK.

DRACO Lite is the production topology at miniature scale: one pinned real case, ten deterministic
criteria spanning all four rubric sections, and one judge pass. The available OpenRouter lineup
substitutes for the historical provider mix, so it demonstrates the protocol rather than
reproducing published scores.

```text
ScreamingFace SDK
  └─ one GET /v1?q=<complete candidate-study URL4>
       └─ ScreamingFace engine (Url4Node + versioned SF routes)
            ├─ pinned case + stable slice
            ├─ shared candidate DAG → model routes → AI Gateway → OpenRouter
            ├─ benchmark policy → managed web_search/web_fetch
            ├─ 9 tool-free synthesis calls
            ├─ final candidate answers → DRACO rubric judge
            └─ candidate mean aggregator → plaintext JSON StudyReport
```

The SDK never calls AI Gateway, OpenRouter, Tavily, Hugging Face, or model providers directly."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 0 · Start, connect, and inspect the engine

Start `packages/screamingface/apps/screamingface-engine/dev.sh` with an accepted `HF_TOKEN` in its
`.env` file. Connect OpenRouter in the panel. Benchmark and model discovery come from the configured
engine's registry—there is no client-side fallback catalog."""
        ),
        nbformat.v4.new_code_cell(
            "import json\nfrom pprint import pprint\nfrom urllib.parse import urlencode\n\n"
            "import screamingface as sf\n\n"
            "sf.connect()"
        ),
        nbformat.v4.new_code_cell(
            'print("Benchmarks:", sf.benchmarks.list(query="draco"))\n'
            'print("OpenRouter models with research tools:")\n'
            'pprint(sf.models.list(query="openrouter/", tools=("web_search",)))'
        ),
        nbformat.v4.new_markdown_cell(
            """## 1 · Build the complete candidate topology

`sf.Model` is one atomic answer Recipe. `sf.Fusion` combines other Recipes through a reducer.
Object identity matters: reusing `gpt` shares one answer node across every dependent Fusion; the two
fresh Opus objects in self-fusion remain two independent samples even though their routes match."""
        ),
        nbformat.v4.new_code_cell(composition),
        nbformat.v4.new_markdown_cell(
            """The sixteen roots are seven solo Models followed by nine Fusions. Qwen is a
Fusion-only leaf. Across the whole graph there are ten distinct researched model nodes: eight named
leaves plus two independent Opus samples.

## 2 · Inspect reusable answer Recipes

Each candidate can still be shared as its parameterized answer Recipe. It contains `$question` and
does not include a dataset, slice, grader, or aggregator."""
        ),
        nbformat.v4.new_code_cell(
            "for candidate in candidates:\n"
            '    print(f"\\n--- {candidate.name} ---\\n{candidate.url4}")'
        ),
        nbformat.v4.new_markdown_cell(
            """These answer-level URL4s are useful for inspection and reuse. They are not the
benchmark result recipe. The complete reproducible study is compiled by the loaded benchmark.

## 3 · Load the benchmark manifest"""
        ),
        nbformat.v4.new_code_cell(
            'draco = sf.benchmarks.load("draco-lite@1")\n\n'
            "{\n"
            '    "id": draco.id,\n'
            '    "title": draco.title,\n'
            '    "grader": {\n'
            '        "kind": draco.grader.kind,\n'
            '        "model": draco.grader.model,\n'
            '        "passes": draco.grader.passes,\n'
            '        "params": draco.grader.params,\n'
            "    },\n"
            '    "aggregator": draco.aggregator.kind,\n'
            '    "tools": [tool.id for tool in draco.tools],\n'
            '    "max_tool_calls": draco.max_tool_calls,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """`load` validates the engine manifest; it does not download cases. During execution,
the versioned case route loads the pinned `perplexity-ai/draco` revision with the engine's
`HF_TOKEN`. DRACO Lite selects the first case, seals the first positive and negative criteria, then
adds the first criterion from each remaining rubric section, then fills in dataset order, for ten
total. Its grader uses one
pass; production `draco@1` uses complete rubrics and five.

The deployment itself is authored from the same compact SDK values available to researchers:

```python
sf.Benchmark(
    "my-research@1",
    cases=[sf.Case("q1", "Question", reference={...})],
    grader=sf.graders.Rubric(model="...", prompt="...", passes=1, params={...}),
    aggregator=sf.aggregators.Mean(),
    tools=(sf.tools.WebSearch(max_results=5), sf.tools.WebFetch()),
    max_tool_calls=12,
)
```

This is benchmark authoring, not an ETL DSL. A deployed benchmark exposes immutable versioned
routes and a small manifest.

## 4 · Compile the one complete study URL4 without running it"""
        ),
        nbformat.v4.new_code_cell("study_url4 = draco.url4(candidates)\nprint(study_url4)"),
        nbformat.v4.new_code_cell(
            'request_target = "/v1?" + urlencode({"q": study_url4})\n'
            'print("GET", request_target[:700] + "…")'
        ),
        nbformat.v4.new_markdown_cell(
            """This is one top-level URL4 transaction—not sixteen requests. Its readable shape is:

```text
/benchmarks/draco-lite/1/cases*(
  tool_policy = /benchmarks/draco/1/tool-policy,
  candidate_spec = {
    nodes: { shared Models and Fusions },
    candidates: { 16 ordered names → root node IDs }
  },
  candidate_input = { case, question, rubric, tool policy },
  case_result = /benchmarks/draco-lite/1/evaluate-candidates(
    candidate_spec
  )!candidate_input
)!case_result;
iteration.slice=0:1;
iteration.on_error=collect
  !/aggregators/candidate-mean/1()!'Aggregate candidate benchmark results'
```

The candidate specification is data inside ordinary URL4 composition. The versioned engine route
executes that declared DAG with shared-node memoization and per-root failure isolation. No URL4 SDK
or AI Gateway modification is required.

## 5 · What executes inside the candidate route"""
        ),
        nbformat.v4.new_markdown_cell(
            """For the single case:

1. The engine starts the ten distinct research leaves concurrently.
2. Every leaf receives the same benchmark-owned `web_search`/`web_fetch` policy and 12-call budget.
3. Each Fusion waits only for its member nodes, then makes one tool-free synthesis call.
4. A failed node fails only candidates that depend on it; unrelated candidate roots continue.
5. The engine grades only the sixteen final candidate answers—not their members again.
6. The candidate aggregator preserves declaration order, coverage, scores, and typed failures.

The nominal model-call count is therefore:

```text
10 researched samples
 9 synthesis calls
160 judge calls = 16 candidates × 10 criteria × 1 pass
──
179 model calls
```

Provider-managed search operations and explicit judge-output validation retries are additional.

## 6 · Tools and ownership"""
        ),
        nbformat.v4.new_markdown_cell(
            """The URL4 carries provider-neutral capability policy, never Tavily credentials or
provider-specific tool code. OpenRouter routes map `web_search` and `web_fetch` to OpenRouter's
managed server tools. Verified bare Hugging Face routes map the same policy to the ScreamingFace
engine's bounded Tavily agent loop. Synthesis and judging are tool-free.

AI Gateway remains model transport and model-credential storage. The ScreamingFace engine owns
benchmark policy, tool-backend selection, candidate orchestration, and grading.

## 7 · Grading semantics"""
        ),
        nbformat.v4.new_markdown_cell(
            """For each final answer, the grader makes one request per criterion and pass. Each
judge sees the original question, candidate answer, one criterion, and whether it is positive or
negative. It never sees the criterion weight or sibling criteria and must return
`{explanation, criterion_status: MET|UNMET}`.

```text
normalized_score = clamp(Σ(MET × weight) / Σ(positive weights), 0, 1)
```

Positive MET adds reward; negative MET subtracts a penalty. Missing verdicts reduce coverage rather
than silently becoming zero.

## 8 · Plaintext engine response"""
        ),
        nbformat.v4.new_code_cell(
            """example_response = {
    "schema": "screamingface.study-report.v1",
    "benchmark_id": "draco-lite@1",
    "case_ids": ["<pinned case UUID>"],
    "candidates": {
        "claude-fable-5": {
            "n_cases": 1,
            "n_scored": 1,
            "coverage": 1.0,
            "score": 0.5,
            "metrics": {"normalized_score": 0.5, "verdict_coverage": 1.0},
            "failures": [],
            "complete": True,
        },
        "frontier-trio": {
            "n_cases": 1,
            "n_scored": 1,
            "coverage": 1.0,
            "score": 1.0,
            "metrics": {"normalized_score": 1.0, "verdict_coverage": 1.0},
            "failures": [],
            "complete": True,
        },
    },
    "complete": True,
}

print(json.dumps(example_response, indent=2))"""
        ),
        nbformat.v4.new_markdown_cell(
            """The URL4 engine still returns `text/plain`; its body is strict JSON. The SDK
validates
the schema, benchmark and case identities, ordered candidate set, score ranges, coverage, metrics,
and typed failures before constructing immutable `sf.StudyReport` and `sf.CandidateReport` values.

## 9 · Execute deliberately"""
        ),
        nbformat.v4.new_code_cell(
            "# This performs the real paid 83-call nominal run:\n"
            "# report = draco.evaluate(candidates)\n"
            "# report\n\n"
            "study_url4"
        ),
        nbformat.v4.new_markdown_cell(
            """When executed, `report.url4` is exactly `study_url4`. `report.candidates` contains
all
sixteen independently scored roots and `report.best` selects the highest scored completed one.

Switching to production DRACO is intentionally more than raising a number: `draco@1` changes to
100 cases, complete rubrics, and five judge passes. Published-result parity also requires the
historical pinned model/provider behavior and an audited full run."""
        ),
    ]
    for index, cell in enumerate(cells, 1):
        cell["id"] = f"draco-explained-{index:02d}"
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
        default=Path(__file__).parents[1] / "examples" / "08_draco_explained.ipynb",
    )
    args = parser.parse_args()
    nbformat.write(notebook(), args.output)


if __name__ == "__main__":
    main()
