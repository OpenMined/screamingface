"""Complete validation, compilation, execution, and decoding for one Evaluation."""

from __future__ import annotations

import asyncio
import inspect
import logging
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
_logger = logging.getLogger(__name__)


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
    check_disclosure = _validate_check_surface(values, benchmark, resource)
    evaluation = compile_evaluation(values, resource, limit)
    catalog = load_models()
    _validate_required_models(evaluation, catalog.models)
    preflight_sync(tuple(evaluation.candidates), load_model_details)
    observer = _sync_event_observer(
        on_event,
        progress,
        len(evaluation.candidates),
        benchmark,
        case_count=evaluation.case_count,
        candidate_models=_candidate_model_ids(tuple(evaluation.candidates)),
        candidate_urls=tuple(candidate.url4 for candidate in evaluation.candidates),
        candidate_names=tuple(candidate.name for candidate in evaluation.candidates),
        check_disclosure=check_disclosure,
    )
    try:
        outcomes = _run_candidates_sync(transport, tuple(evaluation.candidates), observer)
    except BaseException:
        _close_event_observer(observer)
        raise
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
    check_disclosure = _validate_check_surface(values, benchmark, resource)
    evaluation = compile_evaluation(values, resource, limit)
    catalog = await load_models()
    _validate_required_models(evaluation, catalog.models)
    await preflight_async(tuple(evaluation.candidates), load_model_details)
    observer = _async_event_observer(
        on_event,
        progress,
        len(evaluation.candidates),
        benchmark,
        case_count=evaluation.case_count,
        candidate_models=_candidate_model_ids(tuple(evaluation.candidates)),
        candidate_urls=tuple(candidate.url4 for candidate in evaluation.candidates),
        candidate_names=tuple(candidate.name for candidate in evaluation.candidates),
        check_disclosure=check_disclosure,
    )
    try:
        outcomes = await _run_candidates_async(transport, tuple(evaluation.candidates), observer)
    except BaseException:
        _close_event_observer(observer)
        raise
    return report_from_outcomes(evaluation, outcomes)


def _evaluation_options(on_event: object, progress: object) -> None:
    if on_event is not None and not callable(on_event):
        raise TypeError("on_event must be callable or None")
    if progress is not None and not isinstance(progress, bool):
        raise TypeError("progress must be True, False, or None")


def _sync_event_observer(
    callback: Callable[[Event], None] | None,
    progress: bool | None,
    total_candidates: int | None = None,
    benchmark: str | None = None,
    case_count: int | None = None,
    candidate_models: tuple[str, ...] = (),
    candidate_urls: tuple[str, ...] = (),
    candidate_names: tuple[str, ...] = (),
    check_disclosure: str | None = None,
) -> Callable[[Event], None] | None:
    from screamingface._evaluation.progress import _progress_observer

    builtin = _progress_observer(
        progress,
        total_candidates=total_candidates,
        benchmark=benchmark,
        case_count=case_count,
        candidate_models=candidate_models,
        candidate_urls=candidate_urls,
        candidate_names=candidate_names,
        check_disclosure=check_disclosure,
    )
    if builtin is None and callback is None:
        return None
    return _SyncEventObserver(builtin, callback)


def _async_event_observer(
    callback: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
    total_candidates: int | None = None,
    benchmark: str | None = None,
    case_count: int | None = None,
    candidate_models: tuple[str, ...] = (),
    candidate_urls: tuple[str, ...] = (),
    candidate_names: tuple[str, ...] = (),
    check_disclosure: str | None = None,
) -> Callable[[Event], Awaitable[None]] | None:
    from screamingface._evaluation.progress import _progress_observer

    builtin = _progress_observer(
        progress,
        total_candidates=total_candidates,
        benchmark=benchmark,
        case_count=case_count,
        candidate_models=candidate_models,
        candidate_urls=candidate_urls,
        candidate_names=candidate_names,
        check_disclosure=check_disclosure,
    )
    if builtin is None and callback is None:
        return None
    return _AsyncEventObserver(builtin, callback)


class _SyncEventObserver:
    def __init__(
        self,
        builtin: Callable[[Event], None] | None,
        callback: Callable[[Event], None] | None,
    ) -> None:
        self._builtin = builtin
        self._callback = callback
        self._lock = Lock()

    def __call__(self, event: Event) -> None:
        with self._lock:
            if self._builtin is not None:
                _observe_progress(self._builtin, event)
            if self._callback is not None:
                self._callback(event)

    def close(self) -> None:
        _close_progress(self._builtin)


class _AsyncEventObserver:
    def __init__(
        self,
        builtin: Callable[[Event], None] | None,
        callback: Callable[[Event], None | Awaitable[None]] | None,
    ) -> None:
        self._builtin = builtin
        self._callback = callback
        self._lock = asyncio.Lock()

    async def __call__(self, event: Event) -> None:
        async with self._lock:
            if self._builtin is not None:
                _observe_progress(self._builtin, event)
            if self._callback is not None:
                returned = self._callback(event)
                if inspect.isawaitable(returned):
                    await returned

    def close(self) -> None:
        _close_progress(self._builtin)


def _close_event_observer(observer: object) -> None:
    if isinstance(observer, (_SyncEventObserver, _AsyncEventObserver)):
        observer.close()


def _candidate_model_ids(candidates: tuple[Candidate, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(model for candidate in candidates for model in candidate.models))


def _close_progress(observer: object) -> None:
    close = getattr(observer, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        _logger.exception("ScreamingFace progress cleanup failed")


def _observe_progress(observer: Callable[[Event], None], event: Event) -> None:
    """Keep decorative progress output outside the Evaluation failure boundary."""

    try:
        observer(event)
    except (OSError, ValueError):
        # Closed pipes and notebook streams must not cancel paid Engine work.
        return
    except Exception:
        # Progress is decorative, so an unexpected renderer defect must not abort paid work.
        # Log it rather than swallowing it: this path needs to remain diagnosable.
        _logger.exception("ScreamingFace progress rendering failed")


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
    except BaseException as exc:
        # INVARIANT: sweep BEFORE cancelling the siblings, exactly as the synchronous path
        # does. Each Run discards its own capability on the way out, so cancelling first
        # empties the registry and makes this fallback a guaranteed no-op.
        try:
            await transport.cancel_active()
        except Exception as cancel_error:  # noqa: BLE001 - preserve the original interruption
            exc.add_note(f"Stopping active SF Engine runs also failed: {cancel_error}")
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


def _validate_check_surface(
    values: Sequence[Recipe],
    benchmark: str,
    resource: _BenchmarkResource,
) -> str | None:
    """Settle loop Recipes against a benchmark's check surface before spend.

    A missing surface fails closed. A paid surface declares the maximum number
    of benchmark-owned check calls; the returned disclosure text carries that
    cost multiplier to whichever surface shows it — the evaluation panel when
    one is rendering, a Python warning otherwise (OME-845). Returns None when
    there is nothing to disclose.
    """

    from screamingface.corrective import CorrectiveLoop, SelfCorrective
    from screamingface.errors import PlanningError

    loops = tuple(value for value in values if isinstance(value, CorrectiveLoop | SelfCorrective))
    if not loops:
        return None
    surface = resource.check_surface
    if surface is None:
        names = ", ".join(repr(value.name) for value in loops)
        raise PlanningError(
            f"Benchmark {benchmark!r} does not support mid-run checking, so corrective "
            f"candidate(s) {names} cannot run on it",
            code="check_surface_missing",
            permanent=True,
            details={"benchmark": benchmark, "candidates": [value.name for value in loops]},
        )
    if surface.expected_check_cost != "paid":
        return None
    per_case = sum(value.max_rounds * _loop_member_count(value) for value in loops)
    maximum = per_case * resource.case_count
    return (
        f"Benchmark {benchmark!r} may make up to {maximum} paid check calls "
        f"({per_case} per case x {resource.case_count} cases), in addition to the "
        "Candidate's own model calls. Passing earlier uses fewer calls; each check "
        "may retry according to the benchmark's policy."
    )


def _loop_member_count(recipe: Recipe) -> int:
    from screamingface.corrective import CorrectiveLoop

    return len(recipe.members) if isinstance(recipe, CorrectiveLoop) else 1


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
