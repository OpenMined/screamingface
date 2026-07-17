"""URL4-engine-only panel evaluation and local deterministic scoring."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from html import escape

from screamingface.data import Question, load_live_questions, load_mock_questions
from screamingface.engine import (
    EnginePort,
    Url4EngineClient,
    parse_fusion_result,
    parse_panel_result,
)
from screamingface.reducers import MajorityVote, Synthesize
from screamingface.results import ModelResult, Run, RunFailure
from screamingface.session import Session, _in_notebook

_ANSWER = re.compile(r"\b([A-D])\b", re.IGNORECASE)
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class QuestionPanel:
    answers: dict[str, str]
    fusion_answer: str | None = None


@dataclass
class RunAccumulator:
    model_ids: tuple[str, ...]
    fusion_correct: int = 0
    incomplete: int = 0
    failures: list[RunFailure] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.member_correct = {model: 0 for model in self.model_ids}
        self.model_failures = {model: 0 for model in self.model_ids}

    def add(self, question: Question, fusion_answer: str, panel: QuestionPanel) -> None:
        expected = chr(65 + question.answer)
        self.fusion_correct += fusion_answer == expected
        self.incomplete += any(not panel.answers[model] for model in self.model_ids)
        for model in self.model_ids:
            answer = panel.answers[model]
            self.member_correct[model] += answer == expected
            if not answer:
                self.model_failures[model] += 1
                self.failures.append(
                    RunFailure(question.id, model, "invalid_answer", "Model did not return A-D")
                )


async def evaluate(
    *,
    session: Session,
    fusion,
    benchmark: str,
    first: int,
    seed: int,
    progress: ProgressCallback | None = None,
    preflight: bool = True,
) -> Run:
    """Evaluate via one URL4 engine request per benchmark question."""
    del preflight  # retained temporarily for call-site compatibility
    if benchmark != "gpqa":
        raise ValueError("the MVP supports only the 'gpqa' benchmark")
    questions = _load_questions(session, first, seed)
    engine = session.engine or Url4EngineClient(session.engine_url)
    totals = RunAccumulator(fusion.models)
    if progress is not None:
        progress(0, len(questions), "Loading GPQA sample")
    for index, question in enumerate(questions, 1):
        if progress is not None:
            progress(index - 1, len(questions), f"Question {index}/{len(questions)} · URL4 engine")
        panel = await _run_question(question, engine, fusion)
        final = _reduce_panel(panel, fusion)
        totals.add(question, final, panel)
        if progress is not None:
            progress(index, len(questions), f"Question {index}/{len(questions)} complete")
    result = _build_run(session, fusion, questions, totals, seed)
    if progress is not None:
        progress(len(questions), len(questions), "Complete")
    return result


def _reduce_panel(panel: QuestionPanel, fusion) -> str:
    if panel.fusion_answer is not None:
        return normalize_answer(panel.fusion_answer)
    if not isinstance(fusion.reducer, MajorityVote):  # pragma: no cover - closed by Fusion
        raise TypeError(f"unsupported local reducer: {type(fusion.reducer).__name__}")
    return majority_vote(
        tuple(panel.answers[model] for model in fusion.models),
        fusion.models,
        fusion.reducer.tie_breaker,
    )


def _load_questions(session: Session, first: int, seed: int) -> tuple[Question, ...]:
    if session.mode == "mock":
        return load_mock_questions(first)
    return load_live_questions(first, seed)


async def _run_question(question: Question, engine: EnginePort, fusion) -> QuestionPanel:
    expression = fusion.request_for(question.prompt())
    body = await engine.evaluate(expression)
    if isinstance(fusion.reducer, MajorityVote):
        result = parse_panel_result(body, fusion.models)
        fusion_answer = None
    elif isinstance(fusion.reducer, Synthesize):
        result = parse_fusion_result(body, fusion.models, fusion.reducer.model)
        fusion_answer = result.answer
    else:  # pragma: no cover - Fusion validates the closed reducer union
        raise TypeError(f"unsupported reducer: {type(fusion.reducer).__name__}")
    return QuestionPanel(
        {
            model: normalize_answer(answer)
            for model, answer in zip(fusion.models, result.answers, strict=True)
        },
        fusion_answer=fusion_answer,
    )


def majority_vote(
    answers: Sequence[str],
    model_ids: Sequence[str],
    tie_breaker: str | None,
) -> str:
    normalized = tuple(normalize_answer(answer) for answer in answers)
    counts = Counter(answer for answer in normalized if answer)
    result = ""
    if counts:
        top = max(counts.values())
        winners = {answer for answer, count in counts.items() if count == top}
        result = next(iter(winners)) if len(winners) == 1 else sorted(winners)[0]
        if len(winners) > 1 and tie_breaker is not None:
            tied_answer = normalized[tuple(model_ids).index(tie_breaker)]
            if tied_answer:
                result = tied_answer
    return result


def _majority_processor(model_ids: tuple[str, ...], judge: str | None):
    """Compatibility wrapper; reducers no longer execute inside an SDK node."""

    async def process(sources: str, intent: str | None, _scope) -> str:
        if intent != "majority_vote":
            raise ValueError(f"unsupported reducer intent: {intent}")
        return majority_vote(sources.split("\n"), model_ids, judge)

    return process


def normalize_answer(text: str) -> str:
    match = _ANSWER.search(text.strip())
    return match.group(1).upper() if match else ""


def _build_run(
    session: Session,
    fusion,
    questions: tuple[Question, ...],
    totals: RunAccumulator,
    seed: int,
) -> Run:
    sample_size = len(questions)
    scores = [100 * count / sample_size for count in totals.member_correct.values()]
    score = round(100 * totals.fusion_correct / sample_size, 1)
    baseline = round(max(scores), 1)
    model_results = tuple(
        ModelResult(
            model=model,
            score=round(100 * totals.member_correct[model] / sample_size, 1),
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            failures=totals.model_failures[model],
        )
        for model in fusion.models
    )
    return Run(
        benchmark=(
            "GPQA-shaped synthetic science fixture" if session.mode == "mock" else "GPQA Diamond"
        ),
        dataset_source=session.dataset_source,
        mode=session.mode,
        models=fusion.models,
        url=fusion.url4,
        sample_size=sample_size,
        seed=seed,
        score=score,
        baseline=baseline,
        gain=round(score - baseline, 1),
        cost_usd=0.0,
        fusion_name=fusion.name,
        reducer=fusion.reducer.name,
        tie_breaker=(
            fusion.reducer.tie_breaker if isinstance(fusion.reducer, MajorityVote) else None
        ),
        incomplete=totals.incomplete,
        pricing_source="engine response does not yet report usage",
        pricing_as_of="n/a",
        model_results=model_results,
        failures=tuple(totals.failures),
    )


def evaluate_sync(*, show_progress: bool | None = None, **kwargs) -> Run:
    from screamingface.session import _run

    session: Session = kwargs["session"]
    total_requests = kwargs["first"]
    reporter = _progress_reporter(show_progress, total_requests, session.static_widgets)
    try:
        return _run(evaluate(**kwargs, progress=reporter))
    except BaseException:
        if reporter is not None:
            reporter(0, total_requests, "Stopped with an error")
        raise


def _progress_reporter(
    show_progress: bool | None, total: int, static_widgets: bool
) -> ProgressCallback | None:
    enabled = _in_notebook() and not static_widgets if show_progress is None else show_progress
    if not enabled:
        return None
    try:
        return _NotebookProgress(total).update
    except ImportError:
        return _text_progress


class _NotebookProgress:
    def __init__(self, total: int) -> None:
        import ipywidgets as widgets
        from IPython.display import display

        self._bar = widgets.IntProgress(value=0, min=0, max=total, description="Questions")
        self._status = widgets.HTML()
        display(widgets.VBox((self._bar, self._status)))

    def update(self, completed: int, total: int, message: str) -> None:
        self._bar.max = total
        self._bar.value = completed
        self._status.value = (
            f"<strong>{completed}/{total}</strong> · {escape(message)}"
            "<br><span style='color:#70757a'>Each question is one URL4 engine request.</span>"
        )


def _text_progress(completed: int, total: int, message: str) -> None:
    ending = "\n" if completed == total and message == "Complete" else "\r"
    print(f"GPQA {completed}/{total} · {message}", end=ending, flush=True)
