"""Complete validation, compilation, execution, and decoding for one Evaluation."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Protocol

from screamingface._core.ports import AsyncRunTransport, SyncRunTransport, _RunOutcome
from screamingface._evaluation.benchmark import _BenchmarkResource
from screamingface._evaluation.model import (
    Candidate,
    _candidate_values,
    _Evaluation,
    _validate_limit,
)
from screamingface._evaluation.model_parameters import preflight_async, preflight_sync
from screamingface.discovery import ModelDetails, ModelInfo
from screamingface.events import Event
from screamingface.recipe import Recipe
from screamingface.report import Report


class _ModelCatalog(Protocol):
    @property
    def models(self) -> Sequence[ModelInfo]: ...


type _SyncModelLoading = Callable[[], _ModelCatalog]
type _AsyncModelLoading = Callable[[], Awaitable[_ModelCatalog]]
type _SyncModelDetailsLoading = Callable[[str], ModelDetails]
type _AsyncModelDetailsLoading = Callable[[str], Awaitable[ModelDetails]]
type _SyncBenchmarkLoading = Callable[[str, int | None], _BenchmarkResource]
type _AsyncBenchmarkLoading = Callable[[str, int | None], Awaitable[_BenchmarkResource]]

_MAX_CANDIDATES_IN_FLIGHT = 8


def evaluate_sync(
    load_benchmark: _SyncBenchmarkLoading,
    transport: SyncRunTransport,
    load_models: _SyncModelLoading,
    load_model_details: _SyncModelDetailsLoading,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str,
    limit: int | None,
    on_event: Callable[[Event], None] | None,
    progress: bool | None,
) -> Report:
    """Run the complete synchronous Evaluation workflow behind the Client interface."""

    from screamingface._evaluation.compilation import compile_evaluation
    from screamingface._evaluation.results import report_from_outcomes

    _evaluation_options(on_event, progress)
    values = _evaluation_inputs(candidates, benchmark, limit)
    resource = load_benchmark(benchmark, limit)
    catalog = load_models()
    evaluation = compile_evaluation(values, resource, limit)
    _validate_required_models(evaluation, catalog.models)
    preflight_sync(tuple(evaluation.candidates), load_model_details)
    observer = _sync_event_observer(on_event, progress)
    outcomes = _run_candidates_sync(transport, tuple(evaluation.candidates), observer)
    return report_from_outcomes(evaluation, outcomes)


async def evaluate_async(
    load_benchmark: _AsyncBenchmarkLoading,
    transport: AsyncRunTransport,
    load_models: _AsyncModelLoading,
    load_model_details: _AsyncModelDetailsLoading,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str,
    limit: int | None,
    on_event: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
) -> Report:
    """Run the complete asynchronous Evaluation workflow behind the Client interface."""

    from screamingface._evaluation.compilation import compile_evaluation
    from screamingface._evaluation.results import report_from_outcomes

    _evaluation_options(on_event, progress)
    values = _evaluation_inputs(candidates, benchmark, limit)
    resource = await load_benchmark(benchmark, limit)
    catalog = await load_models()
    evaluation = compile_evaluation(values, resource, limit)
    _validate_required_models(evaluation, catalog.models)
    await preflight_async(tuple(evaluation.candidates), load_model_details)
    observer = _async_event_observer(on_event, progress)
    outcomes = await _run_candidates_async(transport, tuple(evaluation.candidates), observer)
    return report_from_outcomes(evaluation, outcomes)


def _evaluation_options(on_event: object, progress: object) -> None:
    if on_event is not None and not callable(on_event):
        raise TypeError("on_event must be callable or None")
    if progress is not None and not isinstance(progress, bool):
        raise TypeError("progress must be True, False, or None")


def _sync_event_observer(
    callback: Callable[[Event], None] | None,
    progress: bool | None,
) -> Callable[[Event], None] | None:
    from screamingface._evaluation.progress import _progress_observer

    builtin = _progress_observer(progress)
    if builtin is None and callback is None:
        return None
    lock = Lock()

    def observe(event: Event) -> None:
        with lock:
            if builtin is not None:
                _observe_progress(builtin, event)
            if callback is not None:
                callback(event)

    return observe


def _async_event_observer(
    callback: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
) -> Callable[[Event], Awaitable[None]] | None:
    from screamingface._evaluation.progress import _progress_observer

    builtin = _progress_observer(progress)
    if builtin is None and callback is None:
        return None
    lock = asyncio.Lock()

    async def observe(event: Event) -> None:
        async with lock:
            if builtin is not None:
                _observe_progress(builtin, event)
            if callback is not None:
                returned = callback(event)
                if inspect.isawaitable(returned):
                    await returned

    return observe


def _observe_progress(observer: Callable[[Event], None], event: Event) -> None:
    """Keep decorative progress output outside the Evaluation failure boundary."""

    try:
        observer(event)
    except Exception:
        # Closed pipes and notebook streams must not cancel paid Engine work.
        pass


def _run_candidates_sync(
    transport: SyncRunTransport,
    candidates: tuple[Candidate, ...],
    observer: Callable[[Event], None] | None,
) -> tuple[tuple[Candidate, _RunOutcome], ...]:
    if len(candidates) == 1:
        candidate = candidates[0]
        return ((candidate, transport.run(candidate, observer)),)

    with ThreadPoolExecutor(
        max_workers=min(len(candidates), _MAX_CANDIDATES_IN_FLIGHT),
        thread_name_prefix="screamingface-candidate",
    ) as executor:
        futures = ()
        try:
            futures = tuple(
                executor.submit(transport.run, candidate, observer) for candidate in candidates
            )
            return tuple(
                (candidate, future.result())
                for candidate, future in zip(candidates, futures, strict=True)
            )
        except BaseException as exc:
            try:
                transport.cancel_active()
            except Exception as cancel_error:  # noqa: BLE001 - preserve the original interruption
                exc.add_note(f"Stopping active SF Engine runs also failed: {cancel_error}")
            for future in futures:
                future.cancel()
            raise


async def _run_candidates_async(
    transport: AsyncRunTransport,
    candidates: tuple[Candidate, ...],
    observer: Callable[[Event], None | Awaitable[None]] | None,
) -> tuple[tuple[Candidate, _RunOutcome], ...]:
    if len(candidates) == 1:
        candidate = candidates[0]
        return ((candidate, await transport.run(candidate, observer)),)

    gate = asyncio.Semaphore(_MAX_CANDIDATES_IN_FLIGHT)

    async def run(candidate: Candidate) -> _RunOutcome:
        async with gate:
            return await transport.run(candidate, observer)

    tasks = tuple(asyncio.create_task(run(candidate)) for candidate in candidates)
    try:
        outcomes = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return tuple(zip(candidates, outcomes, strict=True))


def _validate_required_models(
    evaluation: _Evaluation,
    available: Sequence[ModelInfo],
) -> None:
    from screamingface.errors import PlanningError

    available_ids = {model.id for model in available}
    missing = tuple(model for model in evaluation.required_models if model not in available_ids)
    if not missing:
        return
    if len(missing) == 1:
        message = f"Model {missing[0]!r} is not available on this Engine"
    else:
        names = ", ".join(repr(model) for model in missing)
        message = f"Models {names} are not available on this Engine"
    raise PlanningError(
        message,
        code="model_unavailable",
        permanent=True,
        details={"models": list(missing)},
    )


def _evaluation_inputs(
    candidates: Recipe | Sequence[Recipe],
    benchmark: str,
    limit: int | None,
) -> tuple[Recipe, ...]:
    values = _candidate_values(candidates)
    if not isinstance(benchmark, str) or not benchmark.strip():
        raise ValueError("benchmark must be a non-empty string")
    if benchmark == "default":
        raise ValueError("benchmark must name an explicit Benchmark, not 'default'")
    _validate_limit(limit)
    return values


__all__: list[str] = []
