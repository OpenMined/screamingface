"""Complete validation, compilation, execution, and decoding for one Evaluation."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from screamingface._core.ports import AsyncRunTransport, SyncRunTransport, _RunOutcome
from screamingface._evaluation.benchmark import _BenchmarkManifest
from screamingface._evaluation.model import (
    Candidate,
    _candidate_from_engine,
    _candidate_values,
    _Evaluation,
    _evaluation_from_engine,
    _member_projection,
    _operation_from_engine,
    _validate_limit,
)
from screamingface.discovery import ModelInfo
from screamingface.events import Event
from screamingface.recipe import Recipe
from screamingface.report import Report

type _SyncModelListing = Callable[[], Sequence[ModelInfo]]
type _AsyncModelListing = Callable[[], Awaitable[Sequence[ModelInfo]]]
type _SyncManifestLoading = Callable[[str | None], _BenchmarkManifest]
type _AsyncManifestLoading = Callable[[str | None], Awaitable[_BenchmarkManifest]]

_MAX_CANDIDATES_IN_FLIGHT = 8


def evaluate_sync(
    load_manifest: _SyncManifestLoading,
    transport: SyncRunTransport,
    list_models: _SyncModelListing,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
    limit: int | None,
    on_event: Callable[[Event], None] | None,
    progress: bool | None,
) -> Report:
    """Run the complete synchronous Evaluation workflow behind the Client interface."""

    from screamingface._evaluation.results import report_from_outcomes

    _evaluation_options(on_event, progress)
    evaluation = _compile_sync(load_manifest, candidates, benchmark, limit)
    _validate_required_models(evaluation, list_models())
    observer = _sync_event_observer(on_event, progress)
    outcomes = _run_candidates_sync(transport, tuple(evaluation.candidates), observer)
    return report_from_outcomes(evaluation, outcomes)


async def evaluate_async(
    load_manifest: _AsyncManifestLoading,
    transport: AsyncRunTransport,
    list_models: _AsyncModelListing,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
    limit: int | None,
    on_event: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
) -> Report:
    """Run the complete asynchronous Evaluation workflow behind the Client interface."""

    from screamingface._evaluation.results import report_from_outcomes

    _evaluation_options(on_event, progress)
    evaluation = await _compile_async(load_manifest, candidates, benchmark, limit)
    _validate_required_models(evaluation, await list_models())
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
                builtin(event)
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
                builtin(event)
            if callback is not None:
                returned = callback(event)
                if inspect.isawaitable(returned):
                    await returned

    return observe


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
        futures = tuple(
            executor.submit(transport.run, candidate, observer) for candidate in candidates
        )
        try:
            return tuple(
                (candidate, future.result())
                for candidate, future in zip(candidates, futures, strict=True)
            )
        except BaseException:
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


def _compile_sync(
    load_manifest: _SyncManifestLoading,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
    limit: int | None,
) -> _Evaluation:
    values = _evaluation_inputs(candidates, benchmark, limit)
    return _compile(values, load_manifest(benchmark), limit)


async def _compile_async(
    load_manifest: _AsyncManifestLoading,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
    limit: int | None,
) -> _Evaluation:
    values = _evaluation_inputs(candidates, benchmark, limit)
    return _compile(values, await load_manifest(benchmark), limit)


def _compile(
    candidates: tuple[Recipe, ...],
    manifest: _BenchmarkManifest,
    limit: int | None,
) -> _Evaluation:
    from screamingface._evaluation.compiler import compile_benchmark

    case_count = manifest.info.case_count if limit is None else min(limit, manifest.info.case_count)
    compiled = []
    model_calls = 0
    synthesis_calls = 0
    for value in candidates:
        candidate = compile_benchmark(value, manifest, limit=case_count)
        model_calls += candidate.model_calls_per_case
        synthesis_calls += candidate.synthesis_calls_per_case
        compiled.append(
            _candidate_from_engine(
                name=value.name,
                kind=candidate.kind,
                models=candidate.models,
                url4=candidate.url4,
                operations=tuple(
                    _operation_from_engine(
                        id=operation.id,
                        kind=operation.kind,
                        label=operation.label,
                        depends_on=operation.depends_on,
                    )
                    for operation in candidate.operations
                ),
                members=tuple(
                    _member_projection(
                        operation_id=member.operation_id,
                        name=member.name,
                        kind=member.kind,
                        models=member.models,
                    )
                    for member in candidate.members
                ),
            )
        )
    return _evaluation_from_engine(
        benchmark=manifest.info,
        limit=limit,
        case_count=case_count,
        candidates=compiled,
        required_capabilities=manifest.required_capabilities,
        required_models=tuple(
            dict.fromkeys(
                (
                    *(model for candidate in compiled for model in candidate.models),
                    manifest.judge_model,
                )
            )
        ),
        operation_counts={
            "model": model_calls * case_count,
            "synthesis": synthesis_calls * case_count,
            "judge": (
                len(compiled) * case_count * manifest.criteria_per_case * manifest.judge_passes
            ),
            "grading": len(compiled) * case_count,
            "aggregation": len(compiled),
        },
    )


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
    benchmark: str | None,
    limit: int | None,
) -> tuple[Recipe, ...]:
    values = _candidate_values(candidates)
    if benchmark is not None and (not isinstance(benchmark, str) or not benchmark.strip()):
        raise ValueError("benchmark must be a non-empty string or None")
    _validate_limit(limit)
    return values


__all__: list[str] = []
