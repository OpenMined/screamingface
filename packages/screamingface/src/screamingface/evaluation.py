"""URL4-engine-only panel evaluation and local deterministic scoring."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from html import escape

from screamingface.benchmarks import _EvaluationCase, _LoadedBenchmark, _resolve_benchmark
from screamingface.engine import (
    EnginePort,
    Url4EngineClient,
    parse_fusion_result,
    parse_panel_result,
)
from screamingface.graders import _ExactChoiceGrader, _Grade, _Grader
from screamingface.model_inputs import _FusionMember
from screamingface.reducers import LocalReducer, MajorityVote, ModelReducer
from screamingface.results import ModelResult, Run, RunFailure
from screamingface.session import Session, _in_notebook

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class QuestionPanel:
    answers: dict[str, str]
    fusion_answer: str | None = None


@dataclass
class RunAccumulator:
    members: tuple[_FusionMember, ...]
    fusion_score: float = 0.0
    incomplete: int = 0
    failures: list[RunFailure] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.member_scores = {member.id: 0.0 for member in self.members}
        self.fusion_metrics: dict[str, float] = {}
        self.member_metrics: dict[str, dict[str, float]] = {
            member.id: {} for member in self.members
        }
        self.model_failures = {member.id: 0 for member in self.members}

    def add(
        self,
        case: _EvaluationCase,
        fusion_grade: _Grade,
        member_grades: dict[str, _Grade],
    ) -> None:
        self.fusion_score += fusion_grade.score
        _accumulate_metrics(self.fusion_metrics, fusion_grade.metrics)
        self.incomplete += any(not member_grades[member.id].valid for member in self.members)
        for member in self.members:
            grade = member_grades[member.id]
            self.member_scores[member.id] += grade.score
            _accumulate_metrics(self.member_metrics[member.id], grade.metrics)
            if not grade.valid:
                self.model_failures[member.id] += 1
                self.failures.append(
                    RunFailure(
                        case.id,
                        member.model,
                        grade.failure_code or "invalid_answer",
                        grade.failure_message or "Model returned an invalid answer",
                        name=member.id if member.id != member.model else None,
                    )
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
    """Evaluate via URL4, including benchmark-owned grader calls when required."""
    del preflight  # retained temporarily for call-site compatibility
    definition = _resolve_benchmark(benchmark)
    _validate_required_tools(definition, fusion)
    loaded = definition.load(session, first, seed)
    cases = loaded.cases
    grader = definition.grader
    engine = session.engine or Url4EngineClient(session.engine_url)
    totals = RunAccumulator(fusion._members)
    if progress is not None:
        progress(0, len(cases), f"Loading {definition.id.upper()} sample")
    for index, case in enumerate(cases, 1):
        if progress is not None:
            progress(index - 1, len(cases), f"Question {index}/{len(cases)} · URL4 engine")
        panel = await _run_question(case, engine, fusion, grader)
        final = _reduce_panel(panel, fusion)
        fusion_grade, member_grades = await _grade_question(
            case,
            final,
            panel,
            fusion._members,
            grader,
            engine,
        )
        totals.add(case, fusion_grade, member_grades)
        if progress is not None:
            progress(index, len(cases), f"Question {index}/{len(cases)} complete")
    result = _build_run(session, fusion, loaded, totals, seed)
    if progress is not None:
        progress(len(cases), len(cases), "Complete")
    return result


def _validate_required_tools(definition, fusion) -> None:
    missing = tuple(tool for tool in definition.required_tools if tool not in fusion.tools)
    if missing:
        names = ", ".join(missing)
        raise ValueError(
            f"{definition.name} requires these fusion tools: {names}; "
            f"add tools={list(missing)!r} to sf.Fusion(...)"
        )


def _reduce_panel(panel: QuestionPanel, fusion) -> str:
    if panel.fusion_answer is not None:
        return panel.fusion_answer
    if not isinstance(fusion.reducer, LocalReducer):  # pragma: no cover - closed by Fusion
        raise TypeError(f"unsupported local reducer: {type(fusion.reducer).__name__}")
    answers = tuple(panel.answers[member.id] for member in fusion._members)
    return fusion.reducer.reduce(
        answers,
        tuple(member.id for member in fusion._members),
    )


async def _run_question(
    case: _EvaluationCase,
    engine: EnginePort,
    fusion,
    grader: _Grader,
) -> QuestionPanel:
    expression = fusion.request_for(case.prompt)
    body = await engine.evaluate(expression)
    if isinstance(fusion.reducer, LocalReducer):
        result = parse_panel_result(body, fusion._members)
        fusion_answer = None
    elif isinstance(fusion.reducer, ModelReducer):
        result = parse_fusion_result(body, fusion._members, fusion.reducer.model)
        fusion_answer = result.answer
    else:  # pragma: no cover - Fusion validates the closed reducer union
        raise TypeError(f"unsupported reducer: {type(fusion.reducer).__name__}")
    return QuestionPanel(
        {
            member.id: grader.parse_answer(answer)
            for member, answer in zip(fusion._members, result.answers, strict=True)
        },
        fusion_answer=(grader.parse_answer(fusion_answer) if fusion_answer is not None else None),
    )


async def _grade_question(
    case: _EvaluationCase,
    fusion_answer: str,
    panel: QuestionPanel,
    members: tuple[_FusionMember, ...],
    grader: _Grader,
    engine: EnginePort,
) -> tuple[_Grade, dict[str, _Grade]]:
    grades = await grader.grade_many(
        case,
        (fusion_answer, *(panel.answers[member.id] for member in members)),
        engine=engine,
    )
    return grades[0], {member.id: grade for member, grade in zip(members, grades[1:], strict=True)}


def majority_vote(
    answers: Sequence[str],
    model_ids: Sequence[str],
    tie_breaker: str | None,
) -> str:
    normalized = tuple(normalize_answer(answer) for answer in answers)
    return MajorityVote(tie_breaker=tie_breaker).reduce(normalized, model_ids)


def _majority_processor(model_ids: tuple[str, ...], judge: str | None):
    """Compatibility wrapper; reducers no longer execute inside an SDK node."""

    async def process(sources: str, intent: str | None, _scope) -> str:
        if intent != "majority_vote":
            raise ValueError(f"unsupported reducer intent: {intent}")
        return majority_vote(sources.split("\n"), model_ids, judge)

    return process


def normalize_answer(text: str) -> str:
    """Compatibility helper for the MVP's exact-choice answer protocol."""

    return _ExactChoiceGrader().parse_answer(text)


def _accumulate_metrics(totals: dict[str, float], metrics: tuple[tuple[str, float], ...]) -> None:
    for name, value in metrics:
        totals[name] = totals.get(name, 0.0) + value


def _build_run(
    session: Session,
    fusion,
    loaded: _LoadedBenchmark,
    totals: RunAccumulator,
    seed: int,
) -> Run:
    sample_size = len(loaded.cases)
    scores = [100 * score / sample_size for score in totals.member_scores.values()]
    score = round(100 * totals.fusion_score / sample_size, 1)
    baseline = round(max(scores), 1)
    model_results = tuple(
        ModelResult(
            model=member.model,
            score=round(100 * totals.member_scores[member.id] / sample_size, 1),
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            failures=totals.model_failures[member.id],
            name=member.id if member.id != member.model else None,
            metrics=_mean_metrics(totals.member_metrics[member.id], sample_size),
        )
        for member in fusion._members
    )
    return Run(
        benchmark=loaded.display_name,
        dataset_source=loaded.dataset_source,
        mode=session.mode,
        models=fusion.model_ids,
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
        primary_metric=loaded.definition.primary_metric,
        metrics=_mean_metrics(totals.fusion_metrics, sample_size),
    )


def _mean_metrics(totals: dict[str, float], sample_size: int) -> tuple[tuple[str, float], ...]:
    return tuple(
        (name, round(100 * value / sample_size, 1)) for name, value in sorted(totals.items())
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
            "<br><span style='color:#70757a'>Fusion and grader work run through URL4.</span>"
        )


def _text_progress(completed: int, total: int, message: str) -> None:
    ending = "\n" if completed == total and message == "Complete" else "\r"
    print(f"GPQA {completed}/{total} · {message}", end=ending, flush=True)
