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
            """# IFEval smoke run: judge-free grading through the ScreamingFace SDK

IFEval (arXiv:2311.07911) carries 541 prompts with machine-checkable constraints — word
counts, forbidden punctuation, required sections. The Engine grades every response with a
deterministic verifier: **no judge model, zero grading cost**.

> **Cost note:** the evaluation cell performs exactly one Candidate call per selected
> case and nothing else. Discovery makes no model calls."""
        ),
        nbformat.v4.new_markdown_cell(
            """## Before running

The local AI Gateway must be running on `127.0.0.1:9105`, and the isolated Engine demo must be
running on `127.0.0.1:9108`. The connection panel sends the OpenRouter key through the Engine to
AI Gateway; the Client never calls AI Gateway directly.

For a host-local Engine, prepare IFEval's pinned cases (this also downloads the offline
NLTK tokenizer corpus the verifier reads) and pass the assets root explicitly:

```bash
uv run --with datasets python -m url4_cloud.benchmarks.ifeval.prepare \\
  --out /tmp/screamingface-benchmark-assets/ifeval
URL4_BENCHMARK_ASSETS=/tmp/screamingface-benchmark-assets \\
  uv run url4-cloud serve --local
```

`/opt/benchmarks` is the container image default and normally does not exist on the host."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## Meet the benchmark

Before spending anything, read what the exam actually is. Discovery is free — plain
Engine REST, no model calls."""
        ),
        nbformat.v4.new_code_cell("sf.benchmarks.list()"),
        nbformat.v4.new_code_cell('ifeval = sf.benchmarks.get("ifeval")\nifeval'),
        nbformat.v4.new_markdown_cell(
            """### Read real prompts

Each prompt carries its constraints **in its own text** — "no commas", "at least 300
words", "highlight 3 sections". That is what makes IFEval machine-checkable: the Engine's
deterministic verifier re-reads the response against exactly those constraints, so
grading needs no judge model. Page further with `ifeval.cases(limit=3, offset=100)`."""
        ),
        nbformat.v4.new_code_cell("ifeval.cases(limit=3)"),
        nbformat.v4.new_markdown_cell("## Define a Candidate"),
        nbformat.v4.new_code_cell('haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")'),
        nbformat.v4.new_markdown_cell(
            """## Evaluate the benchmark

`limit=5` selects the first five of IFEval's 541 prompts — five Candidate calls total.
The primary score is the paper's prompt-level strict accuracy; instruction-level and
loose readings arrive in the metrics."""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    haiku,
    benchmark="ifeval",
    limit=5,
)
report"""
        ),
        nbformat.v4.new_markdown_cell("## Inspect the Report"),
        nbformat.v4.new_code_cell("report.candidates"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("report.to_json()"),
        nbformat.v4.new_markdown_cell(
            """## R1 preview — probing the corrective-loop syntax (no services, no cost)

Everything above was **R0**: each candidate answers each prompt once. The LANL paper's
result (97.34% strict with small models) comes from a **corrective loop**: answer →
deterministic check → turn violations into feedback → retry, bounded at 3 attempts.

In url4 that loop *unrolls* into a nested expression with **named siblings**:

```
( prior_2:( prior_1:()/member!'attempt-1',
            grade:($prior_1)/check!'…'      ← checker reads the FIRST answer
          )/member!'attempt-2',              ← second attempt sees answer + feedback
  grade:($prior_2)/check!'…' )!'$…'
```

Two things must be true for this to work, and we can test both **right here** — the
`url4` package in this environment is the *same* DAG engine the Cloud embeds. The probe
below builds a miniature world with two fake routes (no model, no network, $0):

- `/member` — a stand-in candidate. It answers **with a comma** on attempt 1; if its
  input contains checker feedback, it corrects itself.
- `/grade` — a stand-in verifier: passes iff the answer has no comma (the real thing is
  the vendored IFEval checker behind `/check`).

What we're proving: **(a)** named siblings (`prior_1:`, `grade_1:`) execute and are
referenceable as `$prior_1`; **(b)** a `grade:` node can target a *deterministic route*,
not just a model."""
        ),
        nbformat.v4.new_code_cell(
            """import json

from url4 import RelExpr, Text, expr, render, src
from url4.peer.server import Request, Url4Node

probe = Url4Node("r1-probe")
# Every route call is recorded here in execution order, so each attempt's answer
# and each checker verdict stay visible after the run.
trace: list[dict] = []


@probe.endpoint("/member")
def member(request: Request) -> str:
    context = request.context or ""
    # Attempt 2 receives the attempt-1 answer + checker feedback as its input.
    if "feedback" in context.lower() and "PASSED" not in context:
        answer = "Tea is warm and nice without a single comma"
    else:
        answer = "Tea is warm, and it is nice."
    trace.append({"route": "/member", "intent": request.intent, "in": context, "out": answer})
    return answer


@probe.endpoint("/grade")
def grade(request: Request) -> str:
    answer = request.context or ""
    passed = "," not in answer
    verdict = json.dumps(
        {"passed": passed, "feedback": "PASSED" if passed else "violation: remove every comma"}
    )
    trace.append({"route": "/grade", "intent": request.intent, "in": answer, "out": verdict})
    return verdict"""
        ),
        nbformat.v4.new_markdown_cell(
            """Build the two-attempt chain. Reading inside-out: `prior_1` answers, `grade_1`
checks it (note its input is the *reference* `$prior_1`), the whole group becomes
attempt 2's input, and `grade_2` checks the retry. The rendered string is the same
syntax shape as the full 3-attempt R1 chain."""
        ),
        nbformat.v4.new_code_cell(
            """def check(reference: str) -> RelExpr:
    return RelExpr(path="/grade", context=reference, intent=Text("no_comma"))


attempt_1 = expr(
    src(
        RelExpr(path="/member", context="Describe tea. No commas.", intent=Text("attempt-1")),
        name="prior_1",
        weight=0.0,
    ),
    src(check("$prior_1"), name="grade_1", weight=0.0),
    intent=Text("previous answer: $prior_1 | checker feedback: $grade_1"),
)
chain = expr(
    src(
        RelExpr(path="/member", context=render(attempt_1), intent=Text("attempt-2")),
        name="prior_2",
        weight=0.0,
    ),
    src(check("$prior_2"), name="grade_2", weight=0.0),
    intent=Text("final answer: $prior_2 | final grade: $grade_2"),
)
print(render(chain))"""
        ),
        nbformat.v4.new_code_cell(
            """trace.clear()
result = await probe.evaluate(render(chain))
result.text"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Watch the loop happen

The trace shows every route call in execution order — `prior_1`'s answer, its verdict,
the feedback flowing into attempt 2, and the retry's verdict:"""
        ),
        nbformat.v4.new_code_cell(
            """for index, step in enumerate(trace, 1):
    print(f"step {index} — {step['route']} !{step['intent']}")
    print(f"   in : {step['in'][:110]}")
    print(f"   out: {step['out']}")
    print()"""
        ),
        nbformat.v4.new_markdown_cell(
            """**How to read the trace:** step 1 — attempt 1 answers *with* a comma. Step 2 — the
checker fails it and names the exact violation. Step 3 — attempt 2's input carries the
prior answer **and** that feedback, so it corrects itself. Step 4 — the retry passes.
The corrective loop's data flow works end-to-end in today's url4 syntax.

Still open before real R1 (`OME-721`): linking the *same real candidate* into all
attempt slots, per-member checks for ensembles, and the cost caveat — an unrolled chain
runs every attempt even when attempt 1 already passed, so R1 claims accuracy only."""
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
