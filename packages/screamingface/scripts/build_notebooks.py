"""Build the public v1 notebooks deterministically."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat import NotebookNode


def notebooks() -> dict[str, NotebookNode]:
    return {
        "00_quickstart.ipynb": _quickstart(),
        "05_draco_e2e.ipynb": _draco_e2e(),
        "06_draco_full_e2e.ipynb": _draco_full_e2e(),
        "07_ifeval_e2e.ipynb": _ifeval_e2e(),
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


def _quickstart() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace quickstart

Connect the configured SF Engine, define Candidates, and evaluate them."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Connect OpenRouter

`sf.connect()` renders the Engine-backed provider panel. Entering an API key sends it to the SF
Engine for AI Gateway validation and encrypted storage; the notebook does not retain it."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define Candidates"),
        nbformat.v4.new_code_cell(
            """opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier = sf.Fusion([opus, gpt])"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate

Select DRACO explicitly. `limit=1` selects one of its 100 cases, but still evaluates every
criterion in that case with the paper-aligned five Judge passes. The Benchmark owns Judge and
aggregation policy."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    [opus, gpt, frontier],
    benchmark="draco",
    limit=1,
    on_event=print,
    progress=False,
)
report"""
        ),
    )


def _draco_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# DRACO smoke run: Client → URL4 Engine → AI Gateway

This notebook exercises the complete pipeline through the public ScreamingFace SDK. The Engine
owns the dataset, judge, grading, and aggregation; the SDK Candidate owns answer policy.

> **Cost warning:** the evaluation cell performs one Candidate call plus five Judge calls for
> every criterion in the selected case. Discovery makes no model calls."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Before running

The local AI Gateway must be running on `127.0.0.1:9105`, and the isolated Engine demo must be
running on `127.0.0.1:9108`. The connection panel sends the OpenRouter key through the Engine to
AI Gateway; the Client never calls AI Gateway directly.

For a host-local Engine, prepare DRACO's pinned Cases and pass their root explicitly:

```bash
uv run --with datasets python -m url4_cloud.benchmarks.draco.prepare \\
  --out /tmp/screamingface-benchmark-assets/draco
URL4_BENCHMARK_ASSETS=/tmp/screamingface-benchmark-assets \\
  uv run url4-cloud serve --local
```

`/opt/benchmarks` is the container image default and normally does not exist on the host."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define a Candidate"),
        nbformat.v4.new_code_cell('haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")'),
        nbformat.v4.new_markdown_cell(
            """## Evaluate the benchmark

Running the next cell evaluates one Candidate answer against every rubric criterion, with five
independent Judge calls per criterion."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    haiku,
    benchmark="draco",
    limit=1,
)
report"""
        ),
        nbformat.v4.new_markdown_cell("## Inspect the Report"),
        nbformat.v4.new_code_cell("report.candidates"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("report.to_json()"),
    )


def _ifeval_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# IFEval on ScreamingFace: two exams, four experiments

IFEval (arXiv:2311.07911) is 541 prompts with machine-checkable constraints — word
counts, forbidden punctuation, required sections. The Engine grades every response with
a deterministic verifier: **no judge model in the grading path, zero grading cost**.

There are two Benchmarks, and each adapts to the Candidate you hand it:

- `ifeval` — one shot. A solo Model answers once; a Fusion's members answer and its
  synthesizer **blends** them into one new answer. The blend is checked.
- `ifeval-iterative-correction` — up to three attempts. A solo Model reads the checker's
  violations, **writes its own feedback, and retries**. A Fusion runs the verifying
  ensemble of Skurikhin et al. (https://openreview.net/forum?id=XSIYfTm2h7): every
  member is checked individually, and the **synthesizer acts as JUDGE** — it picks a
  passing answer word-for-word, or turns the violations into coaching when nobody
  passed. It never writes the answer on this exam.

One rule to remember: **the synthesizer plays two roles.** Blender on `ifeval`,
judge on `ifeval-iterative-correction`."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Before running

AI Gateway on `127.0.0.1:9105`, Engine on `127.0.0.1:9108`. From `packages/screamingface/`:

```bash
just stack-prepare   # once — downloads the pinned benchmark cases
just stack-up        # gateway :9105 + engine :9108 (logs: just stack-logs)
```"""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## The Candidates

Two models and one Fusion. The Fusion's synthesizer is also a member — the
winning ensemble of Skurikhin et al. ([Ens-1]) is shaped exactly like this: two
members, with the judge doubling as one of them."""
        ),
        nbformat.v4.new_code_cell(
            """kimi = sf.Model("openrouter/moonshotai/kimi-k3", params={"max_tokens": 4096})
haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")

fusion = sf.Fusion(
    [kimi, haiku],
    name="kimi-haiku",
    synthesizer="openrouter/moonshotai/kimi-k3",
)
fusion"""
        ),
        nbformat.v4.new_markdown_cell(
            """## ① Baseline — one model, one shot

Comparable to published IFEval numbers."""
        ),
        nbformat.v4.new_code_cell(
            """canonical_1_model = sf.evaluate(
    kimi,
    benchmark="ifeval",
    limit=3,
    progress=False,
)
canonical_1_model"""
        ),
        nbformat.v4.new_markdown_cell(
            """## ② Does blending preserve instructions?

The synthesizer writes one NEW answer from the members' answers — new text the checker
never saw. A blend can break a constraint every member satisfied (add a comma, drop a
section). This cell measures that risk."""
        ),
        nbformat.v4.new_code_cell(
            """canonical_fusion = sf.evaluate(
    fusion,
    benchmark="ifeval",
    limit=3,
    progress=False,
)
canonical_fusion"""
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
            """iterative_1_model = sf.evaluate(
    kimi,
    benchmark="ifeval-iterative-correction",
    limit=3,
    progress=False,
)
iterative_1_model"""
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
            """iterative_fusion = sf.evaluate(
    fusion,
    benchmark="ifeval-iterative-correction",
    limit=3,
    progress=False,
)
iterative_fusion"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Reading the four scores

- ① vs ② — did blending help or hurt instruction-following?
- ① vs ③ — how much does a feedback loop help one model?
- ③ vs ④ — self-correction vs ensemble correction, same loop, same exam.
- ② vs ④ — blend-then-check vs check-then-select.

Cost note: the iterative-correction exam has no early stop yet — all three attempts
always run (and the solo shape adds two self-feedback calls), so its token totals
overstate a stop-on-success system. Compare scores freely within a column; never
compare our costs to the paper's."""
        ),
        nbformat.v4.new_code_cell(
            """{
    name: {
        "score": report.candidates[0].score,
        "output_tokens": report.usage.output_tokens,
    }
    for name, report in {
        "① ifeval · kimi": canonical_1_model,
        "② ifeval · fusion": canonical_fusion,
        "③ iterative-correction · kimi": iterative_1_model,
        "④ iterative-correction · fusion": iterative_fusion,
    }.items()
}"""
        ),
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

> **Spend warning:** the evaluation cell is paid. It uses one case per Candidate; remove `limit=1`
> only when you intend to run the complete dataset."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## 1. Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## 2. Define the full solo lineup

These are the seven solo Candidates from the original full-pipelines notebook. Qwen is also
defined because it participates in the open-source Fusion."""
        ),
        nbformat.v4.new_code_cell(
            """fable = sf.Model("openrouter/anthropic/claude-fable-5")
opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")
gemini_pro = sf.Model("openrouter/google/gemini-3.1-pro-preview")
gemini_flash = sf.Model("openrouter/google/gemini-3-flash-preview")
kimi = sf.Model("openrouter/moonshotai/kimi-k2.6")
deepseek = sf.Model("openrouter/deepseek/deepseek-v4-pro")
qwen = sf.Model("openrouter/qwen/qwen3.6-plus")"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 3. Define the nine Fusion Candidates

The Benchmark supplies the synthesizer automatically. Equivalent Models deduplicate across the
graph. The self-Fusion uses explicit sample identities so its two Opus calls remain independent."""
        ),
        nbformat.v4.new_code_cell(
            """fable_plus_gpt = sf.Fusion([fable, gpt])
frontier = sf.Fusion([opus, gpt, gemini_pro])
opus_plus_gpt = sf.Fusion([opus, gpt])
opus_self_fusion = sf.Fusion(
    [
        sf.Model("openrouter/anthropic/claude-opus-4.8", name="opus-sample-1"),
        sf.Model("openrouter/anthropic/claude-opus-4.8", name="opus-sample-2"),
    ]
)
budget = sf.Fusion([gemini_flash, kimi, deepseek])
beat_runner_up = sf.Fusion([opus, gpt, deepseek])
pareto = sf.Fusion([deepseek, kimi, gpt])
pareto_lean = sf.Fusion([deepseek, kimi])
best_open_source = sf.Fusion([deepseek, kimi, qwen])"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 4. Evaluate every Candidate

One evaluation call runs the complete Candidate lineup against DRACO. Candidates run
concurrently under the Client's internal scheduler; the Benchmark supplies all other execution
policy."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    [
        fable,
        opus,
        gpt,
        gemini_pro,
        gemini_flash,
        kimi,
        deepseek,
        fable_plus_gpt,
        frontier,
        opus_plus_gpt,
        opus_self_fusion,
        budget,
        beat_runner_up,
        pareto,
        pareto_lean,
        best_open_source,
    ],
    benchmark="draco",
    limit=1,
)
report"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 5. Inspect the Report

The Report presents Candidate scores, failures, operation graphs, timing, and usage."""
        ),
        nbformat.v4.new_code_cell("report.candidates"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("report.failures"),
        nbformat.v4.new_code_cell("report.to_json()"),
    )
    notebook.metadata["kernelspec"] = {
        "display_name": "screamingface (SDK)",
        "language": "python",
        "name": "screamingface-sdk",
    }
    return notebook


def main() -> None:
    examples = Path(__file__).parents[1] / "examples"
    for name, value in notebooks().items():
        nbformat.write(value, examples / name)


if __name__ == "__main__":
    main()
