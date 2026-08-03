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

This notebook runs the **corrective** method (the default): a bounded retry loop where
the checker's violations feed each retry — the protocol of
[*Beyond Leaderboards: Tokenomics of Agentic Small Language Model Ensembles*](https://openreview.net/forum?id=XSIYfTm2h7)
(Skurikhin et al., Los Alamos National Laboratory). Model calls are the only spend;
discovery and grading are free."""
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
            """## Evaluate — the corrective chain (the default method)

IFEval here has two **methods** (the catalog entry above lists them):

- **`corrective`** (default) — the retry loop from
  [Skurikhin et al. (Los Alamos National Laboratory)](https://openreview.net/forum?id=XSIYfTm2h7),
  unrolled: the candidate answers, the deterministic checker grades it, the checker's
  *violations* are fed back, and the candidate retries — up to 3 attempts per prompt.
- **`single_pass`** — the paper's protocol: one answer, one check. This is the only
  score comparable to published IFEval numbers.

> **Cost note:** the chain is unrolled, so `limit=3` spends **9 candidate calls**
> (3 prompts × 3 attempts — every attempt runs even when the first one passed).
> Grading is still free.

Data flow (the exam owns the loop; haiku is just the answerer):

```text
SDK ── GET /v1/benchmarks/ifeval ──▶ Engine returns the CORRECTIVE url4
SDK links haiku into the one /candidate slot, submits ONE url4

per case (×3):
  haiku answers ─────────────────────▶ /check ▶ record 1
  haiku + answer 1 + verdict 1 ──────▶ /check ▶ record 2   (retry sees violations)
  haiku + answer 2 + verdict 2 ──────▶ /check ▶ record 3   (always runs — unrolled)

/aggregate: earliest strict-passing attempt is the case's answer
  ▶ score (retry protocol) + pass_at_1/2/3 + corrected_cases
```"""
        ),
        nbformat.v4.new_code_cell(
            """report = sf.evaluate(
    haiku,
    benchmark="ifeval",
    limit=3,
)
report"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Observe 1 — pass@attempt: two experiments hiding in one run

- `pass_at_1` is the **single-pass baseline**: the fraction of prompts the model
  nailed on its first try. This is the number you would compare (informally) to
  published IFEval scores.
- `pass_at_3` is what the corrective loop achieves — the headline `score`.
- `corrected_cases` counts prompts the checker's feedback actually **saved**: failed
  at attempt 1, passed later. If `pass_at_1 == pass_at_3`, the model needed no help
  on this slice — try a bigger `limit` or a smaller model to see the loop earn its
  keep."""
        ),
        nbformat.v4.new_code_cell("report.candidates[0].metrics"),
        nbformat.v4.new_markdown_cell(
            """### Observe 2 — the experiment protocol is readable

The Engine sent back the *entire experiment* as one url4 expression before anything
ran — `report.candidates[0].url4` is the exact plan that executed. You can audit the
loop right in the string: three candidate slots, three checker calls, and the retry
prompt threading the previous verdict forward."""
        ),
        nbformat.v4.new_code_cell(
            """plan = report.candidates[0].url4
print("attempts per case       :", plan.count("/candidate("))
print("checker calls per case  :", plan.count("/check("))
print("retry sees the verdict  :", "Checker verdict (JSON)" in plan)
print("exam revision in routes :", report.benchmark.revision in plan)"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Observe 3 — what the loop costs

Run the same slice with `method="single_pass"` and compare: the corrective run burns
roughly 3× the tokens for whatever accuracy it buys. (This is why corrective scores
must never sit next to published single-pass numbers — different protocol, different
budget.)"""
        ),
        nbformat.v4.new_code_cell(
            """baseline = sf.evaluate(haiku, benchmark="ifeval", limit=3, method="single_pass")
{
    "corrective": {
        "score": report.candidates[0].score,
        "output_tokens": report.usage.output_tokens,
    },
    "single_pass": {
        "score": baseline.candidates[0].score,
        "output_tokens": baseline.usage.output_tokens,
    },
}"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Observe 4 — peek at the raw execution stream (optional)

Every run streams events while it executes. Today they describe raw url4 node
lifecycle (semantic events — "case 3, attempt 2" — are in flight engine-side), but
even the raw counts show the machine at work: one evaluation fans out into dozens of
nodes, and only the model calls cost anything."""
        ),
        nbformat.v4.new_code_cell(
            """from collections import Counter

events = []
sf.evaluate(haiku, benchmark="ifeval", limit=1, on_event=events.append, progress=False)
Counter(getattr(event, "name", None) or event.kind for event in events)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## The verifying ensemble — `sf.CorrectiveEnsemble`

The corrective method above put the retry loop in the BENCHMARK. The philosophically
clean home for it is the CANDIDATE — and that is exactly the system of
[Skurikhin et al. (Los Alamos National Laboratory)](https://openreview.net/forum?id=XSIYfTm2h7):
small-model members answer in parallel, the benchmark's own checker grades every
draft mid-flight, violations feed each member's retry (3 bounded attempts), and a
judge model tie-breaks among passers — with deterministic engine actions returning
the winner verbatim, so the judge cannot mutate it.

Because the loop lives inside the candidate, it runs against the frozen
**`single_pass`** exam — the ensemble and a solo model land in the SAME comparable
column.

> **Cost note:** per case the ensemble spends up to 3 members × 3 attempts + 3 judge
> calls = 12 model calls (checking is free). `limit=2` below ≈ 24 small-model calls
> plus 2 solo-model calls.

Data flow (the exam is identical for both rows; only the candidate differs):

```text
exam, per case:  /candidate(input, case) ──▶ ONE final answer ──▶ /check ▶ record
/aggregate: plain single-pass score — paper-comparable

row 1  haiku:     prompt ──▶ haiku ──▶ answer                     (1 call/case)

row 2  ensemble — everything below happens INSIDE the /candidate slot:
  attempt (×3):   kimi ─┐
                  deepseek ─┼─▶ each draft ──▶ /check ▶ feedback (violations text)
                  qwen ─┘
                  judge reads drafts + verdicts ──▶ letter ──▶ /select (verbatim)
  /finalize: earliest PASSED selection ──▶ the ONE answer the exam sees
                                                                 (12 calls/case)
```"""
        ),
        nbformat.v4.new_code_cell(
            """kimi = sf.Model("openrouter/moonshotai/kimi-k2.6")
deepseek = sf.Model("openrouter/deepseek/deepseek-v4-pro")
qwen = sf.Model("openrouter/qwen/qwen3.6-plus")
flash = sf.Model("openrouter/google/gemini-3-flash-preview")

ensemble = sf.CorrectiveEnsemble([kimi, deepseek, qwen], judge=flash)
ensemble"""
        ),
        nbformat.v4.new_code_cell(
            """duel = sf.evaluate(
    [haiku, ensemble],
    benchmark="ifeval",
    limit=2,
    method="single_pass",
)
duel"""
        ),
        nbformat.v4.new_markdown_cell(
            """**What to observe:** both rows are the same exam and the same protocol — a fair
fight. The ensemble's `score` is what verification-and-retry buys; its
`output_tokens` next to the solo model's is the token overhead it costs. That
accuracy-vs-tokenomics tradeoff is the paper's whole argument, reproduced in one
dict:"""
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
        nbformat.v4.new_markdown_cell("## Inspect the full Report"),
        nbformat.v4.new_code_cell("report.candidates"),
        nbformat.v4.new_code_cell("report.usage"),
        nbformat.v4.new_code_cell("report.to_json()"),
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
