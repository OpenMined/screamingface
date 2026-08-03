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
            """# IFEval: canonical and corrective protocols through ScreamingFace

IFEval (arXiv:2311.07911) carries 541 prompts with machine-checkable constraints — word
counts, forbidden punctuation, required sections. The Engine grades every response with a
deterministic verifier: **no judge model, zero grading cost**.

The Engine publishes three independently named Benchmark protocols from the same IFEval
family:

- `ifeval`: the canonical single-answer protocol, comparable to published IFEval results.
- `ifeval-corrective`: three fixed answer/check attempts with sanitized verifier feedback.
- `ifeval-corrective-ensemble`: three members are separately checked and retried before a
  pinned Benchmark Judge selects one answer.

The SDK does not implement any protocol. It links a Model or Fusion into the complete
URL4 supplied by the selected Benchmark. Model calls are the only spend; discovery and
deterministic grading are free."""
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

Before spending anything, read what the exams actually are. Discovery is free — plain
Engine REST, no model calls. The three resources share `family="ifeval"`, but have different
identities, revisions, protocols, costs, and scores."""
        ),
        nbformat.v4.new_code_cell("sf.benchmarks.list()"),
        nbformat.v4.new_code_cell(
            'canonical_benchmark = sf.benchmarks.get("ifeval")\n'
            'corrective_benchmark = sf.benchmarks.get("ifeval-corrective")\n'
            'ensemble_benchmark = sf.benchmarks.get("ifeval-corrective-ensemble")\n'
            "canonical_benchmark, corrective_benchmark, ensemble_benchmark"
        ),
        nbformat.v4.new_markdown_cell(
            """### Read real prompts

Each prompt carries its constraints **in its own text** — "no commas", "at least 300
words", "highlight 3 sections". That is what makes IFEval machine-checkable: the Engine's
deterministic verifier re-reads the response against exactly those constraints, so
grading needs no judge model. Both variants use the same cases. Page further with
`canonical_benchmark.cases(limit=3, offset=100)`."""
        ),
        nbformat.v4.new_code_cell("canonical_benchmark.cases(limit=3)"),
        nbformat.v4.new_markdown_cell("## Define a Candidate"),
        nbformat.v4.new_code_cell('haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")'),
        nbformat.v4.new_markdown_cell(
            """## Run canonical IFEval

Canonical IFEval invokes the Candidate once and deterministically checks that answer.
`limit=3` selects three cases; it does not select a smaller Benchmark variant."""
        ),
        nbformat.v4.new_code_cell(
            """canonical = sf.evaluate(
    haiku,
    benchmark="ifeval",
    limit=3,
    progress=False,
)
canonical"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Run the corrective IFEval variant

The corrective Benchmark owns a fixed three-attempt protocol. After attempts one and
two, its deterministic checker converts failures into sanitized constraint feedback and
the same Candidate tries again. URL4 currently has no conditional early stop, so all
three attempts run even if the first answer passes.

For `limit=3`, this means nine Candidate calls. The aggregate selects the earliest strict
pass, or the final attempt if none passes. Its result is a different experiment from
canonical IFEval and must be reported under its own Benchmark identity."""
        ),
        nbformat.v4.new_code_cell(
            """corrective = sf.evaluate(
    haiku,
    benchmark="ifeval-corrective",
    limit=3,
    progress=False,
)
corrective"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Compare the two experiments

The corrective score may improve, but it pays for three attempts per case. Keep its score
and token use separate from canonical published IFEval results."""
        ),
        nbformat.v4.new_code_cell(
            """{
    "canonical": {
        "score": canonical.candidates[0].score,
        "output_tokens": canonical.usage.output_tokens,
        "metrics": dict(canonical.candidates[0].metrics),
    },
    "corrective": {
        "score": corrective.candidates[0].score,
        "output_tokens": corrective.usage.output_tokens,
        "metrics": dict(corrective.candidates[0].metrics),
    },
}"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Audit the complete URL4

Each report contains the exact complete URL4 that executed. The canonical expression has
one Candidate invocation; the corrective expression has three and two feedback steps.
The client did not construct or interpret this workflow."""
        ),
        nbformat.v4.new_code_cell(
            """canonical_url4 = canonical.candidates[0].url4
corrective_url4 = corrective.candidates[0].url4

print("canonical candidate invocations :", canonical_url4.count("/candidate?"))
print("corrective candidate invocations:", corrective_url4.count("/candidate?"))
print("corrective feedback steps       :", corrective_url4.count("!'feedback'"))"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Peek at the raw execution stream (optional)

Every run streams events while it executes. Today they describe raw url4 node
lifecycle (semantic events — "case 3, attempt 2" — are in flight engine-side), but
even the raw counts show the machine at work: one evaluation fans out into dozens of
nodes, and only the model calls cost anything."""
        ),
        nbformat.v4.new_code_cell(
            """from collections import Counter

events = []
sf.evaluate(haiku, benchmark="ifeval-corrective", limit=1, on_event=events.append, progress=False)
Counter(event.kind for event in events)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate a normal Fusion

A Fusion is still an ordinary Candidate: its members answer and its synthesizer produces
one final answer. Either Benchmark can invoke that Candidate without any IFEval-specific
SDK type.

Running a Fusion against `ifeval-corrective` retries and verifies the **Fusion's final
answer** three times. Kimi receives an explicit 16384-token ceiling because this reasoning
model can consume smaller completion budgets before emitting final answer text on longer
IFEval prompts. That is Candidate policy rather than Benchmark behavior."""
        ),
        nbformat.v4.new_code_cell(
            """kimi = sf.Model(
    "openrouter/moonshotai/kimi-k2.6",
    params={"max_tokens": 16384},
)
deepseek = sf.Model("openrouter/deepseek/deepseek-v4-pro")
qwen = sf.Model("openrouter/qwen/qwen3.6-plus")

fusion = sf.Fusion(
    [kimi, deepseek, qwen],
    name="three-model fusion",
    synthesizer="openrouter/google/gemini-3-flash-preview",
)
fusion"""
        ),
        nbformat.v4.new_code_cell(
            """duel = sf.evaluate(
    [haiku, fusion],
    benchmark="ifeval-corrective",
    limit=1,
    progress=False,
)
duel"""
        ),
        nbformat.v4.new_markdown_cell(
            """Both rows above use the same corrective Benchmark protocol. Their scores are
comparable to one another, while their token totals expose the cost of the Fusion. Candidate
lists execute concurrently, so this live example stays at one case to avoid turning the local
Gateway and upstream provider's concurrency limits into part of the experiment."""
        ),
        nbformat.v4.new_code_cell(
            """{
    candidate.name: {
        "score": candidate.score,
        "output_tokens": candidate.usage.output_tokens,
    }
    for candidate in duel.candidates
}"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Run the member-level corrective ensemble

This is a separately revisioned experiment. It requires exactly three direct Model members.
The Benchmark invokes those members structurally, verifies and retries each one independently
for three attempts, and uses its pinned Flash Judge to select one answer per attempt. The
earliest passing selection becomes the final answer and receives canonical IFEval scoring.

The Fusion's ordinary final synthesizer is not invoked in this protocol. The SDK merely exposes
the three member expressions as universal bindings; all correction and selection behavior lives
inside the Engine-owned Benchmark URL4."""
        ),
        nbformat.v4.new_code_cell(
            """ensemble_report = sf.evaluate(
    fusion,
    benchmark="ifeval-corrective-ensemble",
    limit=1,
    progress=False,
)
ensemble_report"""
        ),
        nbformat.v4.new_code_cell(
            """ensemble_url4 = ensemble_report.candidates[0].url4
print("member invocations per case:", ensemble_url4.count("/candidate_model_member_"))
print("judge invocations per case :", ensemble_url4.count("gemini-3-flash-preview"))"""
        ),
        nbformat.v4.new_markdown_cell("## Inspect the full Report"),
        nbformat.v4.new_code_cell("corrective.candidates"),
        nbformat.v4.new_code_cell("corrective.usage"),
        nbformat.v4.new_code_cell("corrective.to_json()"),
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
