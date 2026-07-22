"""One-request URL4 execution for engine-advertised benchmarks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from screamingface._compiler import (
    MAJORITY_VOTE_ROUTE,
    compile_benchmark_expression,
    compile_candidates_benchmark_expression,
)
from screamingface._connection_preflight import require_connections
from screamingface._engine_http import (
    exact_fields,
    nonblank,
    object_value,
    require_eval_request_target,
    unique_json_object,
)
from screamingface._engine_stream import EvaluationEvent, evaluate_stream
from screamingface._profile import (
    REPORT_SCHEMA,
    STUDY_REPORT_SCHEMA,
    ModelRecord,
    Registry,
    load_registry,
)
from screamingface._progress import (
    OperationStage,
    OperationStatus,
    Progress,
    ProgressSetting,
)
from screamingface._requirements import evaluate_requirements
from screamingface.benchmark import Benchmark
from screamingface.errors import (
    EngineProtocolError,
    UnknownBenchmarkError,
    UnknownModelError,
    UnsupportedReducerError,
    UnsupportedToolError,
)
from screamingface.graders import Rubric
from screamingface.recipe import Recipe
from screamingface.reducers import MajorityVote, Model
from screamingface.report import (
    CandidateReport,
    EvaluationFailure,
    FailureKind,
    MemberReport,
    Report,
    StudyReport,
)

# The local engine permits a complete research transaction to run for 30 minutes.
# Give HTTP framing and terminal SSE delivery a small margin beyond that server deadline.
_EVALUATION_TIMEOUT = 1810.0


def evaluate_candidates(
    benchmark: Benchmark,
    candidates: Sequence[Recipe],
    *,
    first: int | None,
    progress: ProgressSetting = None,
) -> StudyReport:
    """Execute one ordered candidate set as a shared engine-side benchmark graph."""

    values = _candidates(candidates)
    limit = _first(first)
    tracker = Progress(f"{len(values)} candidates", benchmark.id, progress)
    tracker.stage("checking", "Checking benchmark and candidate requirements")
    try:
        registry = load_registry()
        _manifest(benchmark, registry)
        for candidate in values:
            _preflight(candidate, benchmark, registry)
        requirements = tuple(
            dict.fromkeys(
                requirement
                for candidate in values
                for requirement in evaluate_requirements(candidate, benchmark, registry)
            )
        )
        require_connections(requirements, registry)
        expression = candidates_url4(benchmark, values, first=limit)
        require_eval_request_target(
            expression,
            registry.max_request_target_bytes,
            f"benchmark {benchmark.id!r} candidate set",
        )
        tracker.stage("running", "Executing the shared candidate URL4 graph", total=len(values))
        response_text = _request(
            expression,
            tracker=tracker,
            total=len(values),
            completion_stage="candidate",
        )
        report = _study_report(response_text, benchmark, values, expression)
    except Exception as exc:
        tracker.fail(str(exc))
        raise
    completed = sum(candidate.n_scored > 0 for candidate in report.candidates.values())
    if report.complete:
        tracker.finish("Complete")
    else:
        tracker.partial(
            f"{completed}/{len(values)} candidates scored",
            completed=completed,
            total=len(values),
        )
    return report


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
        expression = benchmark_url4(benchmark, recipe, first=limit)
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
        response_text = _request(expression, tracker=tracker, total=limit)
        report = _report(response_text, benchmark, recipe, expression)
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


def benchmark_url4(benchmark: Benchmark, recipe: Recipe, *, first: int | None = None) -> str:
    """Compile one complete engine-advertised benchmark transaction without HTTP."""

    if not isinstance(benchmark, Benchmark):
        raise TypeError("URL4 compilation requires an sf.Benchmark")
    if not isinstance(recipe, Recipe):
        raise TypeError("URL4 compilation requires an sf.Model or sf.Fusion")
    limit = _first(first)
    return compile_benchmark_expression(
        benchmark_id=benchmark.id,
        cases_route=_required_route(benchmark._cases_route, "cases"),
        grader_route=_required_route(benchmark._grader_route, "grader"),
        aggregator_route=_required_route(benchmark._aggregator_route, "aggregator"),
        recipe=recipe,
        grader_kind=benchmark.grader.kind,
        tools=benchmark.tools,
        max_tool_calls=benchmark.max_tool_calls,
        tool_policy_route=benchmark._tool_policy_route,
        first=limit,
    )


def candidates_url4(
    benchmark: Benchmark,
    candidates: Sequence[Recipe],
    *,
    first: int | None = None,
) -> str:
    """Compile one shareable candidate-set benchmark transaction without HTTP."""

    if not isinstance(benchmark, Benchmark):
        raise TypeError("URL4 compilation requires an sf.Benchmark")
    values = _candidates(candidates)
    limit = _first(first)
    candidate_route = _required_route(benchmark._candidate_route, "candidate evaluation")
    tool_policy_route = _required_route(benchmark._tool_policy_route, "tool policy")
    return compile_candidates_benchmark_expression(
        benchmark_id=benchmark.id,
        cases_route=_required_route(benchmark._cases_route, "cases"),
        candidate_route=candidate_route,
        aggregator_route=_required_route(
            benchmark._candidate_aggregator_route,
            "candidate aggregator",
        ),
        candidates=values,
        tool_policy_route=tool_policy_route,
        first=limit,
    )


def _request(
    expression: str,
    *,
    tracker: Progress | None = None,
    total: int | None = None,
    completion_stage: Literal["grading", "candidate"] = "grading",
) -> str:
    saw_progress = False

    def update(event: EvaluationEvent) -> None:
        nonlocal saw_progress
        if tracker is None:
            return
        saw_progress = _update_progress(
            tracker,
            event,
            total=total,
            completion_stage=completion_stage,
            saw_progress=saw_progress,
        )

    return evaluate_stream(expression, timeout=_EVALUATION_TIMEOUT, on_event=update)


def _update_progress(
    tracker: Progress,
    event: EvaluationEvent,
    *,
    total: int | None,
    completion_stage: Literal["grading", "candidate"],
    saw_progress: bool,
) -> bool:
    if event.type == "accepted":
        tracker.stage("running", "Engine accepted the URL4 evaluation", total=total)
    elif event.type == "running":
        tracker.elapsed(0.0 if event.elapsed_seconds is None else event.elapsed_seconds)
        if not saw_progress:
            tracker.observe("running", "Engine evaluating URL4")
    elif event.type == "progress":
        _update_operation(tracker, event)
        if event.stage == completion_stage and event.status in {
            "completed",
            "failed",
            "skipped",
        }:
            tracker.advance()
        saw_progress = True
    return saw_progress


def _update_operation(tracker: Progress, event: EvaluationEvent) -> None:
    label = event.label or "Evaluation in progress"
    if event.stage in {"model", "synthesis", "grading", "candidate"}:
        tracker.operation(
            cast(OperationStage, event.stage),
            cast(OperationStatus, event.status),
            label,
            operation_id=event.operation_id,
        )
    elif event.stage == "aggregating":
        tracker.observe("aggregating", label)
    else:
        tracker.observe("running", label)


def _report(
    response_text: str,
    benchmark: Benchmark,
    recipe: Recipe,
    expression: str,
) -> Report:
    try:
        payload = unique_json_object(response_text)
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


def _study_report(
    response_text: str,
    benchmark: Benchmark,
    candidates: tuple[Recipe, ...],
    expression: str,
) -> StudyReport:
    try:
        payload = unique_json_object(response_text)
        exact_fields(
            payload,
            {"schema", "benchmark_id", "case_ids", "candidates", "complete"},
            "candidate study report",
        )
        if payload["schema"] != STUDY_REPORT_SCHEMA:
            raise ValueError(f"expected schema {STUDY_REPORT_SCHEMA!r}")
        if payload["benchmark_id"] != benchmark.id:
            raise ValueError("study report benchmark ID does not match the loaded benchmark")
        case_ids = _case_ids(payload["case_ids"])
        raw_candidates = object_value(payload["candidates"], "study report candidates")
        expected_names = tuple(candidate.name for candidate in candidates)
        if tuple(raw_candidates) != expected_names:
            raise ValueError("study report candidates do not match the requested candidate order")
        values: list[tuple[str, CandidateReport]] = []
        for name in expected_names:
            record = object_value(raw_candidates[name], f"candidate {name!r}")
            values.append((name, _candidate_report(name, record, len(case_ids))))
        complete = payload["complete"]
        if not isinstance(complete, bool) or complete != all(value.complete for _, value in values):
            raise ValueError("study report complete flag is inconsistent")
        return StudyReport(
            benchmark_id=benchmark.id,
            url4=expression,
            case_ids=case_ids,
            candidates=values,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineProtocolError(f"invalid candidate study report: {exc}") from exc


def _candidate_report(
    name: str,
    record: dict[str, object],
    case_count: int,
) -> CandidateReport:
    label = f"candidate {name!r}"
    exact_fields(
        record,
        {"n_cases", "n_scored", "coverage", "score", "metrics", "failures", "complete"},
        label,
    )
    n_cases = _integer(record["n_cases"], f"{label} n_cases", minimum=1)
    if n_cases != case_count:
        raise ValueError(f"{label} case count does not match case_ids")
    failures = _failures(record["failures"])
    complete = record["complete"]
    if not isinstance(complete, bool) or complete != (not failures):
        raise ValueError(f"{label} complete flag is inconsistent")
    return CandidateReport(
        name=name,
        n_cases=n_cases,
        n_scored=_integer(record["n_scored"], f"{label} n_scored", minimum=0),
        coverage=_number(record["coverage"], f"{label} coverage"),
        score=_optional_number(record["score"], f"{label} score"),
        metrics=_metrics(record["metrics"], f"{label} metrics"),
        failures=failures,
    )


def _manifest(benchmark: Benchmark, registry: Registry) -> None:
    current = next((record for record in registry.benchmarks if record.id == benchmark.id), None)
    if current is None:
        raise UnknownBenchmarkError(f"unknown benchmark {benchmark.id!r}")
    expected = (
        benchmark.title,
        benchmark._cases_route,
        _grader_signature(benchmark.grader),
        benchmark._grader_route,
        benchmark.aggregator.kind,
        benchmark._aggregator_route,
        tuple(tool.id for tool in benchmark.tools),
        benchmark.max_tool_calls,
        benchmark._tool_policy_route,
        benchmark._candidate_route,
        benchmark._candidate_aggregator_route,
    )
    observed = (
        current.title,
        current.cases_route,
        (
            current.grader.kind,
            current.grader.model,
            current.grader.prompt,
            current.grader.passes,
            tuple(current.grader.parameter_items),
        ),
        current.grader.route,
        current.aggregator.kind,
        current.aggregator.route,
        current.tools,
        current.max_tool_calls,
        current.tool_policy_route,
        current.candidate_route,
        current.candidate_aggregator_route,
    )
    if expected != observed:
        raise EngineProtocolError(
            f"loaded benchmark {benchmark.id!r} no longer matches the configured engine"
        )


def _grader_signature(grader: object) -> tuple[object, ...]:
    if isinstance(grader, Rubric):
        return (
            grader.kind,
            grader.model,
            grader.prompt,
            grader.passes,
            tuple(grader._parameter_items),
        )
    kind = getattr(grader, "kind", None)
    return (kind, None, None, None, ())


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


def _candidates(values: Sequence[Recipe]) -> tuple[Recipe, ...]:
    if isinstance(values, str | bytes) or not isinstance(values, Sequence):
        raise TypeError("candidates must be a sequence of sf.Model or sf.Fusion values")
    candidates = tuple(values)
    if not candidates:
        raise ValueError("candidate evaluation requires at least one Recipe")
    if not all(isinstance(candidate, Recipe) for candidate in candidates):
        raise TypeError("candidates must contain only sf.Model or sf.Fusion values")
    names = tuple(candidate.name for candidate in candidates)
    if len(names) != len(set(names)):
        duplicate = next(name for name in names if names.count(name) > 1)
        raise ValueError(f"duplicate candidate name {duplicate!r}")
    return candidates


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
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    minimum = -1.0 if signed else 0.0
    if not minimum <= normalized <= 1.0:
        raise ValueError(f"{label} must be between {minimum:g} and 1")
    return normalized


def _optional_number(value: object, label: str, *, signed: bool = False) -> float | None:
    return None if value is None else _number(value, label, signed=signed)


__all__ = [
    "benchmark_url4",
    "candidates_url4",
    "evaluate_benchmark",
    "evaluate_candidates",
]
