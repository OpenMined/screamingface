"""Build the production DRACO per-candidate URL4 design notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free DRACO/URL4 contract notebook."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# Production DRACO: one URL4 per candidate

This notebook is a design handoff between the ScreamingFace SDK/engine and URL4. It shows the
production DRACO candidate set, the public ScreamingFace construction, and the exact execution
boundary:

1. one candidate becomes one complete URL4 benchmark transaction;
2. the URL4 engine owns dataset iteration, the stable slice, model execution, grading, and
   per-candidate aggregation;
3. the SDK sends one `GET /v1?q=...` request for each candidate; and
4. the SDK compares the returned candidate reports.

There is deliberately no proposed `settle()` syntax and no URL4 containing all 16 candidates.
Candidate independence supplies the failure boundary: one failed candidate request cannot discard
another candidate's successful report.

This notebook does not execute the paid production run. It is intended to be read and reviewed."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Production target

The current reproduction configuration contains **16 candidates over the same 100-case slice**:

- 7 solo Models;
- 9 model-reduced Fusions;
- provider-neutral `web_search` and `web_fetch`, with at most 12 tool calls, on answer-producing
  calls;
- tool-free synthesis calls;
- the official DRACO rubric grader, including 5 independent judge passes per criterion; and
- one DRACO aggregation per candidate.

`sf.Model` and `sf.Fusion` are both `sf.Recipe` values. A candidate is simply the Recipe being
evaluated. A Fusion's member calls and reducer call are sibling bindings in that candidate's flat
per-case URL4 graph. Executable calls are never embedded as text inside another model's context.

The source configuration currently says `judge_runs: 3` even though its production comments
require 5. The reproducible protocol must be corrected to **5** before publishing a result."""
        ),
        nbformat.v4.new_markdown_cell("## ScreamingFace construction"),
        nbformat.v4.new_code_cell(
            '''import screamingface as sf

DRACO_ANSWER_PROMPT = """You are answering a research-quality prompt. Provide a thorough,
well-reasoned answer in prose. Address every aspect the prompt raises. Use clear structure
(headings, bullet lists where appropriate) and cite specific facts, methodologies, or sources
where relevant.

Do not refuse, abstain, or claim uncertainty unless the question is genuinely ambiguous — the
goal is to demonstrate depth of understanding. Length: aim for the level of detail the question
warrants; brevity that skips key points will be penalised by the rubric."""

DRACO_SYNTHESIS_PROMPT = """You are synthesising a single, comprehensive answer to a
research-quality prompt by combining N independent answers from a panel of models. The downstream
grader will score your output against a STRUCTURED RUBRIC of weighted criteria — your goal is to
maximise rubric coverage.

Procedure:
1. Read every panel answer carefully.
2. Identify which claims, facts, citations, or arguments each panel member contributes that the
   others miss.
3. Produce ONE unified prose response that combines the strongest reasoning, preserves specifics,
   resolves disagreements in favour of the better-supported claim, and uses clear structure.
4. Do not introduce new facts that no panel member provided.
5. Do not hedge or refuse.

Output: the unified prose answer, no preamble, no JSON wrapper."""

answer_params = {"temperature": 0, "max_tokens": 8192}
synthesis_params = {"temperature": 0, "max_tokens": 8192}


def solo(model: str, name: str) -> sf.Model:
    return sf.Model(
        model,
        name=name,
        prompt=DRACO_ANSWER_PROMPT,
        params=answer_params,
    )


def synth(model: str) -> sf.Reducer:
    return sf.reducers.Model(
        model=model,
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=synthesis_params,
    )


# Seven solo candidates. Reusing an object inside a Fusion shares it within that candidate graph.
fable = solo("openrouter/anthropic/claude-fable-5", "claude-fable-5")
opus = solo("openrouter/anthropic/claude-opus-4.8", "claude-opus-4.8")
gpt = solo("openrouter/openai/gpt-5.5", "gpt-5.5")
gemini_pro = solo("openrouter/google/gemini-3.1-pro-preview", "gemini-3.1-pro")
gemini_flash = solo("openrouter/google/gemini-3-flash-preview", "gemini-3-flash")
kimi = solo("openrouter/moonshotai/kimi-k2.6", "kimi-k2.6")
deepseek = solo("openrouter/deepseek/deepseek-v4-pro", "deepseek-v4-pro")

# Fusion-only leaf.
qwen = solo("openrouter/qwen/qwen3.6-plus", "qwen-3.6-plus")

fable_plus_gpt = sf.Fusion(
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
        sf.Model(
            "openrouter/anthropic/claude-opus-4.8",
            name="opus-sample-1",
            prompt=DRACO_ANSWER_PROMPT,
            params={"temperature": 0.7, "max_tokens": 8192},
        ),
        sf.Model(
            "openrouter/anthropic/claude-opus-4.8",
            name="opus-sample-2",
            prompt=DRACO_ANSWER_PROMPT,
            params={"temperature": 0.7, "max_tokens": 8192},
        ),
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

candidates = (
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
)

draco = sf.benchmarks.load("draco@1")'''
        ),
        nbformat.v4.new_markdown_cell(
            """## Execute one complete transaction per candidate

`Benchmark.evaluate(...)` intentionally accepts one candidate. Each call returns an independent
`sf.Report`, and `report.url4` is the complete benchmark URL4 for that candidate—not merely its
model prompt.

The loop below would make **16 top-level HTTP requests**, one per candidate. Each request evaluates
the same stable 100-case slice inside the engine. It is shown for contract clarity and is not run
by this notebook."""
        ),
        nbformat.v4.new_code_cell(
            "reports = {candidate.name: draco.evaluate(candidate, first=100) "
            "for candidate in candidates}\n\n"
            "candidate_url4s = {name: report.url4 for name, report in reports.items()}"
        ),
        nbformat.v4.new_markdown_cell(
            """## Transport and query count

Every mapping entry above is sent independently as:

```http
GET /v1?q=<percent-encoded-candidate-expression>
```

“One query per candidate” means one top-level URL4 HTTP transaction, not one provider call. For a
100-case slice:

- a solo candidate normally performs 100 answer calls plus its DRACO judge calls;
- a Fusion performs its member calls and one synthesis call per case, plus judge calls; and
- the URL4 engine performs the iteration, slicing, grading, error collection, and aggregation.

The SDK never calls AI Gateway, Tavily, or a model provider directly."""
        ),
        nbformat.v4.new_markdown_cell(
            r"""## Representative flat solo-candidate URL4

This is the readable, non-percent-encoded shape for one solo candidate. The benchmark iteration is
structural URL4 composition; the per-case candidate graph itself is a flat ordered binding list.

The versioned policy route is resolved once per case. It contains portable capability and budget
data, not a Tavily/OpenRouter choice or credential.

```url4
(
  /benchmarks/draco/1/cases*(
    tool_policy=/benchmarks/draco/1/tool-policy,
    question=$item.input,
    model_input={
      schema:'screamingface.model-input.v1',
      question:'$question',
      tool_policy:'$tool_policy'
    },
    member_1=/openrouter/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ($model_input)!'Answer the research question completely.',
    recipe_result={
      schema:'screamingface.recipe-result.v1',
      members:{
        member_1:{model:'openrouter/anthropic/claude-opus-4.8',answer:'$member_1'}
      },
      answer:'$member_1'
    },
    grade_input={
      benchmark_id:'draco@1',
      case_id:'$item.id',
      reference:'$item.reference'
    },
    case_result=/graders/draco-rubric/1($recipe_result)!'$grade_input'
  )!'$case_result';
  iteration.slice=0:100;
  iteration.on_error=collect
)!/aggregators/draco/1()!'Aggregate benchmark results'
```

There is no bare `()!intent` standing in for a model. The answer route is explicit."""
        ),
        nbformat.v4.new_markdown_cell(
            r"""## Representative flat Fusion-candidate URL4

Member calls and synthesis are sibling bindings. The synthesizer consumes `$member_1`,
`$member_2`, and `$member_3` as resolved text; their URL4 expressions are not embedded inside its
context.

```url4
(
  /benchmarks/draco/1/cases*(
    tool_policy=/benchmarks/draco/1/tool-policy,
    question=$item.input,
    model_input={schema:'screamingface.model-input.v1',question:'$question',tool_policy:'$tool_policy'},
    member_1=/openrouter/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ($model_input)!'Answer the research question completely.',
    member_2=/openrouter/openai/gpt-5.5
      ?temperature=0&max_tokens=8192
      ($model_input)!'Answer the research question completely.',
    member_3=/openrouter/google/gemini-3.1-pro-preview
      ?temperature=0&max_tokens=8192
      ($model_input)!'Answer the research question completely.',
    recipe_answer=/openrouter/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      (
        Question: $question

        Panel 1: $member_1
        Panel 2: $member_2
        Panel 3: $member_3
      )!'Synthesize the single strongest answer.',
    recipe_result={
      schema:'screamingface.recipe-result.v1',
      members:{
        member_1:{model:'openrouter/anthropic/claude-opus-4.8',answer:'$member_1'},
        member_2:{model:'openrouter/openai/gpt-5.5',answer:'$member_2'},
        member_3:{model:'openrouter/google/gemini-3.1-pro-preview',answer:'$member_3'}
      },
      answer:'$recipe_answer'
    },
    grade_input={
      benchmark_id:'draco@1',
      case_id:'$item.id',
      reference:'$item.reference'
    },
    case_result=/graders/draco-rubric/1($recipe_result)!'$grade_input'
  )!'$case_result';
  iteration.slice=0:100;
  iteration.on_error=collect
)!/aggregators/draco/1()!'Aggregate benchmark results'
```

The other 14 candidates use the same envelope with their own flat Recipe bindings."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Self-fusion identity

`opus-sample-1` and `opus-sample-2` deliberately compile into two distinct sibling bindings even
though their routes and parameters look equal. They are two sampled calls, not one shared result.

Within any one candidate URL4, reusing the same `sf.Model` object compiles that dependency once and
references its binding wherever needed. Across separate candidates, no cross-request reuse is
promised. A future engine cache may optimize that cost, but it is not part of the correctness
contract."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Expected plaintext response

Each candidate request returns `text/plain` containing one strictly validated report:

```json
{
  "schema": "screamingface.report.v1",
  "benchmark_id": "draco@1",
  "case_ids": ["case-001", "case-002"],
  "n_cases": 100,
  "n_scored": 100,
  "coverage": 1.0,
  "score": 0.66,
  "baseline": 0.61,
  "gain": 0.05,
  "members": {
    "member_1": {"model": "openrouter/anthropic/claude-opus-4.8", "score": 0.61, "metrics": {}},
    "member_2": {"model": "openrouter/openai/gpt-5.5", "score": 0.58, "metrics": {}},
    "member_3": {
      "model": "openrouter/google/gemini-3.1-pro-preview",
      "score": 0.57,
      "metrics": {}
    }
  },
  "metrics": {"normalized_score": 0.66, "pass_rate": 0.72},
  "failures": [],
  "complete": true
}
```

The SDK attaches the submitted expression as `report.url4`. It compares candidate reports only
after their independent URL4 transactions return."""
        ),
        nbformat.v4.new_markdown_cell(
            """## What remains outside this URL4 contract

No generic URL4 grammar extension blocks this design. The remaining production work is on the
ScreamingFace engine profile and benchmark implementation:

- register the pinned DRACO cases route;
- implement and verify the exact rubric-judge protocol and five passes;
- register the final model/provider routes;
- advertise the already registered versioned tool-policy route in the completed DRACO manifest;
- return usage, failure, and coverage telemetry; and
- run the production candidate set to validate result parity.

Cross-candidate caching and a single transport request containing several candidates are optional
future optimizations, not MVP correctness requirements."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"full-draco-url4-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "07_full_draco_url4.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
