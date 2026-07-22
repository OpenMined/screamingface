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

Run the complete DRACO comparison shape—**7 solo models and 9 Fusions**—over one real research
question. DRACO Lite changes only the scale: it keeps ten deterministic criteria spanning the
rubric's sections and runs one judge pass per criterion.

This is a real paid run, but it is **not a production DRACO score**. Production `draco@1` uses all
100 questions, complete rubrics, and five judge passes.

## Before you run it

Have a compatible ScreamingFace engine available. Its operator must configure an accepted
Hugging Face dataset token, an executable OpenRouter catalog, and the versioned DRACO routes. The
SDK package does not bundle or start that deployment.

The SDK talks only to the ScreamingFace engine. The engine loads the pinned DRACO case, executes
URL4, calls AI Gateway for OpenRouter inference, applies the benchmark's research-tool policy,
grades every final candidate, and aggregates the comparison."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Connect"),
        nbformat.v4.new_code_cell("import screamingface as sf\n\nsf.connect()"),
        nbformat.v4.new_markdown_cell(
            """Connect **OpenRouter**. One engine-scoped API key covers every model route below.
Dataset access is separate: the dataset token belongs in the engine deployment environment.

## 2 · Compose the candidates

The model lineup uses currently available OpenRouter routes, but the candidate topology matches the
full DRACO comparison. Reusing the same Python object shares that answer across dependent Fusions.
The two self-fusion samples are separate objects, so both execute. Ordinary Model names are inferred
from the last part of their routes; only the two samples need explicit names."""
        ),
        nbformat.v4.new_code_cell(
            '''DRACO_ANSWER_PROMPT = """You are answering a research-quality prompt.
Provide a thorough, well-reasoned answer in prose. Address every aspect the prompt raises.
Use clear structure
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

fable = sf.Model(
    "openrouter/anthropic/claude-fable-5",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
opus = sf.Model(
    "openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
gpt = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
gemini_pro = sf.Model(
    "openrouter/google/gemini-3.1-pro-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
gemini_flash = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
kimi = sf.Model(
    "openrouter/moonshotai/kimi-k2.5",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
deepseek = sf.Model(
    "openrouter/deepseek/deepseek-v4-pro",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)
qwen = sf.Model(  # Fusion-only leaf
    "openrouter/qwen/qwen3.6-plus",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0, "max_tokens": 8192},
)

fable_plus_gpt = sf.Fusion(
    "fable-plus-gpt",
    members=[fable, gpt],
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
frontier_trio = sf.Fusion(
    "frontier-trio",
    members=[opus, gpt, gemini_pro],
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
opus_plus_gpt = sf.Fusion(
    "opus-plus-gpt",
    members=[opus, gpt],
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
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
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
budget_trio = sf.Fusion(
    "budget-trio",
    members=[gemini_flash, kimi, deepseek],
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
beat_runner_up = sf.Fusion(
    "beat-runner-up",
    members=[opus, gpt, deepseek],
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
pareto_cross = sf.Fusion(
    "pareto-cross",
    members=[deepseek, kimi, gpt],
    reducer=sf.reducers.Model(
        model="openrouter/deepseek/deepseek-v4-pro",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
pareto_lean = sf.Fusion(
    "pareto-lean",
    members=[deepseek, kimi],
    reducer=sf.reducers.Model(
        model="openrouter/deepseek/deepseek-v4-pro",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)
best_open_source = sf.Fusion(
    "best-open-source",
    members=[deepseek, kimi, qwen],
    reducer=sf.reducers.Model(
        model="openrouter/deepseek/deepseek-v4-pro",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"temperature": 0, "max_tokens": 8192},
    ),
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

len(candidates)'''
        ),
        nbformat.v4.new_markdown_cell(
            """## 3 · Evaluate the scaled-down study

One call compiles and sends **one shareable URL4** for the complete candidate study. Within the
single case, the engine executes 10 distinct researched model samples, reuses them wherever the
same object appears, performs 9 synthesis calls, then grades the 16 final candidates.

Nominal total: **10 research + 9 synthesis + (16 × 10 criteria × 1 pass) = 179 model calls**.
Tool operations and any explicit validation retry are additional. OpenRouter spend and provider
availability still apply."""
        ),
        nbformat.v4.new_code_cell(
            'draco = sf.benchmarks.load("draco-lite@1")\nreport = draco.evaluate(candidates)'
        ),
        nbformat.v4.new_markdown_cell("## 4 · Compare"),
        nbformat.v4.new_code_cell("report"),
        nbformat.v4.new_markdown_cell(
            """`report.candidates` preserves the declared order and contains each candidate's score,
coverage, metrics, and typed failures. `report.best` returns the highest-scoring completed
candidate.
`report.url4` is the exact complete study transaction that can be shared and rerun against a
compatible ScreamingFace engine."""
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
