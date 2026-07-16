"""URL4-backed panel evaluation and majority-vote scoring."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from typing import Protocol
from urllib.parse import unquote, urlsplit

from url4 import Url4Node

from screamingface.data import Question, load_live_questions, load_mock_questions
from screamingface.errors import FusionNotReady, ProviderCallError
from screamingface.gateway import GatewayPort
from screamingface.models import models
from screamingface.results import ModelResult, Run, RunFailure
from screamingface.session import Session, _in_notebook

_ANSWER = re.compile(r"\b([A-D])\b", re.IGNORECASE)
ProgressCallback = Callable[[int, int, str], None]


class CompletionPort(Protocol):
    async def answer(self, model: str, question: Question, *, seed: int) -> ModelAnswer: ...


@dataclass(frozen=True)
class ModelAnswer:
    text: str
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class MockCompletionAdapter:
    async def answer(self, model: str, question: Question, *, seed: int) -> ModelAnswer:
        meta = models.get(model)
        index = int(question.id.rsplit("-", 1)[-1]) - 1
        # Three complementary four-question error buckets produce a meaningful positive
        # majority-vote gain without pretending these are real provider capabilities.
        start = meta.mock_error_bucket * 4
        wrong = (index - seed) % 20 in range(start, start + 4)
        choice = (question.answer + 1) % len(question.options) if wrong else question.answer
        return ModelAnswer(chr(65 + choice))


@dataclass
class GatewayCompletionAdapter:
    client: GatewayPort
    profiles: dict[str, str]

    async def answer(self, model: str, question: Question, *, seed: int) -> ModelAnswer:
        del seed
        provider = model.split("/", 1)[0]
        price = models.get(model).price_per_million or 0.0
        prompt = question.prompt()
        max_tokens = 8
        completion = await self.client.complete(
            model=model,
            profile=self.profiles.get(provider, "default"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        actual = price * completion.total_tokens / 1_000_000
        return ModelAnswer(
            completion.text,
            actual,
            completion.prompt_tokens,
            completion.completion_tokens,
            completion.total_tokens,
        )


@dataclass
class QuestionIOLayer:
    question: Question
    adapter: CompletionPort
    seed: int
    answers: dict[str, str] = field(default_factory=dict)
    usage: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    model_costs: dict[str, float] = field(default_factory=dict)
    failures: list[RunFailure] = field(default_factory=list)
    cost_usd: float = 0.0
    on_call_complete: Callable[[str], None] | None = None

    async def fetch(self, target: str, *, relative: bool) -> str:
        if relative:
            raise ValueError(f"unexpected relative URL4 request: {target}")
        parsed = urlsplit(target)
        if parsed.scheme != "sf-model":
            raise ValueError(f"unsupported URL4 source: {target}")
        model = unquote(f"{parsed.netloc}{parsed.path}")
        try:
            answer = await self.adapter.answer(model, self.question, seed=self.seed)
        except ProviderCallError as exc:
            self.answers[model] = ""
            self.failures.append(RunFailure(self.question.id, model, exc.code, str(exc)))
            return ""
        finally:
            if self.on_call_complete is not None:
                self.on_call_complete(model)
        normalized = normalize_answer(answer.text)
        self.answers[model] = normalized
        self.usage[model] = (
            answer.prompt_tokens,
            answer.completion_tokens,
            answer.total_tokens,
        )
        self.model_costs[model] = answer.cost_usd
        self.cost_usd += answer.cost_usd
        if not normalized:
            self.failures.append(
                RunFailure(self.question.id, model, "invalid_answer", "Model did not return A-D")
            )
        return normalized


@dataclass
class RunAccumulator:
    models: tuple[str, ...]
    fusion_correct: int = 0
    incomplete: int = 0
    cost_usd: float = 0.0
    failures: list[RunFailure] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.member_correct = {model: 0 for model in self.models}
        self.usage = {model: [0, 0, 0] for model in self.models}
        self.model_costs = {model: 0.0 for model in self.models}
        self.model_failures = {model: 0 for model in self.models}

    def add(self, question: Question, final: str, io: QuestionIOLayer) -> None:
        expected = chr(65 + question.answer)
        self.fusion_correct += final == expected
        self.incomplete += any(not io.answers.get(model) for model in self.models)
        self.cost_usd += io.cost_usd
        self.failures.extend(io.failures)
        for model in self.models:
            self.member_correct[model] += io.answers.get(model, "") == expected
            for index, value in enumerate(io.usage.get(model, (0, 0, 0))):
                self.usage[model][index] += value
            self.model_costs[model] += io.model_costs.get(model, 0.0)
            self.model_failures[model] += sum(failure.model == model for failure in io.failures)


@dataclass
class _EvaluationProgress:
    callback: ProgressCallback | None
    total_questions: int
    model_count: int
    completed_calls: int = 0

    @property
    def total_calls(self) -> int:
        return self.total_questions * self.model_count

    def report(self, message: str) -> None:
        if self.callback is not None:
            self.callback(self.completed_calls, self.total_calls, message)

    def call_finished(self, question_index: int, model: str) -> None:
        self.completed_calls += 1
        self.report(f"Question {question_index}/{self.total_questions} · {model} finished")


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
    """Evaluate a fusion on a benchmark sample and return an immutable Run.

    Rounding policy: ``score`` and ``baseline`` are accuracy percentages rounded to
    one decimal place, and ``gain`` is their difference rounded the same way.
    """
    if benchmark != "gpqa":
        raise ValueError("OME-400 supports only the 'gpqa' benchmark")
    if preflight:
        await _preflight(session, fusion)
    tracker = _EvaluationProgress(progress, first, len(fusion.models))
    tracker.report("Loading GPQA sample")
    questions, adapter = _prepare_run(session, first, seed)
    totals = RunAccumulator(fusion.models)
    for index, question in enumerate(questions, start=1):
        tracker.report(f"Question {index}/{len(questions)} · querying {len(fusion.models)} models")
        final, io = await _run_question(
            question,
            adapter,
            fusion,
            seed,
            on_call_complete=lambda model, index=index: tracker.call_finished(index, model),
        )
        totals.add(question, final, io)
        tracker.report(f"Question {index}/{len(questions)} complete")
    scores = [100 * count / len(questions) for count in totals.member_correct.values()]
    score = round(100 * totals.fusion_correct / len(questions), 1)
    baseline = round(max(scores), 1)
    model_results = tuple(
        ModelResult(
            model=model,
            score=round(100 * totals.member_correct[model] / len(questions), 1),
            prompt_tokens=totals.usage[model][0],
            completion_tokens=totals.usage[model][1],
            total_tokens=totals.usage[model][2],
            cost_usd=round(totals.model_costs[model], 8),
            failures=totals.model_failures[model],
        )
        for model in fusion.models
    )
    result = Run(
        benchmark=(
            "GPQA-shaped synthetic science fixture" if session.mode == "mock" else "GPQA Diamond"
        ),
        dataset_source=session.dataset_source,
        mode=session.mode,
        models=fusion.models,
        url=fusion.url,
        sample_size=len(questions),
        seed=seed,
        score=score,
        baseline=baseline,
        gain=round(score - baseline, 1),
        cost_usd=round(totals.cost_usd, 8),
        fusion_name=fusion.name,
        reduce=fusion.reduce,
        judge=fusion.judge,
        incomplete=totals.incomplete,
        profiles=tuple(sorted(session.profiles.items())),
        # WHY: provenance comes from the catalog entries actually priced into this
        # run, so a future per-model pricing update is reflected without edits here.
        pricing_source=" + ".join(
            sorted({models.get(model).pricing_source for model in fusion.models})
        ),
        pricing_as_of=max(models.get(model).pricing_as_of for model in fusion.models).isoformat(),
        prompt_tokens=sum(values[0] for values in totals.usage.values()),
        completion_tokens=sum(values[1] for values in totals.usage.values()),
        total_tokens=sum(values[2] for values in totals.usage.values()),
        model_results=model_results,
        failures=tuple(totals.failures),
    )
    tracker.report("Complete")
    return result


async def _preflight(session: Session, fusion) -> None:
    if session.mode == "mock":
        return
    gateway = session._live_gateway()
    await session._refresh_profiles_async()
    gateway_models = set(await gateway.list_models())
    connected = session.connected_providers or frozenset()
    required: dict[str, list[str]] = {}
    for model in fusion.models:
        required.setdefault(model.split("/", 1)[0], []).append(model)
    missing = {
        provider: tuple(models)
        for provider, models in required.items()
        if provider not in connected
    }
    unavailable = tuple(model for model in fusion.models if model not in gateway_models)
    if missing or unavailable:
        raise FusionNotReady(missing, unavailable)


def _prepare_run(
    session: Session, first: int, seed: int
) -> tuple[tuple[Question, ...], CompletionPort]:
    if session.mode == "mock":
        return load_mock_questions(first), MockCompletionAdapter()
    if session.gateway is None:
        raise RuntimeError("Live setup requires an AI Gateway session")
    adapter = GatewayCompletionAdapter(session.gateway, session.profiles)
    return load_live_questions(first, seed), adapter


async def _run_question(
    question: Question,
    adapter: CompletionPort,
    fusion,
    seed: int,
    *,
    on_call_complete: Callable[[str], None] | None = None,
):
    io = QuestionIOLayer(question, adapter, seed, on_call_complete=on_call_complete)
    node = Url4Node(
        "screamingface",
        outbound=io,
        process_fn=_majority_processor(fusion.models, fusion.judge),
    )
    result = await node.evaluate(fusion.expression)
    return result.text, io


def _majority_processor(model_ids: tuple[str, ...], judge: str | None):
    async def process(sources: str, intent: str | None, _scope) -> str:
        if intent != "majority_vote":
            raise ValueError(f"unsupported reducer intent: {intent}")
        raw_answers = sources.split("\n")
        answers = [normalize_answer(value) for value in raw_answers]
        answers = (answers + [""] * len(model_ids))[: len(model_ids)]
        counts = Counter(answer for answer in answers if answer)
        result = ""
        if counts:
            top = max(counts.values())
            winners = {answer for answer, count in counts.items() if count == top}
            result = next(iter(winners)) if len(winners) == 1 else sorted(winners)[0]
            if len(winners) > 1 and judge is not None:
                # WHY: spec §7 — a tied vote selects the judge's existing answer
                # outright; the alphabetical fallback above applies only without a
                # judge or when the judge produced no valid answer.
                judge_answer = answers[model_ids.index(judge)]
                if judge_answer:
                    result = judge_answer
        return result

    return process


def normalize_answer(text: str) -> str:
    match = _ANSWER.search(text.strip())
    return match.group(1).upper() if match else ""


def evaluate_sync(*, show_progress: bool | None = None, **kwargs) -> Run:
    from screamingface.session import _run

    session: Session = kwargs["session"]
    if session.mode == "live":
        _run(_preflight(session, kwargs["fusion"]))
    total_calls = kwargs["first"] * len(kwargs["fusion"].models)
    reporter = _progress_reporter(show_progress, total_calls, session.static_widgets)
    try:
        return _run(evaluate(**kwargs, progress=reporter, preflight=False))
    except BaseException:
        if reporter is not None:
            reporter(0, total_calls, "Stopped with an error")
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

        self._bar = widgets.IntProgress(value=0, min=0, max=total, description="Calls")
        self._status = widgets.HTML()
        display(widgets.VBox((self._bar, self._status)))

    def update(self, completed: int, total: int, message: str) -> None:
        self._bar.max = total
        self._bar.value = completed
        self._status.value = (
            f"<strong>{completed}/{total}</strong> · {escape(message)}"
            "<br><span style='color:#70757a'>Each question queries the panel concurrently; "
            "provider requests time out after 30 seconds.</span>"
        )


def _text_progress(completed: int, total: int, message: str) -> None:
    ending = "\n" if completed == total and message == "Complete" else "\r"
    print(f"GPQA {completed}/{total} · {message}", end=ending, flush=True)
