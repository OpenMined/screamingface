"""Build the executable DRACO and URL4 architecture deep dive."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free verbose DRACO notebook."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# DRACO through ScreamingFace and URL4 · fully explained

This is the verbose companion to `05_draco_quickstart.ipynb`. It builds the complete **7 solo +
9 Fusion** DRACO comparison with currently advertised OpenRouter/AI Gateway model routes, shows
the answer URL4 and complete benchmark URL4, and explains every ownership boundary.

It does **not** start a 100-case paid study. The benchmark protocol is production DRACO; the
July 2026 model/provider lineup is substituted, so resulting numbers are not the paper's original
model ranking.

```text
ScreamingFace SDK
  └─ one GET /v1?q=<complete URL4> per candidate
       └─ ScreamingFace engine (Url4Node)
            ├─ pinned DRACO cases + stable slice
            ├─ model routes → AI Gateway → OpenRouter
            ├─ benchmark policy → managed web_search/web_fetch
            ├─ model-backed synthesis
            ├─ versioned DRACO rubric grader → judge calls
            └─ mean aggregator → plaintext JSON report
```

The SDK never calls AI Gateway, OpenRouter, Tavily, Hugging Face, or a model provider directly."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 0 · Start, connect, and discover

Start `packages/screamingface/apps/screamingface-engine/dev.sh` with `HF_TOKEN` in its environment.
DRACO is advertised only when its pinned judge model is present in the AI Gateway startup model
snapshot."""
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
            """AI Gateway owns model availability. The ScreamingFace engine turns its validated
startup snapshot into URL4 routes and adds tool capabilities. The SDK has no executable fallback
catalog.

## 1 · Build the available-model DRACO candidates

`sf.Model` is an atomic answer Recipe; `sf.Fusion` is a composite answer Recipe. Reusing the same
object creates a shared binding within one candidate. Two separate Model objects remain two sampled
calls even if their IDs match."""
        ),
        nbformat.v4.new_code_cell(
            '''ANSWER_PROMPT = """Answer the research prompt thoroughly. Address every part,
preserve
specific facts and sources, use web evidence, and return clear well-reasoned prose."""

SYNTHESIS_PROMPT = """Combine every labeled panel answer into one comprehensive response. Preserve
specific supported claims and citations, resolve disagreements, and return only unified prose."""


def leaf(model_id: str, name: str, *, temperature: float = 0) -> sf.Model:
    return sf.Model(
        model_id,
        name=name,
        prompt=ANSWER_PROMPT,
        params={"temperature": temperature, "max_tokens": 8192},
    )


def synth(model_id: str) -> sf.Reducer:
    return sf.reducers.Model(
        model=model_id,
        prompt=SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    )


fable = leaf("openrouter/anthropic/claude-fable-5", "claude-fable-5")
opus = leaf("openrouter/anthropic/claude-opus-4.8", "claude-opus-4.8")
gpt = leaf("openrouter/openai/gpt-5.5", "gpt-5.5")
gemini_pro = leaf("openrouter/google/gemini-3.1-pro-preview", "gemini-3.1-pro")
gemini_flash = leaf("openrouter/google/gemini-3-flash-preview", "gemini-3-flash")
kimi = leaf("openrouter/moonshotai/kimi-k2.6", "kimi-k2.6")
deepseek = leaf("openrouter/deepseek/deepseek-v4-pro", "deepseek-v4-pro")
qwen = leaf("openrouter/qwen/qwen3.6-plus", "qwen-3.6-plus")'''
        ),
        nbformat.v4.new_code_cell(
            """fable_plus_gpt = sf.Fusion(
    "fable-plus-gpt",
    members=[fable, gpt],
    reducer=synth("openrouter/anthropic/claude-opus-4.8"),
)
frontier_trio = sf.Fusion(
    "frontier-trio",
    members=[opus, gpt, gemini_pro],
    reducer=synth("openrouter/anthropic/claude-opus-4.8"),
)
opus_plus_gpt = sf.Fusion(
    "opus-plus-gpt",
    members=[opus, gpt],
    reducer=synth("openrouter/anthropic/claude-opus-4.8"),
)
opus_self_fusion = sf.Fusion(
    "opus-self-fusion",
    members=[
        leaf("openrouter/anthropic/claude-opus-4.8", "opus-sample-1", temperature=0.7),
        leaf("openrouter/anthropic/claude-opus-4.8", "opus-sample-2", temperature=0.7),
    ],
    reducer=synth("openrouter/anthropic/claude-opus-4.8"),
)
budget_trio = sf.Fusion(
    "budget-trio",
    members=[gemini_flash, kimi, deepseek],
    reducer=synth("openrouter/anthropic/claude-opus-4.8"),
)
beat_runner_up = sf.Fusion(
    "beat-runner-up",
    members=[opus, gpt, deepseek],
    reducer=synth("openrouter/anthropic/claude-opus-4.8"),
)
pareto_cross = sf.Fusion(
    "pareto-cross",
    members=[deepseek, kimi, gpt],
    reducer=synth("openrouter/deepseek/deepseek-v4-pro"),
)
pareto_lean = sf.Fusion(
    "pareto-lean",
    members=[deepseek, kimi],
    reducer=synth("openrouter/deepseek/deepseek-v4-pro"),
)
best_open_source = sf.Fusion(
    "best-open-source",
    members=[deepseek, kimi, qwen],
    reducer=synth("openrouter/deepseek/deepseek-v4-pro"),
)

candidates = [
    fable,
    opus,
    gpt,
    gemini_pro,
    gemini_flash,
    kimi,
    deepseek,
    fable_plus_gpt,
    frontier_trio,
    opus_plus_gpt,
    opus_self_fusion,
    budget_trio,
    beat_runner_up,
    pareto_cross,
    pareto_lean,
    best_open_source,
]

[(candidate.name, type(candidate).__name__) for candidate in candidates]"""
        ),
        nbformat.v4.new_markdown_cell(
            """These are sixteen independent candidates: seven solo Models and nine Fusions.
Qwen is a Fusion-only leaf. A study is an ordered mapping of candidate name to report—one complete
URL4 transaction per candidate—not a single multi-candidate monster graph.

## 2 · The answer URL4"""
        ),
        nbformat.v4.new_code_cell(
            """candidate_url4s = {candidate.name: candidate.url4 for candidate in candidates}

for name, expression in candidate_url4s.items():
    print(f"\\n--- {name} ---\\n{expression}")"""
        ),
        nbformat.v4.new_markdown_cell(
            """Every reusable candidate URL4 still contains `$question`. A solo Model has one
model source and a recipe-result struct. A composite Fusion has named model sources, one tool-free
synthesis source, and the same result struct. URL4 resolves each named dependency once within that
candidate transaction. `frontier_trio.url4` is therefore one entry in `candidate_url4s`, not a
special case. URL4 quoted text forbids raw ASCII control characters, so the SDK serializes Python
prompt newlines as Unicode line separators. This preserves paragraph boundaries while keeping the
expression parseable and shareable.

## 3 · Benchmark manifest and benchmark creation"""
        ),
        nbformat.v4.new_code_cell(
            'draco = sf.benchmarks.load("draco@1")\n\n'
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
            """`load` validates an engine manifest; it does not fetch questions. When the complete
URL4 executes, `/benchmarks/draco/1/cases` loads the pinned `perplexity-ai/draco` test revision
using the engine's `HF_TOKEN`. The source validator requires 100 cases, 400 sections, 3,934
criteria, ten domains, unique IDs, and finite non-zero weights.

The engine deployment was created from the same compact SDK concepts a researcher uses:
`sf.Case`, `sf.Benchmark`, `sf.graders.Rubric`, `sf.aggregators.Mean`, `sf.tools.WebSearch`, and
`sf.tools.WebFetch`. That authoring object is deployment input, not a benchmark upload or
client-side ETL language. Once its versioned routes are registered, consumers load the manifest
by ID.

```python
sf.Benchmark(
    "my-research@1",
    cases=[sf.Case("q1", "Question", reference={...})],
    grader=sf.graders.Rubric(model="...", prompt="...", passes=5, params={...}),
    aggregator=sf.aggregators.Mean(),
    tools=(sf.tools.WebSearch(max_results=5), sf.tools.WebFetch()),
    max_tool_calls=12,
)
```

## 4 · The complete benchmark URL4"""
        ),
        nbformat.v4.new_code_cell(
            "one_case_url4s = {candidate.name: draco.url4(candidate, first=1) "
            "for candidate in candidates}\n\n"
            "for name, expression in one_case_url4s.items():\n"
            '    print(f"\\n--- {name} · draco@1 · first=1 ---\\n{expression}")\n\n'
            'one_case_url4 = one_case_url4s["frontier-trio"]'
        ),
        nbformat.v4.new_code_cell(
            'request_target = "/v1?" + urlencode({"q": one_case_url4})\n'
            'print("GET", request_target[:500] + "…")'
        ),
        nbformat.v4.new_markdown_cell(
            """Each entry in `one_case_url4s` is a complete, independently shareable benchmark
transaction for one candidate. `first=1` is inside every URL4 iteration slice, so sharing any one
of them reproduces the same case selection. The browser request is only the percent-encoded form
of the readable expression. The SDK asks for SSE progress; the terminal event contains the same
plaintext result as a normal URL4 response.

```text
case ($item)
├─ question + sealed rubric
├─ shared benchmark tool policy
├─ researched member answers
├─ tool-free synthesis
├─ recipe-result struct
├─ DRACO grader
│  ├─ Fusion answer
│  ├─ every member answer
│  └─ criterion × five independent judge calls per answer
└─ case-grade struct

case grades → /aggregators/mean/1 → screamingface.report.v1
```

## 5 · Search and tools"""
        ),
        nbformat.v4.new_markdown_cell(
            """The URL4 carries provider-neutral `web_search` and `web_fetch` policy—not Tavily
credentials or provider-specific code. OpenRouter routes map them to managed OpenRouter server
tools. Verified bare Hugging Face routes map the same policy to the engine's bounded Tavily agent
loop. Synthesis and judging are always tool-free.

AI Gateway remains model transport and model-credential storage. ScreamingFace engine owns
benchmark policy, capability/backend selection, and Tavily orchestration when required.

## 6 · Official DRACO grading"""
        ),
        nbformat.v4.new_markdown_cell(
            """For every answer, the versioned grader flattens the rubric and makes one judge
request per criterion × five passes. Each request contains the original question, answer,
criterion requirement, and only `positive` or `negative`. The judge never sees weights or sibling
criteria and must return `{explanation, criterion_status: MET|UNMET}`.

```text
normalized_score = clamp(Σ(MET × weight) / Σ(positive weights), 0, 1)
```

Positive MET adds reward; negative MET subtracts a penalty. Invalid JSON is retried twice. Missing
verdicts lower coverage and are excluded from numerator and denominator. Metrics include weighted
score, pass rate, per-axis scores, coverage, and pass-to-pass standard deviations.

**Cost warning:** a typical 40-criterion case × five passes is about 200 judge calls per distinct
answer. A three-member Fusion is therefore roughly 800 judge calls for one case, before answer and
synthesis calls. Validate mechanics with `draco-preview@1` first.

## 7 · Plaintext response and SDK validation"""
        ),
        nbformat.v4.new_code_cell(
            """example_response = {
    "schema": "screamingface.report.v1",
    "benchmark_id": "draco@1",
    "case_ids": ["<case UUID>"],
    "n_cases": 1,
    "n_scored": 1,
    "coverage": 1.0,
    "score": 0.72,
    "baseline": 0.68,
    "gain": 0.04,
    "members": {
        "member_1": {"model": "openrouter/anthropic/claude-opus-4.8", "score": 0.68, "metrics": {}},
        "member_2": {"model": "openrouter/openai/gpt-5.5", "score": 0.64, "metrics": {}},
        "member_3": {
            "model": "openrouter/google/gemini-3.1-pro-preview",
            "score": 0.61,
            "metrics": {},
        },
    },
    "metrics": {"normalized_score": 0.72, "pass_rate": 0.75, "verdict_coverage": 1.0},
    "failures": [],
    "complete": True,
}

print(json.dumps(example_response, indent=2))"""
        ),
        nbformat.v4.new_markdown_cell(
            """URL4 returns `text/plain`; the body is one JSON document. The SDK validates the
schema, benchmark ID, member slots/models, counts, score ranges, metrics, typed failures, and paired
coverage before constructing immutable `sf.Report`. Failures are never silently scored as zero.

## 8 · Inspect cheaply, run deliberately"""
        ),
        nbformat.v4.new_code_cell(
            """preview = sf.benchmarks.load("draco-preview@1")
preview_url4 = preview.url4(frontier_trio, first=1)

# Paid execution is explicit:
# preview_report = preview.evaluate(frontier_trio, first=1)
# production_reports = {
#     candidate.name: draco.evaluate(candidate, first=100)
#     for candidate in candidates
# }

preview_url4"""
        ),
        nbformat.v4.new_markdown_cell(
            """Every production candidate yields its own shareable `report.url4`. Exact here:
pinned data validation, exclusions, tool budget, per-criterion prompt, five passes, judge params,
weighted formula, paired member comparison, stable slice, and engine orchestration. Substituted:
the OpenRouter model/provider lineup. Published-result parity additionally requires the original
pinned routes/provider behavior and an audited full run."""
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
