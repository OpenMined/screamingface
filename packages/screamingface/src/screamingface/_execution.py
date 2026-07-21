"""Preflight and bounded synchronous execution for Fusion.run()."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Protocol

import httpx

from screamingface import connections
from screamingface._compiler import MAJORITY_VOTE_ROUTE, compile_fusion
from screamingface._config import current_engine_url
from screamingface._connection_preflight import require_connections
from screamingface._engine_http import (
    EVAL_PATH,
    engine_error,
    exact_fields,
    nonblank,
    object_value,
    require_eval_request_target,
    unique_json_object,
)
from screamingface._exact_choice import validate_exact_reference
from screamingface._profile import FUSION_RESULT_SCHEMA, Registry, load_registry
from screamingface._progress import Progress, ProgressSetting
from screamingface._requirements import evaluate_requirements, run_requirements
from screamingface.benchmark import Benchmark, Case
from screamingface.benchmarks import load as load_benchmark
from screamingface.errors import (
    InvalidBenchmarkError,
    UnknownModelError,
    UnsupportedReducerError,
    UnsupportedToolError,
)
from screamingface.fusion import Fusion
from screamingface.graders import ExactChoice
from screamingface.reducers import MajorityVote, Model
from screamingface.run import CaseResult, FailureKind, MemberResult, Run, RunFailure

if TYPE_CHECKING:
    from screamingface.report import Report

_CASE_CONCURRENCY = 4
_RUN_TIMEOUT = 910.0
_AUTH_REJECTION_CODES = frozenset({"authentication_required", "connection_needs_reauth"})
_RETRYABLE_FAILURE_CODES = frozenset(
    {
        "gateway_timeout",
        "gateway_unavailable",
        "overloaded",
        "provider_unavailable",
        "rate_limited",
        "resolution_failed",
        "timeout",
    }
)


class _EngineClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response: ...


def run_fusion(
    fusion: Fusion,
    benchmark: str | Benchmark,
    *,
    first: int | None,
    progress: ProgressSetting = None,
    _connections_checked: bool = False,
    _registry: Registry | None = None,
    _tracker: Progress | None = None,
) -> Run:
    """Preflight, execute every selected case, and preserve canonical order."""

    benchmark_id = (
        benchmark if isinstance(benchmark, str) else getattr(benchmark, "id", "benchmark")
    )
    tracker = _tracker or Progress(fusion.name, benchmark_id, progress)
    owns_tracker = _tracker is None
    if owns_tracker:
        tracker.stage("checking", "Checking requirements")
    try:
        result = _run_fusion(
            fusion,
            benchmark,
            first=first,
            _connections_checked=_connections_checked,
            _registry=_registry,
            tracker=tracker,
        )
    except Exception as exc:
        if owns_tracker:
            tracker.fail(str(exc))
        raise
    if owns_tracker:
        tracker.finish("Run complete")
    return result


def _run_fusion(
    fusion: Fusion,
    benchmark: str | Benchmark,
    *,
    first: int | None,
    _connections_checked: bool,
    _registry: Registry | None,
    tracker: Progress,
) -> Run:
    limit = _first(first)
    if not isinstance(benchmark, (str, Benchmark)):
        raise TypeError("benchmark must be a benchmark ID or sf.Benchmark")
    recipe = compile_fusion(fusion)
    resolved = load_benchmark(benchmark) if isinstance(benchmark, str) else benchmark
    cases = resolved._materialize_cases()
    selected = cases if limit is None else cases[:limit]
    _references(selected, resolved)
    registry = _registry or load_registry()
    _preflight(fusion, resolved, registry)
    if not _connections_checked:
        require_connections(run_requirements(fusion, resolved, registry), registry)

    expressions = tuple(
        (
            case,
            compile_fusion(
                fusion,
                question=case.input,
                tools=resolved.tools,
                max_tool_rounds=resolved.max_tool_rounds,
            ),
        )
        for case in selected
    )
    for case, expression in expressions:
        require_eval_request_target(
            expression,
            registry.max_request_target_bytes,
            f"case {case.id!r}",
        )
    tracker.stage("running", "Attempting cases", total=len(selected))
    base_url = current_engine_url()
    with httpx.Client(base_url=base_url, timeout=_RUN_TIMEOUT) as client:
        results = _execute_cases(client, fusion, expressions, registry, tracker)
    return Run(
        benchmark=resolved,
        fusion_name=fusion.name,
        fusion_url4=recipe,
        members=tuple((member.id, member.model) for member in fusion._members),
        cases=selected,
        results=results,
    )


def _execute_cases(
    client: _EngineClient,
    fusion: Fusion,
    expressions: tuple[tuple[Case, str], ...],
    registry: Registry,
    tracker: Progress | None = None,
) -> tuple[CaseResult, ...]:
    if not expressions:
        return ()
    canary_case, canary_expression = expressions[0]
    canary = _execute_case(client, fusion, canary_case, canary_expression)
    if canary.failure is not None and _retryable(canary.failure):
        # WHY: One retry distinguishes a brief upstream wobble from a benchmark-wide outage while
        # bounding duplicate model spend before the parallel fan-out begins.
        canary = _execute_case(client, fusion, canary_case, canary_expression)
    _advance(tracker)
    if canary.failure is not None:
        _refresh_rejected_connections(canary.failure.code, registry)
        skipped = tuple(_unscheduled(case.id, canary.failure) for case, _ in expressions[1:])
        _advance(tracker, len(skipped))
        return (canary, *skipped)
    return (canary, *_execute_remaining(client, fusion, expressions[1:], registry, tracker))


def _execute_remaining(
    client: _EngineClient,
    fusion: Fusion,
    expressions: tuple[tuple[Case, str], ...],
    registry: Registry,
    tracker: Progress | None,
) -> tuple[CaseResult, ...]:
    if not expressions:
        return ()
    results: list[CaseResult] = []
    with ThreadPoolExecutor(max_workers=min(_CASE_CONCURRENCY, len(expressions))) as pool:
        for start in range(0, len(expressions), _CASE_CONCURRENCY):
            batch = expressions[start : start + _CASE_CONCURRENCY]
            completed = tuple(pool.map(lambda value: _execute_case(client, fusion, *value), batch))
            results.extend(completed)
            _advance(tracker, len(completed))
            failure = _stopping_failure(completed)
            if failure is not None:
                _refresh_rejected_connections(failure.code, registry)
                results.extend(
                    _unscheduled(case.id, failure)
                    for case, _expression in expressions[start + len(batch) :]
                )
                _advance(tracker, len(expressions) - start - len(batch))
                break
    return tuple(results)


def _advance(tracker: Progress | None, count: int = 1) -> None:
    if tracker is not None:
        tracker.advance(count)


def _stopping_failure(results: tuple[CaseResult, ...]) -> RunFailure | None:
    return next(
        (
            result.failure
            for result in results
            if result.failure is not None and not _retryable(result.failure)
        ),
        None,
    )


def _retryable(failure: RunFailure) -> bool:
    if failure.kind in {"connection", "timeout"}:
        return True
    if failure.code in _RETRYABLE_FAILURE_CODES:
        return True
    return failure.code is None and failure.status is not None and failure.status >= 500


def _refresh_rejected_connections(code: str | None, registry: Registry) -> None:
    if code in _AUTH_REJECTION_CODES:
        connections._list_for_registry(registry)


def _unscheduled(case_id: str, cause: RunFailure) -> CaseResult:
    cause_code = cause.code or "evaluation_failure"
    return _failed(
        case_id,
        "skipped",
        f"Case was not scheduled after evaluation stopped on {cause_code!r}.",
        code="not_scheduled",
    )


def evaluate_fusion(
    fusion: Fusion,
    benchmark: str | Benchmark,
    *,
    first: int | None,
    progress: ProgressSetting = None,
) -> Report:
    """Check the complete model-backed requirement union once, then execute all stages."""

    from screamingface._grading import grade_run

    benchmark_id = (
        benchmark if isinstance(benchmark, str) else getattr(benchmark, "id", "benchmark")
    )
    tracker = Progress(fusion.name, benchmark_id, progress)
    tracker.stage("checking", "Checking requirements")
    try:
        _first(first)
        if not isinstance(benchmark, (str, Benchmark)):
            raise TypeError("benchmark must be a benchmark ID or sf.Benchmark")
        resolved = load_benchmark(benchmark) if isinstance(benchmark, str) else benchmark
        registry = load_registry()
        _preflight(fusion, resolved, registry)
        try:
            requirements = evaluate_requirements(fusion, resolved, registry)
        except ValueError as exc:
            raise UnknownModelError(str(exc)) from exc
        require_connections(requirements, registry)
        run = run_fusion(
            fusion,
            resolved,
            first=first,
            _connections_checked=True,
            _registry=registry,
            _tracker=tracker,
        )
        # WHY: A failed atomic run still becomes an aggregatable report, but it has no response
        # work to show in the shared notebook progress receipt.
        grades = (
            grade_run(run, _connections_checked=True, _tracker=tracker)
            if any(result.failure is None for result in run.results)
            else grade_run(run, _connections_checked=True, progress=False)
        )
        tracker.stage("aggregating", "Aggregating report")
        report = grades.aggregate()
    except Exception as exc:
        tracker.fail(str(exc))
        raise
    _finish_evaluation(tracker, report, run)
    return report


def _finish_evaluation(tracker: Progress, report: Report, run: Run) -> None:
    if report.complete:
        tracker.finish("Complete")
        return
    tracker.stop(
        f"{report.n_scored}/{report.n_cases} cases scored · {_attempted_cases(run)} attempted",
        completed=report.n_scored,
        total=report.n_cases,
    )


def _attempted_cases(run: Run) -> int:
    return sum(
        result.failure is None or result.failure.code != "not_scheduled" for result in run.results
    )


def _execute_case(
    client: _EngineClient,
    fusion: Fusion,
    case: Case,
    expression: str,
) -> CaseResult:
    try:
        response = client.get(EVAL_PATH, params={"q": expression})
    except httpx.TimeoutException:
        return _failed(case.id, "timeout", "URL4 engine evaluation timed out")
    except (httpx.RequestError, httpx.InvalidURL):
        return _failed(case.id, "connection", "could not reach the configured URL4 engine")
    return _response_result(case.id, fusion, response)


def _response_result(case_id: str, fusion: Fusion, response: httpx.Response) -> CaseResult:
    if not response.is_success:
        return _error_result(case_id, response)
    return _success_result(case_id, fusion, response)


def _error_result(case_id: str, response: httpx.Response) -> CaseResult:
    error = engine_error(response)
    if error is None:
        return _failed(
            case_id,
            "http",
            f"URL4 engine returned HTTP {response.status_code}",
            status=response.status_code,
        )
    code, message = error
    kind: FailureKind = "timeout" if response.status_code == 504 or code == "timeout" else "url4"
    return _failed(
        case_id,
        kind,
        message,
        status=response.status_code,
        code=code,
    )


def _success_result(case_id: str, fusion: Fusion, response: httpx.Response) -> CaseResult:

    content_type = response.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != "text/plain":
        return _protocol(case_id, "engine success must be plaintext", response.status_code)
    try:
        payload = unique_json_object(response.text)
        members, answer = _fusion_result(payload, fusion)
    except (KeyError, TypeError, ValueError) as exc:
        return _protocol(case_id, f"invalid fusion result: {exc}", response.status_code)
    return CaseResult(case_id, members=members, answer=answer)


def _fusion_result(
    payload: dict[str, object], fusion: Fusion
) -> tuple[tuple[tuple[str, MemberResult], ...], str]:
    exact_fields(payload, {"schema", "members", "answer"}, "fusion result")
    if payload["schema"] != FUSION_RESULT_SCHEMA:
        raise ValueError(f"expected schema {FUSION_RESULT_SCHEMA!r}")
    wire_members = object_value(payload["members"], "fusion members")
    expected_ids = tuple(member.id for member in fusion._members)
    if set(wire_members) != set(expected_ids):
        raise ValueError("member slots do not match the Fusion")

    members: list[tuple[str, MemberResult]] = []
    for expected in fusion._members:
        item = object_value(wire_members[expected.id], f"member {expected.id!r}")
        exact_fields(item, {"model", "answer"}, f"member {expected.id!r}")
        if item["model"] != expected.model:
            raise ValueError(f"member {expected.id!r} model does not match the Fusion")
        members.append(
            (
                expected.id,
                MemberResult(
                    model=expected.model,
                    answer=nonblank(item["answer"], f"member {expected.id!r} answer"),
                ),
            )
        )
    return tuple(members), nonblank(payload["answer"], "fusion answer")


def _preflight(fusion: Fusion, benchmark: Benchmark, registry: Registry) -> None:
    models = {record.id: record for record in registry.models}
    for model in _required_models(fusion, benchmark):
        if model not in models:
            raise UnknownModelError(f"unknown model {model!r}")
    for member in fusion._members:
        supported = set(models[member.model].supported_tools)
        missing = {tool.id for tool in benchmark.tools} - supported
        if missing:
            raise UnsupportedToolError(
                f"model {member.model!r} does not support benchmark tool(s): {sorted(missing)}"
            )
    _reducer(fusion, registry)


def _required_models(fusion: Fusion, _benchmark: Benchmark) -> tuple[str, ...]:
    models = list(fusion.model_ids)
    models.extend(reducer.model for reducer in fusion._reducers if isinstance(reducer, Model))
    return tuple(models)


def _reducer(fusion: Fusion, registry: Registry) -> None:
    for strategy in fusion._reducers:
        if isinstance(strategy, MajorityVote):
            reducer = next(
                (record for record in registry.reducers if record.id == strategy.kind),
                None,
            )
            if reducer is None or reducer.route != MAJORITY_VOTE_ROUTE:
                raise UnsupportedReducerError(f"engine does not advertise {MAJORITY_VOTE_ROUTE!r}")
        elif not isinstance(strategy, Model):
            raise UnsupportedReducerError(f"unsupported reducer {type(strategy).__name__!r}")


def _references(cases: Sequence[Case], benchmark: Benchmark) -> None:
    for case in cases:
        reference = case.reference
        if reference is None:
            raise InvalidBenchmarkError(f"case {case.id!r} has no grading reference")
        if isinstance(benchmark.grader, ExactChoice):
            try:
                validate_exact_reference(reference)
            except (TypeError, ValueError) as exc:
                raise InvalidBenchmarkError(f"case {case.id!r} {exc}") from exc


def _first(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("first must be a positive integer or None")
    return value


def _failed(
    case_id: str,
    kind: FailureKind,
    message: str,
    *,
    status: int | None = None,
    code: str | None = None,
) -> CaseResult:
    failure = RunFailure(
        case_id=case_id,
        kind=kind,
        message=message,
        status=status,
        code=code,
    )
    return CaseResult(case_id, members=(), answer=None, failure=failure)


def _protocol(case_id: str, message: str, status: int) -> CaseResult:
    return _failed(case_id, "protocol", message, status=status)


__all__ = ["evaluate_fusion", "run_fusion"]
