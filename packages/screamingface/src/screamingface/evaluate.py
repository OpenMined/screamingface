"""Orchestrate one evaluation: ask every model → reduce → grade, over a benchmark.

INVARIANT (spec §2): every model answer flows through the `EngineBackend` port —
this module never generates an answer itself, so swapping the simulated adapter
for the real engine (OME-296) cannot change the loop.
"""

from __future__ import annotations

from .datasets import Benchmark, load_benchmark
from .engine import EngineBackend, SimulatedBackend
from .fusion_core import FusionCore
from .reduce import reduce_answers
from .results import ModelResult, QuestionResult, RunResult


def evaluate(
    fusion: FusionCore,
    benchmark: Benchmark | str,
    seed: int = 0,
    backend: EngineBackend | None = None,
    correlation: float = 0.35,
    n: int = 20,
) -> RunResult:
    """Run `fusion` against `benchmark` and return a `RunResult`.

    `benchmark` may be a loaded `Benchmark` or a benchmark key (then `n`
    questions are loaded). `seed` makes the whole run reproducible (spec I1).
    `correlation` (used only when no `backend` is injected) controls how
    independent the models' errors are — the lever behind fusion lift.
    """
    if not fusion.slots:
        raise ValueError("Cannot evaluate an empty fusion — add at least one model.")
    if isinstance(benchmark, str):
        benchmark = load_benchmark(benchmark, n=n, seed=seed)
    if backend is None:
        backend = SimulatedBackend(correlation=correlation)

    spec = benchmark.spec
    slots = fusion.slots
    weights = fusion.normalized_weights()
    tallies = [{"correct": 0, "latency": 0.0, "cost": 0.0} for _ in slots]

    q_results = []
    for question in benchmark.questions:
        answers = [backend.answer(s.model, question, spec, seed) for s in slots]
        final_choice, note = reduce_answers(fusion, answers, weights)
        final_text = next((a.text for a in answers if a.choice == final_choice), final_choice)

        for t, ans in zip(tallies, answers):
            t["correct"] += int(ans.correct)
            t["latency"] += ans.latency_ms
            t["cost"] += ans.cost

        q_results.append(
            QuestionResult(
                question=question,
                model_answers=answers,
                final_choice=final_choice,
                final_text=final_text,
                correct=final_choice == question.gold_key,
                note=note,
                reasoning=backend.synth_reasoning(seed, question),
            )
        )

    n_q = len(benchmark.questions)
    model_results = [
        ModelResult(
            model_id=s.model.id,
            model_label=s.model.label,
            color=s.model.color,
            n=n_q,
            n_correct=int(t["correct"]),
            mean_latency_ms=(t["latency"] / n_q if n_q else 0.0),
            total_cost=t["cost"],
        )
        for s, t in zip(slots, tallies)
    ]

    return RunResult(
        fusion_name=fusion.name,
        model_ids=[s.model.id for s in slots],
        model_labels=[s.model.label for s in slots],
        reduce_label=fusion.reduce_strategy,
        loop_label=fusion.loop_mode,
        judge_id=fusion.judge_model_id,
        benchmark_id=spec.id,
        benchmark_name=spec.name,
        seed=seed,
        sample_size=n_q,
        source=benchmark.source,
        question_results=q_results,
        model_results=model_results,
    )
