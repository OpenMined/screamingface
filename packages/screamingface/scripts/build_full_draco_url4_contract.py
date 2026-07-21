"""Build the shareable full-production DRACO URL4 design notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free DRACO/URL4 contract notebook."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# Full production DRACO as one URL4

This notebook is a design handoff between the ScreamingFace SDK/engine and URL4. It shows:

1. the intended researcher-facing ScreamingFace construction;
2. the complete readable URL4 graph for the 7 solo Recipes and 9 Fusions in the current DRACO
   reproduction configuration;
3. the plaintext report expected from the ScreamingFace engine; and
4. the one generic URL4 execution capability still needed for this graph.

> **Contract status:** the outer benchmark iteration, stable slice, named bindings, model routes,
> data routes, grading route, cross-row aggregation, and `GET /v1?q=...` transport all exist today.
> The `settle({...})` form below is deliberately **proposed syntax**, not current URL4. Its required
> semantics are specified independently so URL4 can choose the right spelling and builder API.

This is not a smoke notebook and does not execute a paid run. It is meant to be read and
reviewed."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Production target

The current reproduction configuration contains **16 named Recipes over 100 cases**:

- 7 solo model Recipes;
- 9 model-reduced Fusions;
- shared deterministic panel answers reused by every dependent Fusion;
- two deliberately independent Opus samples for self-fusion;
- Tavily `web_search` and `web_fetch`, with at most 12 model/tool rounds, on answer-producing calls;
- tool-free synthesis calls;
- one official rubric-judge request per criterion, repeated 5 times; and
- one final DRACO aggregation across cases and Recipes.

`Recipe` is the umbrella SDK type. `sf.Model` is an atomic Recipe and `sf.Fusion` is a composite
Recipe. `members` belongs inside a Fusion result; `recipes` names the independently compared roots
of the benchmark run.

The source configuration currently says `judge_runs: 3` even though its own production comments
require 5. The final reproducible protocol below intentionally uses **5**. The configuration and
private benchmark definition must be corrected before calling a result a full DRACO reproduction."""
        ),
        nbformat.v4.new_markdown_cell("## ScreamingFace SDK equivalent (target API)"),
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

# Seven solo Recipes. Reusing these exact objects in Fusions makes their answers shared DAG nodes.
fable = sf.Model(
    "anthropic/claude-fable-5", name="claude-fable-5",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)
opus = sf.Model(
    "anthropic/claude-opus-4.8", name="claude-opus-4.8",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)
gpt = sf.Model(
    "openai/gpt-5.5", name="gpt-5.5",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)
gemini_pro = sf.Model(
    "google/gemini-3.1-pro-preview", name="gemini-3.1-pro",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)
gemini_flash = sf.Model(
    "google/gemini-3-flash-preview", name="gemini-3-flash",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)
kimi = sf.Model(
    "moonshotai/kimi-k2.6", name="kimi-k2.6",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)
deepseek = sf.Model(
    "deepseek/deepseek-v4-pro", name="deepseek-v4-pro",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)

# Fusion-only shared leaf.
qwen = sf.Model(
    "qwen/qwen3.6-plus", name="qwen-3.6-plus",
    prompt=DRACO_ANSWER_PROMPT, params=answer_params,
)


def synth(model: str) -> sf.Reducer:
    return sf.reducers.Model(
        model=model,
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=synthesis_params,
    )


fable_plus_gpt = sf.Fusion(
    "fable-plus-gpt", members=[fable, gpt],
    reducer=synth("anthropic/claude-opus-4.8"),
)
frontier_trio = sf.Fusion(
    "frontier-trio", members=[opus, gpt, gemini_pro],
    reducer=synth("anthropic/claude-opus-4.8"),
)
opus_plus_gpt = sf.Fusion(
    "opus-plus-gpt", members=[opus, gpt],
    reducer=synth("anthropic/claude-opus-4.8"),
)

opus_self_fusion = sf.Fusion(
    "opus-self-fusion",
    members=[
        # Two independent samples—not one shared answer used twice.
        sf.Model(
            "anthropic/claude-opus-4.8", name="opus-sample-1",
            prompt=DRACO_ANSWER_PROMPT,
            params={"temperature": 0.7, "max_tokens": 8192},
        ),
        sf.Model(
            "anthropic/claude-opus-4.8", name="opus-sample-2",
            prompt=DRACO_ANSWER_PROMPT,
            params={"temperature": 0.7, "max_tokens": 8192},
        ),
    ],
    reducer=synth("anthropic/claude-opus-4.8"),
)

budget_trio = sf.Fusion(
    "budget-trio", members=[gemini_flash, kimi, deepseek],
    reducer=synth("anthropic/claude-opus-4.8"),
)
beat_runner_up = sf.Fusion(
    "beat-runner-up", members=[opus, gpt, deepseek],
    reducer=synth("anthropic/claude-opus-4.8"),
)
pareto_cross = sf.Fusion(
    "pareto-cross", members=[deepseek, kimi, gpt],
    reducer=synth("deepseek/deepseek-v4-pro"),
)
pareto_lean = sf.Fusion(
    "pareto-lean", members=[deepseek, kimi],
    reducer=synth("deepseek/deepseek-v4-pro"),
)
best_open_source = sf.Fusion(
    "best-open-source", members=[deepseek, kimi, qwen],
    reducer=synth("deepseek/deepseek-v4-pro"),
)

draco = sf.benchmarks.load("draco@1")

# Proposed minimal extension: Benchmark.evaluate accepts one Recipe today; the production form
# accepts several independently named Recipe roots and compiles them into one URL4 transaction.
report = draco.evaluate(
    recipes=[
        fable, opus, gpt, gemini_pro, gemini_flash, kimi, deepseek,
        fable_plus_gpt, frontier_trio, opus_plus_gpt, opus_self_fusion,
        budget_trio, beat_runner_up, pareto_cross, pareto_lean, best_open_source,
    ],
    first=100,
)

report.url4'''
        ),
        nbformat.v4.new_markdown_cell(
            """The benchmark manifest supplies the Tavily tool policy, maximum tool rounds,
versioned case route, official grader route, five judge passes, and aggregator route. Those are
benchmark protocol, not per-Fusion authoring choices.

Route spellings such as `/anthropic/...` are engine-registry aliases. URL4 should not need to know
which downstream transport (AI Gateway, Hugging Face, or another adapter) implements a route."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Complete readable URL4 graph

The browser request is still:

```http
GET /v1?q=<percent-encoded-expression>
```

The block below is the non-URL-encoded expression. `settle({...})` is the only proposed grammar
element. Everything surrounding it follows the currently verified URL4 composition model.

To keep the expression reviewable, the exact answer and synthesis text are referenced through
versioned DRACO data routes. A compatible engine must keep those versioned values immutable. The
versioned grader route similarly owns the Appendix C.5 judge prompts and scoring protocol."""
        ),
        nbformat.v4.new_code_cell(
            r'''PROPOSED_FULL_DRACO_URL4 = r"""
(
  /benchmarks/draco/1/cases*(
    question=$item.input,
    answer_prompt=/benchmarks/draco/1/prompts/answer,
    synthesis_prompt=/benchmarks/draco/1/prompts/synthesis,

    grade_input={
      benchmark_id:'draco@1',
      case_id:'$item.id',
      question:'$question',
      rubric:'$item.reference'
    },

    recipe_results=settle(
      sources=(
    fable_answer=/anthropic/claude-fable-5
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    opus_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    gpt_answer=/openai/gpt-5.5
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    gemini_pro_answer=/google/gemini-3.1-pro-preview
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    gemini_flash_answer=/google/gemini-3-flash-preview
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    kimi_answer=/moonshotai/kimi-k2.6
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    deepseek_answer=/deepseek/deepseek-v4-pro
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    qwen_answer=/qwen/qwen3.6-plus
      ?temperature=0&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    opus_sample_1=/anthropic/claude-opus-4.8
      ?temperature=0.7&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    opus_sample_2=/anthropic/claude-opus-4.8
      ?temperature=0.7&max_tokens=8192
      &tools=web_search:web_fetch&max_tool_rounds=12
      &tavily.search.max_results=5
      &tavily.search.exclude_domain.1=huggingface.co/datasets/perplexity-ai/draco
      &tavily.search.exclude_domain.2=openrouter.ai/blog/announcements/fusion-beats-frontier
      &tavily.search.exclude_domain.3=paperswithcode.com/dataset/draco
      &tavily.search.exclude_domain.4=arxiv.org/abs/2509
      ($question)!'$answer_prompt',

    fable_plus_gpt_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{fable:'$fable_answer',gpt:'$gpt_answer'}})
      !'$synthesis_prompt',

    frontier_trio_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{opus:'$opus_answer',gpt:'$gpt_answer',gemini_pro:'$gemini_pro_answer'}})
      !'$synthesis_prompt',

    opus_plus_gpt_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{opus:'$opus_answer',gpt:'$gpt_answer'}})
      !'$synthesis_prompt',

    opus_self_fusion_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{opus_sample_1:'$opus_sample_1',opus_sample_2:'$opus_sample_2'}})
      !'$synthesis_prompt',

    budget_trio_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{gemini_flash:'$gemini_flash_answer',kimi:'$kimi_answer',deepseek:'$deepseek_answer'}})
      !'$synthesis_prompt',

    beat_runner_up_answer=/anthropic/claude-opus-4.8
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{opus:'$opus_answer',gpt:'$gpt_answer',deepseek:'$deepseek_answer'}})
      !'$synthesis_prompt',

    pareto_cross_answer=/deepseek/deepseek-v4-pro
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{deepseek:'$deepseek_answer',kimi:'$kimi_answer',gpt:'$gpt_answer'}})
      !'$synthesis_prompt',

    pareto_lean_answer=/deepseek/deepseek-v4-pro
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{deepseek:'$deepseek_answer',kimi:'$kimi_answer'}})
      !'$synthesis_prompt',

    best_open_source_answer=/deepseek/deepseek-v4-pro
      ?temperature=0&max_tokens=8192
      ({question:'$question',members:{deepseek:'$deepseek_answer',kimi:'$kimi_answer',qwen:'$qwen_answer'}})
      !'$synthesis_prompt',

    fable_result={schema:'screamingface.recipe-result.v1',name:'claude-fable-5',members:{fable:{model:'anthropic/claude-fable-5',answer:'$fable_answer'}},answer:'$fable_answer'},
    opus_result={schema:'screamingface.recipe-result.v1',name:'claude-opus-4.8',members:{opus:{model:'anthropic/claude-opus-4.8',answer:'$opus_answer'}},answer:'$opus_answer'},
    gpt_result={schema:'screamingface.recipe-result.v1',name:'gpt-5.5',members:{gpt:{model:'openai/gpt-5.5',answer:'$gpt_answer'}},answer:'$gpt_answer'},
    gemini_pro_result={schema:'screamingface.recipe-result.v1',name:'gemini-3.1-pro',members:{gemini_pro:{model:'google/gemini-3.1-pro-preview',answer:'$gemini_pro_answer'}},answer:'$gemini_pro_answer'},
    gemini_flash_result={schema:'screamingface.recipe-result.v1',name:'gemini-3-flash',members:{gemini_flash:{model:'google/gemini-3-flash-preview',answer:'$gemini_flash_answer'}},answer:'$gemini_flash_answer'},
    kimi_result={schema:'screamingface.recipe-result.v1',name:'kimi-k2.6',members:{kimi:{model:'moonshotai/kimi-k2.6',answer:'$kimi_answer'}},answer:'$kimi_answer'},
    deepseek_result={schema:'screamingface.recipe-result.v1',name:'deepseek-v4-pro',members:{deepseek:{model:'deepseek/deepseek-v4-pro',answer:'$deepseek_answer'}},answer:'$deepseek_answer'},

    fable_plus_gpt_result={schema:'screamingface.recipe-result.v1',name:'fable-plus-gpt',members:{fable:{model:'anthropic/claude-fable-5',answer:'$fable_answer'},gpt:{model:'openai/gpt-5.5',answer:'$gpt_answer'}},answer:'$fable_plus_gpt_answer'},
    frontier_trio_result={schema:'screamingface.recipe-result.v1',name:'frontier-trio',members:{opus:{model:'anthropic/claude-opus-4.8',answer:'$opus_answer'},gpt:{model:'openai/gpt-5.5',answer:'$gpt_answer'},gemini_pro:{model:'google/gemini-3.1-pro-preview',answer:'$gemini_pro_answer'}},answer:'$frontier_trio_answer'},
    opus_plus_gpt_result={schema:'screamingface.recipe-result.v1',name:'opus-plus-gpt',members:{opus:{model:'anthropic/claude-opus-4.8',answer:'$opus_answer'},gpt:{model:'openai/gpt-5.5',answer:'$gpt_answer'}},answer:'$opus_plus_gpt_answer'},
    opus_self_fusion_result={schema:'screamingface.recipe-result.v1',name:'opus-self-fusion',members:{opus_sample_1:{model:'anthropic/claude-opus-4.8',answer:'$opus_sample_1'},opus_sample_2:{model:'anthropic/claude-opus-4.8',answer:'$opus_sample_2'}},answer:'$opus_self_fusion_answer'},
    budget_trio_result={schema:'screamingface.recipe-result.v1',name:'budget-trio',members:{gemini_flash:{model:'google/gemini-3-flash-preview',answer:'$gemini_flash_answer'},kimi:{model:'moonshotai/kimi-k2.6',answer:'$kimi_answer'},deepseek:{model:'deepseek/deepseek-v4-pro',answer:'$deepseek_answer'}},answer:'$budget_trio_answer'},
    beat_runner_up_result={schema:'screamingface.recipe-result.v1',name:'beat-runner-up',members:{opus:{model:'anthropic/claude-opus-4.8',answer:'$opus_answer'},gpt:{model:'openai/gpt-5.5',answer:'$gpt_answer'},deepseek:{model:'deepseek/deepseek-v4-pro',answer:'$deepseek_answer'}},answer:'$beat_runner_up_answer'},
    pareto_cross_result={schema:'screamingface.recipe-result.v1',name:'pareto-cross',members:{deepseek:{model:'deepseek/deepseek-v4-pro',answer:'$deepseek_answer'},kimi:{model:'moonshotai/kimi-k2.6',answer:'$kimi_answer'},gpt:{model:'openai/gpt-5.5',answer:'$gpt_answer'}},answer:'$pareto_cross_answer'},
    pareto_lean_result={schema:'screamingface.recipe-result.v1',name:'pareto-lean',members:{deepseek:{model:'deepseek/deepseek-v4-pro',answer:'$deepseek_answer'},kimi:{model:'moonshotai/kimi-k2.6',answer:'$kimi_answer'}},answer:'$pareto_lean_answer'},
    best_open_source_result={schema:'screamingface.recipe-result.v1',name:'best-open-source',members:{deepseek:{model:'deepseek/deepseek-v4-pro',answer:'$deepseek_answer'},kimi:{model:'moonshotai/kimi-k2.6',answer:'$kimi_answer'},qwen:{model:'qwen/qwen3.6-plus',answer:'$qwen_answer'}},answer:'$best_open_source_answer'},

      ),
      roots={
      claude_fable_5:/graders/draco-rubric/1($fable_result)!'$grade_input',
      claude_opus_4_8:/graders/draco-rubric/1($opus_result)!'$grade_input',
      gpt_5_5:/graders/draco-rubric/1($gpt_result)!'$grade_input',
      gemini_3_1_pro:/graders/draco-rubric/1($gemini_pro_result)!'$grade_input',
      gemini_3_flash:/graders/draco-rubric/1($gemini_flash_result)!'$grade_input',
      kimi_k2_6:/graders/draco-rubric/1($kimi_result)!'$grade_input',
      deepseek_v4_pro:/graders/draco-rubric/1($deepseek_result)!'$grade_input',
      fable_plus_gpt:/graders/draco-rubric/1($fable_plus_gpt_result)!'$grade_input',
      frontier_trio:/graders/draco-rubric/1($frontier_trio_result)!'$grade_input',
      opus_plus_gpt:/graders/draco-rubric/1($opus_plus_gpt_result)!'$grade_input',
      opus_self_fusion:/graders/draco-rubric/1($opus_self_fusion_result)!'$grade_input',
      budget_trio:/graders/draco-rubric/1($budget_trio_result)!'$grade_input',
      beat_runner_up:/graders/draco-rubric/1($beat_runner_up_result)!'$grade_input',
      pareto_cross:/graders/draco-rubric/1($pareto_cross_result)!'$grade_input',
      pareto_lean:/graders/draco-rubric/1($pareto_lean_result)!'$grade_input',
      best_open_source:/graders/draco-rubric/1($best_open_source_result)!'$grade_input'
      }
    ),

    case_result={
      schema:'screamingface.draco-case-results.v1',
      benchmark_id:'draco@1',
      case_id:'$item.id',
      recipes:'$recipe_results'
    }
  )!'$case_result';
  iteration.slice=0:100;
  iteration.on_error=collect
)!/aggregators/draco/1()!'Aggregate DRACO Recipe results'
"""

print(PROPOSED_FULL_DRACO_URL4)'''
        ),
        nbformat.v4.new_markdown_cell(
            """## Required semantics of the proposed primitive

The operation need not be named `settle`; the behavior is what ScreamingFace requires.

1. Accept an ordered mapping of independently named roots over one shared source graph.
2. Execute each shared dependency at most once per benchmark case.
3. Preserve success or typed failure independently for every named root.
4. If a shared dependency fails, fail only roots that depend on it; unrelated roots continue.
5. Do not cancel or discard successful siblings after one root fails.
6. Preserve declared root order in the returned mapping.
7. Work inside an iteration body.
8. Compose with outer `iteration.on_error=collect`, which handles whole-case failures.
9. Round-trip through URL4 parse, render, and public Python builders.
10. Use graph-node/binding identity for memoization, not URL equality. The two equal-looking Opus
    self-fusion calls must remain independent sampled executions.

A normal engine endpoint cannot implement this behavior by itself: URL4 resolves endpoint inputs
before dispatch. If one root fails during that resolution, `/settle` would never receive the other
roots. This therefore needs to be evaluator-level composition or an equivalent documented URL4
construct."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Grader boundary

`/graders/draco-rubric/1` is a versioned ScreamingFace-engine route. It receives one Recipe result
and the case's question/rubric metadata, then performs the deterministic DRACO protocol:

- expand the rubric into individual criteria;
- make one judge request per criterion;
- repeat each criterion for 5 independent judge passes;
- never show weights or other criteria to the judge;
- use the exact Appendix C.5 system/user prompt;
- require `{explanation, criterion_status: MET|UNMET}`;
- use the pinned judge model with `temperature=0.2`, `reasoning=low`, and `max_tokens=4096`;
- give the judge no research tools; and
- return verdicts, coverage, failures, usage, and the official weighted score.

The route can make judge subrequests internally through the same `Url4Node`. This keeps the full
benchmark invocation in one outer URL4 without requiring nested criterion iteration in the URL4
grammar."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Expected plaintext response

The engine continues to return `text/plain`; the body contains one JSON document that the
ScreamingFace SDK validates:

```json
{
  "schema": "screamingface.benchmark-report.v1",
  "benchmark_id": "draco@1",
  "case_slice": {"start": 0, "stop": 100},
  "recipes": {
    "claude-fable-5": {
      "score": 0.53,
      "metrics": {
        "normalized_score": 0.53,
        "pass_rate": 0.61,
        "coverage": 1.0
      },
      "failures": []
    },
    "frontier-trio": {
      "score": 0.66,
      "metrics": {
        "normalized_score": 0.66,
        "pass_rate": 0.72,
        "coverage": 1.0
      },
      "failures": []
    }
  },
  "failures": [],
  "complete": true
}
```

The other 14 Recipes follow the same mapping shape. JSON arrays are valid in returned plaintext;
URL4 inline-struct grammar does not constrain an endpoint's serialized response body."""
        ),
        nbformat.v4.new_markdown_cell(
            """## The concrete question for URL4

Current URL4 already covers the outer collection iteration, stable slice, named bindings, data
routes, route dispatch, engine-internal subrequests, per-case error collection, and cross-row
reduction.

The remaining question is:

> Does URL4 already have a documented composition that executes several named roots over a shared
> dependency graph, memoizes shared dependencies, and preserves an independent typed success or
> failure for every root inside an iteration body? If not, can URL4 add a generic evaluator-level
> primitive with the semantics specified above?

This capability is not DRACO- or ScreamingFace-specific. It is generic named, multi-root,
all-settled DAG execution."""
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
