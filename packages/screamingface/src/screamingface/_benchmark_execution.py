"""One-request URL4 execution for engine-advertised benchmarks."""

from __future__ import annotations

import httpx

from screamingface._compiler import MAJORITY_VOTE_ROUTE, compile_benchmark_expression
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
from screamingface._profile import REPORT_SCHEMA, ModelRecord, Registry, load_registry
from screamingface._progress import Progress, ProgressSetting
from screamingface._requirements import evaluate_requirements
from screamingface.benchmark import Benchmark
from screamingface.errors import (
    EngineConnectionError,
    EngineProtocolError,
    UnknownBenchmarkError,
    UnknownModelError,
    UnsupportedReducerError,
    UnsupportedToolError,
)
from screamingface.recipe import Recipe
from screamingface.reducers import MajorityVote, Model
from screamingface.report import EvaluationFailure, FailureKind, MemberReport, Report

_EVALUATION_TIMEOUT = 910.0


def evaluate_benchmark(
    benchmark: Benchmark,
    recipe: Recipe,
    *,
    first: int | None,
    progress: ProgressSetting = None,
) -> Report:
    """Compile and execute one complete benchmark-run URL4 expression."""

    if not isinstance(benchmark, Benchmark):
        raise TypeError("evaluation requires an sf.Benchmark")
    if not isinstance(recipe, Recipe):
        raise TypeError("benchmark evaluation requires an sf.Model or sf.Fusion")
    limit = _first(first)
    tracker = Progress(recipe.name, benchmark.id, progress)
    tracker.stage("checking", "Checking benchmark and model requirements")
    try:
        registry = load_registry()
        _manifest(benchmark, registry)
        _preflight(recipe, benchmark, registry)
        require_connections(evaluate_requirements(recipe, benchmark, registry), registry)
        expression = compile_benchmark_expression(
            benchmark_id=benchmark.id,
            cases_route=_required_route(benchmark._cases_route, "cases"),
            grader_route=_required_route(benchmark._grader_route, "grader"),
            aggregator_route=_required_route(benchmark._aggregator_route, "aggregator"),
            recipe=recipe,
            tools=benchmark.tools,
            max_tool_rounds=benchmark.max_tool_rounds,
            first=limit,
        )
        require_eval_request_target(
            expression,
            registry.max_request_target_bytes,
            f"benchmark {benchmark.id!r}",
        )
        tracker.stage(
            "running",
            "Executing the complete URL4 benchmark graph",
            total=limit,
        )
        response = _request(expression)
        report = _report(response, benchmark, recipe, expression)
    except Exception as exc:
        tracker.fail(str(exc))
        raise
    if report.complete:
        tracker.finish("Complete")
    else:
        tracker.stop(
            f"{report.n_scored}/{report.n_cases} cases scored",
            completed=report.n_scored,
            total=report.n_cases,
        )
    return report


def _request(expression: str) -> httpx.Response:
    base_url = current_engine_url()
    try:
        response = httpx.get(
            f"{base_url}{EVAL_PATH}",
            params={"q": expression},
            timeout=_EVALUATION_TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        raise EngineConnectionError("URL4 benchmark evaluation timed out") from exc
    except (httpx.RequestError, httpx.InvalidURL) as exc:
        raise EngineConnectionError(
            f"could not reach the configured URL4 engine at {base_url}"
        ) from exc
    if not response.is_success:
        error = engine_error(response)
        if error is None:
            raise EngineProtocolError(
                f"URL4 engine returned HTTP {response.status_code} for benchmark evaluation"
            )
        code, message = error
        raise EngineProtocolError(
            f"URL4 engine returned HTTP {response.status_code} ({code}): {message}"
        )
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/plain":
        raise EngineProtocolError("URL4 benchmark success must be plaintext")
    return response


def _report(
    response: httpx.Response,
    benchmark: Benchmark,
    recipe: Recipe,
    expression: str,
) -> Report:
    try:
        payload = unique_json_object(response.text)
        exact_fields(
            payload,
            {
                "schema",
                "benchmark_id",
                "case_ids",
                "n_cases",
                "n_scored",
                "coverage",
                "score",
                "baseline",
                "gain",
                "members",
                "metrics",
                "failures",
                "complete",
            },
            "benchmark report",
        )
        if payload["schema"] != REPORT_SCHEMA:
            raise ValueError(f"expected schema {REPORT_SCHEMA!r}")
        if payload["benchmark_id"] != benchmark.id:
            raise ValueError("report benchmark ID does not match the loaded benchmark")
        case_ids = _case_ids(payload["case_ids"])
        n_cases = _integer(payload["n_cases"], "report n_cases", minimum=1)
        if len(case_ids) != n_cases:
            raise ValueError("report case_ids length must equal n_cases")
        n_scored = _integer(payload["n_scored"], "report n_scored", minimum=0)
        members = _members(payload["members"], recipe)
        metrics = _metrics(payload["metrics"], "report metrics")
        failures = _failures(payload["failures"])
        complete = payload["complete"]
        if not isinstance(complete, bool) or complete != (not failures):
            raise ValueError("report complete must equal whether failures is empty")
        return Report(
            benchmark_id=benchmark.id,
            recipe_name=recipe.name,
            url4=expression,
            n_cases=n_cases,
            n_scored=n_scored,
            coverage=_number(payload["coverage"], "report coverage"),
            score=_optional_number(payload["score"], "report score"),
            baseline=_optional_number(payload["baseline"], "report baseline"),
            gain=_optional_number(payload["gain"], "report gain", signed=True),
            members=members,
            metrics=metrics,
            failures=failures,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineProtocolError(f"invalid benchmark report: {exc}") from exc


def _manifest(benchmark: Benchmark, registry: Registry) -> None:
    current = next((record for record in registry.benchmarks if record.id == benchmark.id), None)
    if current is None:
        raise UnknownBenchmarkError(f"unknown benchmark {benchmark.id!r}")
    expected = (
        benchmark.title,
        benchmark._cases_route,
        benchmark.grader.kind,
        benchmark._grader_route,
        benchmark.aggregator.kind,
        benchmark._aggregator_route,
        tuple(tool.id for tool in benchmark.tools),
        benchmark.max_tool_rounds,
    )
    observed = (
        current.title,
        current.cases_route,
        current.grader.kind,
        current.grader.route,
        current.aggregator.kind,
        current.aggregator.route,
        current.tools,
        current.max_tool_rounds,
    )
    if expected != observed:
        raise EngineProtocolError(
            f"loaded benchmark {benchmark.id!r} no longer matches the configured engine"
        )


def _members(value: object, recipe: Recipe) -> tuple[tuple[str, MemberReport], ...]:
    payload = object_value(value, "report members")
    expected = tuple((member.id, member.model) for member in recipe._members)
    if tuple(payload) != tuple(member_id for member_id, _ in expected):
        raise ValueError("report member slots do not match the Recipe")
    values: list[tuple[str, MemberReport]] = []
    for member_id, model in expected:
        record = object_value(payload[member_id], f"report member {member_id!r}")
        exact_fields(record, {"model", "score", "metrics"}, f"report member {member_id!r}")
        if record["model"] != model:
            raise ValueError(f"report member {member_id!r} model does not match the Recipe")
        values.append(
            (
                member_id,
                MemberReport(
                    model=model,
                    score=_optional_number(record["score"], f"member {member_id!r} score"),
                    metrics=_metrics(record["metrics"], f"member {member_id!r} metrics"),
                ),
            )
        )
    return tuple(values)


def _failures(value: object) -> tuple[EvaluationFailure, ...]:
    if not isinstance(value, list):
        raise TypeError("report failures must be a list")
    failures: list[EvaluationFailure] = []
    for raw in value:
        record = object_value(raw, "report failure")
        exact_fields(record, {"case_id", "kind", "message", "status", "code"}, "report failure")
        failures.append(
            EvaluationFailure(
                case_id=nonblank(record["case_id"], "failure case ID"),
                kind=_failure_kind(record["kind"]),
                message=nonblank(record["message"], "failure message"),
                status=_optional_integer(record["status"], "failure status"),
                code=(None if record["code"] is None else nonblank(record["code"], "failure code")),
            )
        )
    return tuple(failures)


def _failure_kind(value: object) -> FailureKind:
    allowed: tuple[FailureKind, ...] = (
        "connection",
        "timeout",
        "http",
        "url4",
        "protocol",
        "skipped",
    )
    if value not in allowed:
        raise ValueError(f"unknown report failure kind {value!r}")
    return value  # type: ignore[return-value]


def _preflight(recipe: Recipe, benchmark: Benchmark, registry: Registry) -> None:
    models = {record.id: record for record in registry.models}
    for model in _required_models(recipe):
        if model not in models:
            raise UnknownModelError(f"unknown model {model!r}")
    _tool_support(recipe, benchmark, models)
    _reducer_support(recipe, registry)


def _tool_support(recipe: Recipe, benchmark: Benchmark, models: dict[str, ModelRecord]) -> None:
    required_tools = {tool.id for tool in benchmark.tools}
    for member in recipe._members:
        missing = required_tools - set(models[member.model].supported_tools)
        if missing:
            raise UnsupportedToolError(
                f"model {member.model!r} does not support benchmark tool(s): {sorted(missing)}"
            )


def _reducer_support(recipe: Recipe, registry: Registry) -> None:
    for strategy in recipe._reducers:
        if isinstance(strategy, MajorityVote):
            reducer = next(
                (record for record in registry.reducers if record.id == strategy.kind),
                None,
            )
            if reducer is None or reducer.route != MAJORITY_VOTE_ROUTE:
                raise UnsupportedReducerError(f"engine does not advertise {MAJORITY_VOTE_ROUTE!r}")
        elif not isinstance(strategy, Model):
            raise UnsupportedReducerError(f"unsupported reducer {type(strategy).__name__!r}")


def _required_models(recipe: Recipe) -> tuple[str, ...]:
    models = list(recipe.model_ids)
    models.extend(reducer.model for reducer in recipe._reducers if isinstance(reducer, Model))
    return tuple(models)


def _case_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError("report case_ids must be a list")
    ids = tuple(nonblank(case_id, "report case ID") for case_id in value)
    if len(ids) != len(set(ids)):
        raise ValueError("report case_ids must be unique")
    return ids


def _metrics(value: object, label: str) -> dict[str, float]:
    payload = object_value(value, label)
    return {
        nonblank(key, f"{label} name"): _number(metric, f"{label} {key!r}")
        for key, metric in payload.items()
    }


def _first(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("first must be a positive integer or None")
    return value


def _required_route(value: str | None, label: str) -> str:
    if value is None:
        raise ValueError(f"benchmark has no engine {label} route")
    return value


def _integer(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label, minimum=100)


def _number(value: object, label: str, *, signed: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    minimum = -1.0 if signed else 0.0
    if not minimum <= normalized <= 1.0:
        raise ValueError(f"{label} must be between {minimum:g} and 1")
    return normalized


def _optional_number(value: object, label: str, *, signed: bool = False) -> float | None:
    return None if value is None else _number(value, label, signed=signed)


__all__ = ["evaluate_benchmark"]
