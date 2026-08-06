"""Build the public v1 notebooks deterministically."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat
from _ifeval_notebook import kimi_appendix
from nbformat import NotebookNode

_DRACO_ANSWER_PROMPT_PARTS = (
    "You are answering a research-quality prompt. Provide a thorough, ",
    "well-reasoned answer in prose. Address every aspect the prompt raises. ",
    "Use clear structure (headings, bullet lists where appropriate) and cite ",
    "specific facts, methodologies, or sources where relevant.\n\n",
    "Do not refuse, abstain, or claim uncertainty unless the question is ",
    "genuinely ambiguous — the goal is to demonstrate depth of understanding. ",
    "Length: aim for the level of detail the question warrants; brevity that ",
    "skips key points will be penalised by the rubric.",
)
_DRACO_ANSWER_PROMPT = "".join(_DRACO_ANSWER_PROMPT_PARTS)

_DRACO_SYNTHESIS_PROMPT_PARTS = (
    "You are synthesising a single, comprehensive answer to a research-quality ",
    "prompt by combining N independent answers from a panel of models. The ",
    "downstream grader will score your output against a STRUCTURED RUBRIC of ",
    "weighted criteria — your goal is to maximise rubric coverage.\n\n",
    "Procedure:\n",
    "1. Read every panel answer carefully.\n",
    "2. Identify which claims, facts, citations, or arguments each panel member ",
    "contributes that the others miss.\n",
    "3. Produce ONE unified prose response that:\n",
    "   - Combines the strongest reasoning from every panel member\n",
    "   - Preserves specific named entities, dates, methodologies, and citations\n",
    "   - Resolves disagreements by favouring the more specific / better-cited claim\n",
    "   - Uses clear structure (headings, lists) where it aids the reader\n",
    "4. Do not introduce new facts that no panel member provided.\n",
    "5. Do not hedge or refuse — the panel collectively has enough material.\n\n",
    "Output: the unified prose answer, no preamble, no JSON wrapper.",
)
_DRACO_SYNTHESIS_PROMPT = "".join(_DRACO_SYNTHESIS_PROMPT_PARTS)


def notebooks() -> dict[str, NotebookNode]:
    return {
        "00_quickstart.ipynb": _quickstart(),
        "05_draco_lite_e2e.ipynb": _draco_lite_e2e(),
        "06_draco_full_e2e.ipynb": _draco_full_e2e(),
        "07_ifeval_e2e.ipynb": _ifeval_e2e(),
        "08_healthbench_worst30.ipynb": _healthbench_worst30_e2e(),
    }


def _notebook(*cells: NotebookNode) -> NotebookNode:
    for index, cell in enumerate(cells, 1):
        cell["id"] = f"cell-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=list(cells),
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
    )


def _local_stack_cell() -> NotebookNode:
    return nbformat.v4.new_markdown_cell(
        """## Before running

From a terminal in `packages/screamingface/`:

```bash
just stack-prepare  # first run only: download pinned Benchmark assets
just stack-up       # start AI Gateway :9105 and Engine :9108
just stack-status
```

Use `just stack-logs` to inspect startup failures and `just stack-down` when finished. Stack
management stays outside the notebook so **Run All** never starts or stops local services."""
    )


def _draco_candidate_policy_cell(*, synthesis: bool = False) -> NotebookNode:
    source = _string_assignment("DRACO_ANSWER_PROMPT", _DRACO_ANSWER_PROMPT_PARTS)
    if synthesis:
        source += "\n\n" + _string_assignment(
            "DRACO_SYNTHESIS_PROMPT",
            _DRACO_SYNTHESIS_PROMPT_PARTS,
        )
    return nbformat.v4.new_code_cell(source)


def _string_assignment(name: str, parts: tuple[str, ...]) -> str:
    literals = "\n".join(f"    {json.dumps(part, ensure_ascii=False)}" for part in parts)
    return f"{name} = (\n{literals}\n)"


def _quickstart() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace quickstart

Connect the configured SF Engine, define one Candidate, and run DRACO's bounded structural smoke
Benchmark. The Engine owns the Case, retrieval policy, Judge, Grading, and Aggregation."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_markdown_cell(
            """## Connect OpenRouter

`sf.connect()` renders the Engine-backed provider panel. Entering an API key sends it to the SF
Engine for AI Gateway validation and encrypted storage; the notebook does not retain it."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define a Candidate"),
        nbformat.v4.new_code_cell(
            'candidate = sf.Model("openrouter/google/gemini-3-flash-preview")'
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate

`draco/smoke` preserves the canonical DRACO execution structure while reducing multiplicity to one
pinned Case, one criterion, and one Judge pass. It makes two paid calls—one Candidate answer and one
Judge grade—so its score is diagnostic and **not comparable** to canonical DRACO."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(candidate, benchmark="draco/smoke")
report.to_json()"""
        ),
    )


def _draco_lite_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# DRACO Lite: a small retrieval-aware comparison

This notebook exercises both retrieval routes through the public ScreamingFace SDK. The Engine
owns the Case, retrieval policy, Judge, Grading, and Aggregation; each SDK Candidate owns only its
answer policy.

`draco/lite` uses two pinned representative Cases, ten criteria per Case, and one Judge pass per
criterion. It is useful for directional development checks, but its score is **not comparable**
to canonical DRACO.

> **Spend warning:** execution is disabled by default. Review the discovered Benchmark and set
> `RUN_EVALUATION = True` deliberately; **Run All** otherwise makes no model calls."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_markdown_cell(
            """Export `TAVILY_API_KEY` before `just stack-up`. A missing key fails the Tavily
Candidate before its first paid model request instead of silently running without retrieval. The
connection panel sends the OpenRouter key through the Engine to AI Gateway; the Client never calls
AI Gateway directly."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define one Candidate per retrieval route"),
        _draco_candidate_policy_cell(),
        nbformat.v4.new_code_cell(
            """DRACO_PARAMS = {"max_tokens": 8192, "temperature": 0.0}
DRACO_PARAMS_NO_TEMPERATURE = {"max_tokens": 8192}

native_search = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS_NO_TEMPERATURE,
)
tavily_search = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate DRACO Lite

The same Engine-owned lite protocol invokes both Candidates. The current reference deployment
routes GPT through provider-native search and Gemini Flash through the guarded Tavily tool loop.
Success proves both configured routes were available; a model may legitimately answer without
calling an offered function. The repository's forced-tool tests certify actual Tavily
`/search` and `/extract` dispatch deterministically."""
        ),
        nbformat.v4.new_code_cell(
            """RUN_EVALUATION = False

candidates = [native_search, tavily_search]
report = sf.evaluate(candidates, benchmark="draco/lite") if RUN_EVALUATION else None
report_output = (
    report.to_json()
    if report is not None
    else \"Evaluation disabled — set RUN_EVALUATION = True to spend.\"
)
report_output"""
        ),
        nbformat.v4.new_markdown_cell("## Inspect the Report"),
        nbformat.v4.new_code_cell("report.candidates if report is not None else None"),
        nbformat.v4.new_code_cell("report.usage if report is not None else None"),
    )


def _ifeval_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# IFEval on ScreamingFace: stable first run, then the research experiment

IFEval (arXiv:2311.07911) is 541 prompts with machine-checkable constraints — word
counts, forbidden punctuation, required sections. The Engine grades every response with
a deterministic verifier: **no judge model in the grading path, zero grading cost**.

The Engine publishes three independently revisioned IFEval Benchmarks that share Cases and verifier
assets:

- `ifeval` — one shot. A solo Model answers once; a Fusion's members answer and its
  synthesizer **blends** them into one new answer. The blend is checked.
- `ifeval/self-corrective` — three fixed attempts. The whole Candidate reads the
  checker's violations, **writes its own feedback, and retries**.
- `ifeval/verifying-ensemble` — the current verifying ensemble implementation based on
  Skurikhin et al. (https://openreview.net/forum?id=XSIYfTm2h7): every direct Fusion
  member is checked individually, and the **synthesizer acts as JUDGE** — it picks a
  passing answer word-for-word, or turns the violations into coaching when nobody
  passed. It never writes the answer on this exam.

One rule to remember: **the synthesizer plays two roles.** Blender on `ifeval`,
judge on `ifeval/verifying-ensemble`.

The required cells below use Haiku and Gemini Flash for a provider-stable one-Case
validation. Khoa's Kimi K3 configuration remains in the optional appendix because a
reasoning model can consume its completion budget before emitting answer text, and an
upstream provider can fail even when Gateway discovery succeeds."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_markdown_cell(
            """After pulling or merging SDK code, **restart this notebook's kernel before Run
All**. Python keeps already-imported SDK modules in memory; a stale kernel can ask the new Engine
for a pre-merge Benchmark id and receive `unknown_benchmark`."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## Stable smoke Candidates

These four cells are a **paid one-Case validation**, not a scientific result. Haiku is the
solo Candidate. The Fusion pairs Haiku with Gemini Flash and uses Flash as its synthesizer,
so the synthesizer is also a direct member — the shape used by Skurikhin et al. ([Ens-1]).

`progress=True` shows the live Engine stream. Raw URL4 node names are expected until
semantic Case/attempt events land."""
        ),
        nbformat.v4.new_code_cell(
            """smoke_model = sf.Model(
    "openrouter/anthropic/claude-haiku-4.5",
    params={"max_tokens": 4096},
)
smoke_judge = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    params={"max_tokens": 4096},
)

smoke_fusion = sf.Fusion(
    [smoke_model, smoke_judge],
    name="haiku-flash-smoke",
    synthesizer="openrouter/google/gemini-3-flash-preview",
    params={"max_tokens": 4096},
)
smoke_fusion"""
        ),
        nbformat.v4.new_markdown_cell(
            """## ① Baseline — one model, one shot

This validates the canonical paper-comparable protocol. One Case is only a plumbing check;
increase `limit` deliberately for a reported score."""
        ),
        nbformat.v4.new_code_cell(
            """canonical_smoke_model = sf.evaluate(
    smoke_model,
    benchmark="ifeval",
    limit=1,
    progress=True,
)
canonical_smoke_model"""
        ),
        nbformat.v4.new_markdown_cell(
            """## ② Does blending preserve instructions?

The synthesizer writes one NEW answer from the members' answers — new text the checker
never saw. A blend can break a constraint every member satisfied (add a comma, drop a
section). This cell measures that risk."""
        ),
        nbformat.v4.new_code_cell(
            """canonical_smoke_fusion = sf.evaluate(
    smoke_fusion,
    benchmark="ifeval",
    limit=1,
    progress=True,
)
canonical_smoke_fusion"""
        ),
        nbformat.v4.new_markdown_cell(
            """## ③ Can a model correct itself?

The ablation the paper never ran: {solo + feedback loop}. The model answers, the
checker reports violations, the model writes its own feedback and retries — up to
three attempts, earliest pass wins.

Cost: five model calls per case (three answers + two self-feedback authorings), all
unrolled."""
        ),
        nbformat.v4.new_code_cell(
            """corrective_smoke_model = sf.evaluate(
    smoke_model,
    benchmark="ifeval/self-corrective",
    limit=1,
    progress=True,
)
corrective_smoke_model"""
        ),
        nbformat.v4.new_markdown_cell(
            """## ④ The verifying ensemble (the paper's protocol)

Members answer, the checker checks **each draft individually**, and the synthesizer —
acting as judge here — picks a passing answer verbatim, or coaches everyone and retries
when nobody passed. A judge cannot break a constraint a member satisfied, because it
never rewrites the winning text.

Choose a synthesizer that reliably answers tersely: a judge reply that is not a bare
letter gets no vote (the deterministic passers-first rule decides instead), and the
synthesizer inherits provider-default params on this exam."""
        ),
        nbformat.v4.new_code_cell(
            """corrective_smoke_fusion = sf.evaluate(
    smoke_fusion,
    benchmark="ifeval/verifying-ensemble",
    limit=1,
    progress=True,
)
corrective_smoke_fusion"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Read the smoke results

- ① vs ② — did blending help or hurt instruction-following?
- ① vs ③ — how much does a feedback loop help one model?
- ③ vs ④ — self-correction vs ensemble correction, same loop, same exam.
- ② vs ④ — blend-then-check vs check-then-select.

Cost note: the iterative-correction exam has no early stop yet — all three attempts
always run (and the solo shape adds two self-feedback calls), so its token totals
overstate a stop-on-success system. Compare scores freely within a column; never
compare our costs to the paper's.

With one Case these values prove only that the complete contracts execute. They are not
benchmark results."""
        ),
        nbformat.v4.new_code_cell(
            """{
    name: {
        "score": report.candidates[0].score,
        "output_tokens": report.usage.output_tokens,
    }
    for name, report in {
        "① ifeval · haiku": canonical_smoke_model,
        "② ifeval · haiku-flash": canonical_smoke_fusion,
        "③ self-corrective · haiku": corrective_smoke_model,
        "④ verifying-ensemble · haiku-flash": corrective_smoke_fusion,
    }.items()
}"""
        ),
        *kimi_appendix(),
    )


def _draco_full_e2e() -> NotebookNode:
    notebook = _notebook(
        nbformat.v4.new_markdown_cell(
            """# Full DRACO pipeline through the ScreamingFace SDK

This is the SDK-native port of the full `pipeline_walkthrough.ipynb` in
`screamingface-benchmarks/notebooks/general/`.
It preserves the published Candidate surface—**7 solo Models and 9 Fusions**—using only the public
SDK. The Engine owns DRACO's dataset, judge, grading, and aggregation. Each SDK Candidate owns its
answer and synthesis policy.

This notebook always selects canonical `draco`: all 100 Cases, every criterion, and five Judge
passes per criterion. It has no smoke or lite switch, so a completed Report is unambiguously a
full Engine-protocol result.

> **Fidelity status:** `full` describes multiplicity, not byte-for-byte reference conformance.
> The Engine uses the DRACO dataset source, official per-criterion Judge instructions, published
> scoring math, reference answer/synthesis system prompts, and the 7-solo/9-Fusion lineup. Do not
> present its score as a reproduced paper or OpenRouter-blog number yet:
>
> - canonical Engine DRACO uses the paper's five Judge passes, while the current source walkthrough
>   uses three; the retired paper Judge is replaced by Gemini 3.1 Pro and `reasoning=low` is not yet
>   forwarded on that OpenRouter route;
> - answer retrieval is route-declared provider-native search or a Tavily search/fetch loop, not the
>   reference harness's single OpenRouter server-tool configuration and exact tool budgets;
> - Fusion writers receive the same question and ordered labeled panel answers, but the universal
>   SDK framing omits the reference template's final redundant “Produce the unified prose answer
>   now.” sentence and labels members by their public Recipe names;
> - the reference harness can reuse prior solo answers in Fusion panels; this run currently makes
>   independent Candidate calls. That can change spend and generated answers, although the grading
>   protocol is unchanged.

> **Spend warning:** execution is disabled by default. Set `RUN_EVALUATION = True` only after
> reviewing the full experiment's estimated scope."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_markdown_cell(
            """Export `TAVILY_API_KEY` before `just stack-up`: the Gemini, Kimi, DeepSeek, and
Qwen answer routes use its guarded tool loop, and the Engine fails before model spend when that
required retrieval mechanism is unavailable."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## 1. Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## 2. Define the full solo lineup

These are the seven solo Candidates from the original full-pipelines notebook. Qwen is also
defined because it participates in the open-source Fusion. The reference configuration requires
at least 8,192 output tokens for answer and tool paths, so this notebook pins that Candidate policy
instead of inheriting the SDK's smaller general default.

The Gateway's live model contract currently marks `temperature` unsupported for Fable 5 and
GPT-5.5. Their requests therefore omit it; every model that supports it retains the reference
temperature of zero."""
        ),
        _draco_candidate_policy_cell(synthesis=True),
        nbformat.v4.new_code_cell(
            """DRACO_PARAMS = {"max_tokens": 8192, "temperature": 0.0}
DRACO_PARAMS_NO_TEMPERATURE = {"max_tokens": 8192}

fable = sf.Model(
    "openrouter/anthropic/claude-fable-5",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS_NO_TEMPERATURE,
)
opus = sf.Model(
    "openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
gpt = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS_NO_TEMPERATURE,
)
gemini_pro = sf.Model(
    "openrouter/google/gemini-3.1-pro-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
gemini_flash = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
kimi = sf.Model(
    "openrouter/moonshotai/kimi-k2.6",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
deepseek = sf.Model(
    "openrouter/deepseek/deepseek-v4-pro",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
qwen = sf.Model(
    "openrouter/qwen/qwen3.6-plus",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 3. Define the nine Fusion Candidates

Each Fusion names the synthesizer from the reproduced configuration explicitly. Equivalent Models
deduplicate inside one Candidate graph. The self-Fusion uses explicit sample identities and
temperature so its two Opus calls remain independent. DRACO gives guarded retrieval to
answer-producing members; whole-Fusion synthesis and the Benchmark-owned Judge remain
retrieval-free.

The reference harness can reuse solo answers across overlapping Fusion panels. Until the Engine's
cross-Candidate cache lands, this SDK run evaluates each Candidate independently and may repeat
those member calls. The grading protocol stays fixed, but fresh provider calls can change both the
generated answer and spend; cross-harness scores therefore are not assumed identical."""
        ),
        nbformat.v4.new_code_cell(
            """fable_plus_gpt = sf.Fusion(
    [fable, gpt],
    name="fable_plus_gpt",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
frontier_trio = sf.Fusion(
    [opus, gpt, gemini_pro],
    name="frontier_trio",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
opus_plus_gpt = sf.Fusion(
    [opus, gpt],
    name="opus_plus_gpt",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
opus_self_fusion = sf.Fusion(
    [
        sf.Model(
            "openrouter/anthropic/claude-opus-4.8",
            name="opus-sample-1",
            prompt=DRACO_ANSWER_PROMPT,
            params={"max_tokens": 8192, "temperature": 0.7},
        ),
        sf.Model(
            "openrouter/anthropic/claude-opus-4.8",
            name="opus-sample-2",
            prompt=DRACO_ANSWER_PROMPT,
            params={"max_tokens": 8192, "temperature": 0.7},
        ),
    ],
    name="opus_self_fusion",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
budget_trio = sf.Fusion(
    [gemini_flash, kimi, deepseek],
    name="budget_trio",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
beat_runner_up = sf.Fusion(
    [opus, gpt, deepseek],
    name="beat_runner_up",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
pareto_cross = sf.Fusion(
    [deepseek, kimi, gpt],
    name="pareto_cross",
    synthesizer="openrouter/deepseek/deepseek-v4-pro",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
pareto_lean = sf.Fusion(
    [deepseek, kimi],
    name="pareto_lean",
    synthesizer="openrouter/deepseek/deepseek-v4-pro",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)
best_open_source = sf.Fusion(
    [deepseek, kimi, qwen],
    name="best_open_source",
    synthesizer="openrouter/deepseek/deepseek-v4-pro",
    prompt=DRACO_SYNTHESIS_PROMPT,
    params=DRACO_PARAMS,
)"""
        ),
        nbformat.v4.new_markdown_cell("## 4. Arm the canonical run explicitly"),
        nbformat.v4.new_code_cell("RUN_EVALUATION = False"),
        nbformat.v4.new_markdown_cell(
            """## 5. Evaluate every Candidate

One Evaluation runs the complete Candidate lineup concurrently. Leaving
`RUN_EVALUATION = False` makes **Run All** safe and performs no model calls."""
        ),
        nbformat.v4.new_code_cell(
            """candidates = [
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

report = sf.evaluate(candidates, benchmark="draco") if RUN_EVALUATION else None
report_output = (
    report.to_json()
    if report is not None
    else \"Evaluation disabled — set RUN_EVALUATION = True to spend.\"
)
report_output"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 6. Inspect the Report

The Report presents Candidate scores, failures, operation graphs, timing, and usage."""
        ),
        nbformat.v4.new_code_cell("report.candidates if report is not None else None"),
        nbformat.v4.new_code_cell("report.usage if report is not None else None"),
        nbformat.v4.new_code_cell("report.failures if report is not None else None"),
    )
    notebook.metadata["kernelspec"] = {
        "display_name": "screamingface (SDK)",
        "language": "python",
        "name": "screamingface-sdk",
    }
    return notebook


_HEALTH_SYNTHESIS_PROMPT_PARTS = (
    "You are synthesising the single best response to a health-related ",
    "conversation by combining independent responses from a panel of models. ",
    "A physician-authored rubric will grade your output per criterion — ",
    "accuracy, completeness, safety, and appropriate hedging all matter; so ",
    "does avoiding harmful or false content.\n\n",
    "Procedure:\n",
    "1. Read every panel response carefully.\n",
    "2. Identify what each contributes that the others miss (facts, safety ",
    "caveats, follow-up questions, care-seeking guidance).\n",
    "3. Produce ONE unified response to the final user turn that:\n",
    "   - Keeps every clinically correct, relevant point\n",
    "   - Drops anything inaccurate, unsafe, or speculative\n",
    "   - Resolves disagreements by favouring the safer, better-supported claim\n",
    "   - Stays concise — verbosity is not rewarded\n",
    "4. Do not introduce claims no panel member made.\n\n",
    "Output: the unified response only, no preamble, no JSON wrapper.",
)


def _healthbench_worst30_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# HealthBench worst-30% — the entry challenge

Can an open-weights Fusion beat our best open Fusion on the **157 hardest HealthBench
Professional conversations**? This notebook runs the challenge exam end to end: the Engine owns
the Cases, the pinned GPT-5.4 judge (house-paid), the per-rubric-item grading, and the
aggregation; you own the Candidate.

> **This is a challenge metric, NOT an official HealthBench score.** The exam scores the
> team-picked worst-30% subset with an UNCLIPPED mean (official HealthBench clips `max(0, mean)`
> over the full 5,000-row set). On these rows serious baselines score **negative** — that is
> normal, and exactly why the clip is removed: `-0.35 < -0.21 < -0.15` must rank.
>
> Protocol caveats vs the paper: one answer sample (the paper averages 8), no length-adjusted
> score, judge reasoning-effort not yet forwarded, floating `openai/gpt-5.4` slug. The published
> target comes from our own baselines rerun through THIS engine, so comparisons stay fair.

> **Spend warning:** the challenge run is disabled by default. `healthbench/smoke` below is the
> only cell that spends without a switch — one Candidate answer plus one judge call."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## 1. Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## 2. Structural smoke — pennies, not comparable

`healthbench/smoke` runs ONE pinned Case (a terse physician research query) through the full
grading chain: Candidate answer → pre-rendered official grader prompt → GPT-5.4 verdict →
unclipped aggregate. Two paid calls; its score is diagnostic only."""
        ),
        nbformat.v4.new_code_cell(
            """# Structural check of the ENTIRE grading chain on one Case (~2 paid calls):
#   - engine serves the case + baked rubric assets (preflight passes)
#   - your Candidate answers through the gateway
#   - the official grader prompt renders and the GPT-5.4 judge returns a
#     parseable verdict
#   - the aggregate scores it: expect `verdict_coverage: 1.0` and a non-null
#     `score` — a null score means a link in the chain failed (see `cases[*]`
#     for the per-Case failure reason)
# The score itself is diagnostic only — NOT comparable to any HealthBench number.
smoke_candidate = sf.Model("openrouter/deepseek/deepseek-v4-pro")
report = sf.evaluate(smoke_candidate, benchmark="healthbench/smoke")
report.to_json()"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 3. The challenge Candidate — an open trio

The engine's declared open-weights trio (DeepSeek-V4-Pro, Kimi-K2.6, Qwen3.6-plus — Qwen stands
in for July's GLM-5.2, which has no declared Engine route) with DeepSeek synthesising. Health
answers are graded on accuracy AND safety, so the synthesis policy favours the safer,
better-supported claim and stays concise.

The synthesis prompt below is **yours to change** — it is the baseline's recipe, not part of
the exam protocol. Rewriting it (and swapping panel members or the synthesizer) is the main
experiment surface of this challenge. Members and solo Candidates can carry their own answer
policy too — `sf.Model(..., prompt="...")` — the baseline leaves its members bare only because
the published target was measured that way."""
        ),
        nbformat.v4.new_code_cell(
            _string_assignment("HEALTH_SYNTHESIS_PROMPT", _HEALTH_SYNTHESIS_PROMPT_PARTS)
        ),
        nbformat.v4.new_code_cell(
            """# Members are BARE (no prompt) to match how the published target was measured.
# To experiment with a per-member answer policy, give any member its own prompt:
#   deepseek = sf.Model(
#       "openrouter/deepseek/deepseek-v4-pro",
#       prompt="You are a careful clinician. Answer accurately, flag uncertainty, "
#              "always include red-flag symptoms that warrant urgent care.",
#   )
deepseek = sf.Model("openrouter/deepseek/deepseek-v4-pro")
kimi = sf.Model("openrouter/moonshotai/kimi-k2.6")
qwen = sf.Model("openrouter/qwen/qwen3.6-plus")

open_trio = sf.Fusion(
    [deepseek, kimi, qwen],
    name="open_trio",
    synthesizer="openrouter/deepseek/deepseek-v4-pro",
    prompt=HEALTH_SYNTHESIS_PROMPT,
)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 4. Arm the challenge run explicitly

157 Cases × (3 members + 1 synthesis) answer calls plus ~350 house-paid judge calls per attempt.
Leaving `RUN_EVALUATION = False` keeps **Run All** free of model spend."""
        ),
        nbformat.v4.new_code_cell("RUN_EVALUATION = False"),
        nbformat.v4.new_code_cell(
            """if RUN_EVALUATION:
    report = sf.evaluate(open_trio, benchmark="healthbench/worst30")
    print(report.to_json())"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 5. Reading the Report

- `score` — the challenge metric: UNCLIPPED mean over all 157 Case scores. Negative is normal
  here; the number to beat is the published engine-rerun baseline.
- `metrics.verdict_coverage` — must be **1.0** for a valid attempt; any unjudged rubric item
  fails its Case loudly (`score` becomes `null`) rather than silently inflating the mean.
- `metrics.score_sd`, `metrics.judge_invalid_replies` — stability and judge health.
- `cases[*]` — per-Case rubric evidence: every judge verdict with its raw reply, the Candidate's
  exact answer, and the `[points] criterion` lines it was graded against."""
        ),
    )


def main() -> None:
    examples = Path(__file__).parents[1] / "examples"
    for name, value in notebooks().items():
        nbformat.write(value, examples / name)


if __name__ == "__main__":
    main()
