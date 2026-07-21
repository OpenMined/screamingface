"""Complete ExactChoice and URL4-backed Rubric execution for Run.grade()."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from statistics import fmean

import httpx

from screamingface import connections
from screamingface._compiler import compile_model_expression
from screamingface._config import current_engine_url
from screamingface._connection_preflight import require_connections
from screamingface._engine_http import (
    EVAL_PATH,
    engine_error,
    exact_fields,
    nonblank,
    require_eval_request_target,
    unique_object,
)
from screamingface._exact_choice import exact_choice_score, validate_exact_reference
from screamingface._profile import load_registry
from screamingface._progress import Progress, ProgressSetting
from screamingface._requirements import grade_requirements
from screamingface.benchmark import Case
from screamingface.errors import InvalidBenchmarkError, UnknownModelError
from screamingface.graders import ExactChoice, Rubric
from screamingface.grades import (
    CaseGrades,
    CriterionStatus,
    CriterionVerdict,
    Grade,
    GradeFailure,
    GradeFailureKind,
    Grades,
)
from screamingface.run import CaseResult, Run

_JUDGE_CONCURRENCY = 16
_JUDGE_TIMEOUT = 130.0
_VALIDATION_ATTEMPTS = 3
_METRIC_KEY_RE = re.compile(r"[^a-z0-9]+")
_AUTH_REJECTION_CODES = frozenset({"authentication_required", "connection_needs_reauth"})


@dataclass(frozen=True, slots=True)
class _Criterion:
    id: str
    section: str
    section_metric: str
    requirement: str
    weight: float


@dataclass(frozen=True, slots=True)
class _RubricReference:
    criteria: tuple[_Criterion, ...]
    section_metrics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _JudgeTask:
    case_id: str
    target: str
    criterion: _Criterion
    pass_number: int
    expression: str


def grade_run(
    run: Run,
    *,
    progress: ProgressSetting = None,
    _connections_checked: bool = False,
    _tracker: Progress | None = None,
) -> Grades:
    """Dispatch one immutable Run to its benchmark-owned grader."""

    if not isinstance(run, Run):
        raise TypeError("grade_run requires an sf.Run")
    tracker = _tracker or Progress(run.recipe_name, run.benchmark_id, progress)
    owns_tracker = _tracker is None
    tracker.stage("checking", "Preparing grading")
    try:
        grades = _grade_run(
            run,
            tracker,
            _connections_checked=_connections_checked,
        )
    except Exception as exc:
        if owns_tracker:
            tracker.fail(str(exc))
        raise
    if owns_tracker:
        tracker.finish("Grading complete")
    return grades


def _grade_run(run: Run, tracker: Progress, *, _connections_checked: bool) -> Grades:
    cases = run._cases
    grader = run._benchmark.grader
    if isinstance(grader, ExactChoice):
        total = sum(
            1 + len(result._member_items) for result in run.results if result.failure is None
        )
        tracker.stage("grading", "Grading responses", total=total)
        grades = _grade_exact(run, cases)
        tracker.advance(total)
        return grades
    if isinstance(grader, Rubric):
        return _grade_rubric(
            run,
            cases,
            grader,
            tracker=tracker,
            _connections_checked=_connections_checked,
        )
    raise TypeError(f"unsupported grader {type(grader).__name__!r}")


def _grade_exact(run: Run, cases: tuple[Case, ...]) -> Grades:
    for case in cases:
        try:
            validate_exact_reference(case.reference)
        except (TypeError, ValueError) as exc:
            raise InvalidBenchmarkError(f"case {case.id!r} {exc}") from exc
    results = tuple(
        _exact_case(case, result) for case, result in zip(cases, run.results, strict=True)
    )
    return Grades(run=run, results=results)


def _exact_case(case: Case, result: CaseResult) -> CaseGrades:
    if result.failure is not None:
        return CaseGrades(case.id, recipe=None, members=(), run_failure=result.failure)
    assert result.answer is not None
    recipe = _exact_grade(case.reference, result.answer)
    members = tuple(
        (target, _exact_grade(case.reference, member.answer))
        for target, member in result._member_items
    )
    return CaseGrades(case.id, recipe=recipe, members=members)


def _exact_grade(reference: object, answer: str) -> Grade:
    return Grade(score=exact_choice_score(reference, answer), metrics={}, coverage=1.0)


def _grade_rubric(
    run: Run,
    cases: tuple[Case, ...],
    grader: Rubric,
    *,
    tracker: Progress,
    _connections_checked: bool,
) -> Grades:
    references = tuple(_rubric_reference(case) for case in cases)
    registry = load_registry()
    if grader.model not in {record.id for record in registry.models}:
        raise UnknownModelError(f"unknown rubric judge model {grader.model!r}")
    if not _connections_checked:
        require_connections(grade_requirements(run._benchmark, registry), registry)

    tasks = _judge_tasks(run, cases, references, grader)
    tracker.stage("grading", "Grading responses", total=len(tasks))
    for task in tasks:
        require_eval_request_target(
            task.expression,
            registry.max_request_target_bytes,
            (
                f"case {task.case_id!r} {task.target} criterion "
                f"{task.criterion.id!r} pass {task.pass_number}"
            ),
        )
    verdicts = _execute_tasks(tasks, registry=registry, tracker=tracker)
    grouped = _group_verdicts(tasks, verdicts)
    results = tuple(
        _rubric_case(result, reference, grouped)
        for result, reference in zip(run.results, references, strict=True)
    )
    return Grades(run=run, results=results)


def _rubric_reference(case: Case) -> _RubricReference:
    try:
        return _decode_rubric(case.reference)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidBenchmarkError(f"case {case.id!r} invalid rubric reference: {exc}") from exc


def _decode_rubric(reference: object) -> _RubricReference:
    rubric = _mapping(reference, "rubric reference")
    sections = _list(rubric.get("sections"), "rubric sections")
    if not sections:
        raise ValueError("rubric must contain at least one section")

    criteria: list[_Criterion] = []
    section_ids: set[str] = set()
    metric_keys: set[str] = {"pass_rate"}
    section_metrics: list[str] = []
    criterion_ids: set[str] = set()
    for position, raw_section in enumerate(sections, 1):
        section = _mapping(raw_section, f"rubric section {position}")
        section_id = _section_identity(section, position)
        metric_key = _metric_key(section_id)
        _add_unique(section_ids, section_id, "rubric section identity")
        _add_unique(metric_keys, metric_key, "rubric section metric key")
        section_criteria = _list(section.get("criteria"), f"rubric section {section_id!r} criteria")
        if not section_criteria:
            raise ValueError(f"rubric section {section_id!r} must contain criteria")
        decoded = tuple(
            _criterion(raw, section_id, metric_key, criterion_ids) for raw in section_criteria
        )
        if not any(criterion.weight > 0 for criterion in decoded):
            raise ValueError(
                f"rubric section {section_id!r} must contain a positive-weight criterion"
            )
        criteria.extend(decoded)
        section_metrics.append(metric_key)
    return _RubricReference(tuple(criteria), tuple(section_metrics))


def _section_identity(section: Mapping[str, object], position: int) -> str:
    if "id" in section:
        return nonblank(section["id"], f"rubric section {position} ID")
    if "title" in section:
        return nonblank(section["title"], f"rubric section {position} title")
    raise ValueError(f"rubric section {position} requires an ID or title")


def _criterion(
    value: object,
    section: str,
    metric_key: str,
    criterion_ids: set[str],
) -> _Criterion:
    payload = _mapping(value, f"rubric section {section!r} criterion")
    criterion_id = nonblank(payload.get("id"), f"rubric section {section!r} criterion ID")
    _add_unique(criterion_ids, criterion_id, "rubric criterion ID")
    requirement = nonblank(
        payload.get("requirement"), f"rubric criterion {criterion_id!r} requirement"
    )
    weight = _weight(payload.get("weight"), criterion_id)
    return _Criterion(criterion_id, section, metric_key, requirement, weight)


def _weight(value: object, criterion_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"rubric criterion {criterion_id!r} weight must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized == 0.0:
        raise ValueError(f"rubric criterion {criterion_id!r} weight must be finite and non-zero")
    return normalized


def _metric_key(section_id: str) -> str:
    key = _METRIC_KEY_RE.sub("_", section_id.strip().lower()).strip("_")
    if not key:
        raise ValueError(f"rubric section identity {section_id!r} cannot form a metric key")
    return key


def _add_unique(seen: set[str], value: str, label: str) -> None:
    if value in seen:
        raise ValueError(f"duplicate {label}: {value!r}")
    seen.add(value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an array")
    return value


def _judge_tasks(
    run: Run,
    cases: tuple[Case, ...],
    references: tuple[_RubricReference, ...],
    grader: Rubric,
) -> tuple[_JudgeTask, ...]:
    tasks: list[_JudgeTask] = []
    for case, result, reference in zip(cases, run.results, references, strict=True):
        if result.failure is not None:
            continue
        for target, answer in _targets(result):
            for pass_number in range(1, grader.passes + 1):
                for criterion in reference.criteria:
                    context = _judge_context(case.input, answer, criterion)
                    expression = compile_model_expression(
                        model=grader.model,
                        context=context,
                        intent=grader.prompt,
                        params=grader.params,
                    )
                    tasks.append(_JudgeTask(case.id, target, criterion, pass_number, expression))
    return tuple(tasks)


def _targets(result: CaseResult) -> tuple[tuple[str, str], ...]:
    assert result.answer is not None
    return (
        ("recipe", result.answer),
        *((target, member.answer) for target, member in result._member_items),
    )


def _judge_context(question: str, answer: str, criterion: _Criterion) -> str:
    criterion_type = "negative" if criterion.weight < 0 else "positive"
    return (
        "<criterion_type>\n"
        f"{criterion_type}\n"
        "</criterion_type>\n\n"
        "<criterion>\n"
        f"{criterion.requirement}\n"
        "</criterion>\n\n"
        f"<query>{question}</query>\n\n"
        "<response>\n"
        f"{answer}\n"
        "</response>"
    )


def _execute_tasks(
    tasks: tuple[_JudgeTask, ...],
    *,
    registry=None,
    tracker: Progress,
) -> tuple[CriterionVerdict, ...]:
    if not tasks:
        return ()
    verdicts: list[CriterionVerdict] = []
    with httpx.Client(base_url=current_engine_url(), timeout=_JUDGE_TIMEOUT) as client:
        with ThreadPoolExecutor(max_workers=min(_JUDGE_CONCURRENCY, len(tasks))) as pool:
            for start in range(0, len(tasks), _JUDGE_CONCURRENCY):
                batch = tasks[start : start + _JUDGE_CONCURRENCY]
                completed = tuple(pool.map(lambda task: _execute_task(client, task), batch))
                verdicts.extend(completed)
                tracker.advance(len(completed))
                rejection = _verdict_auth_rejection(completed)
                if rejection is not None:
                    if registry is not None:
                        connections._list_for_registry(registry)
                    skipped = tuple(
                        _failed_verdict(
                            task,
                            "url4",
                            "Judge request was not scheduled because provider credentials "
                            "require reconnection.",
                            status=401,
                            code=rejection,
                        )
                        for task in tasks[start + len(batch) :]
                    )
                    verdicts.extend(skipped)
                    tracker.advance(len(skipped))
                    break
    return tuple(verdicts)


def _verdict_auth_rejection(verdicts: tuple[CriterionVerdict, ...]) -> str | None:
    return next(
        (
            verdict.failure.code
            for verdict in verdicts
            if verdict.failure is not None and verdict.failure.code in _AUTH_REJECTION_CODES
        ),
        None,
    )


def _execute_task(client: httpx.Client, task: _JudgeTask) -> CriterionVerdict:
    last_raw: str | None = None
    terminal: CriterionVerdict | None = None
    for _attempt in range(_VALIDATION_ATTEMPTS):
        response = _judge_request(client, task)
        if isinstance(response, CriterionVerdict):
            terminal = _retain_raw_response(response, last_raw)
            break
        failure = _response_failure(task, response)
        if failure is not None:
            terminal = _retain_raw_response(failure, last_raw)
            break
        last_raw = response.text
        try:
            explanation, status = _judge_output(last_raw)
        except (TypeError, ValueError):
            continue
        terminal = _successful_verdict(task, explanation, status, last_raw)
        break
    if terminal is not None:
        return terminal
    raw = last_raw if last_raw is not None and last_raw.strip() else None
    return _failed_verdict(
        task,
        "invalid_judge_output",
        "judge response did not match the required schema after three attempts",
        status=200,
        code="invalid_judge_output",
        raw_response=raw,
    )


def _judge_request(client: httpx.Client, task: _JudgeTask) -> httpx.Response | CriterionVerdict:
    try:
        return client.get(EVAL_PATH, params={"q": task.expression})
    except httpx.TimeoutException:
        return _failed_verdict(task, "timeout", "rubric judge request timed out")
    except (httpx.RequestError, httpx.InvalidURL):
        return _failed_verdict(task, "connection", "could not reach the configured URL4 engine")


def _response_failure(task: _JudgeTask, response: httpx.Response) -> CriterionVerdict | None:
    if not response.is_success:
        return _failed_response(task, response)
    content_type = response.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != "text/plain":
        return _failed_verdict(
            task,
            "protocol",
            "engine judge success must be plaintext",
            status=response.status_code,
        )
    return None


def _failed_response(task: _JudgeTask, response: httpx.Response) -> CriterionVerdict:
    error = engine_error(response)
    if error is None:
        return _failed_verdict(
            task,
            "http",
            f"URL4 engine returned HTTP {response.status_code}",
            status=response.status_code,
        )
    code, message = error
    kind: GradeFailureKind = (
        "timeout" if response.status_code == 504 or code == "timeout" else "url4"
    )
    return _failed_verdict(
        task,
        kind,
        message,
        status=response.status_code,
        code=code,
    )


def _judge_output(body: str) -> tuple[str, CriterionStatus]:
    start = body.find("{")
    if start < 0:
        raise ValueError("judge response has no JSON object")
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    try:
        payload, _end = decoder.raw_decode(body, start)
    except json.JSONDecodeError as exc:
        raise ValueError("judge response has invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("judge response must be an object")
    exact_fields(payload, {"explanation", "criterion_status"}, "judge response")
    explanation = nonblank(payload["explanation"], "judge explanation")
    status = payload["criterion_status"]
    if status not in {"MET", "UNMET"}:
        raise ValueError("judge criterion_status must be MET or UNMET")
    return explanation, status


def _successful_verdict(
    task: _JudgeTask,
    explanation: str,
    status: CriterionStatus,
    raw_response: str,
) -> CriterionVerdict:
    criterion = task.criterion
    return CriterionVerdict(
        criterion.id,
        criterion.section,
        criterion.requirement,
        criterion.weight,
        task.pass_number,
        status,
        explanation,
        raw_response,
    )


def _failed_verdict(
    task: _JudgeTask,
    kind: GradeFailureKind,
    message: str,
    *,
    status: int | None = None,
    code: str | None = None,
    raw_response: str | None = None,
) -> CriterionVerdict:
    criterion = task.criterion
    failure = GradeFailure(
        task.case_id,
        task.target,
        kind,
        message,
        criterion_id=criterion.id,
        pass_number=task.pass_number,
        status=status,
        code=code,
    )
    return CriterionVerdict(
        criterion.id,
        criterion.section,
        criterion.requirement,
        criterion.weight,
        task.pass_number,
        None,
        None,
        raw_response,
        failure,
    )


def _retain_raw_response(verdict: CriterionVerdict, raw_response: str | None) -> CriterionVerdict:
    if verdict.raw_response is not None or raw_response is None or not raw_response.strip():
        return verdict
    return CriterionVerdict(
        verdict.criterion_id,
        verdict.section,
        verdict.requirement,
        verdict.weight,
        verdict.pass_number,
        verdict.status,
        verdict.explanation,
        raw_response,
        verdict.failure,
    )


def _group_verdicts(
    tasks: tuple[_JudgeTask, ...], verdicts: tuple[CriterionVerdict, ...]
) -> dict[tuple[str, str], tuple[CriterionVerdict, ...]]:
    grouped: dict[tuple[str, str], list[CriterionVerdict]] = {}
    for task, verdict in zip(tasks, verdicts, strict=True):
        grouped.setdefault((task.case_id, task.target), []).append(verdict)
    return {key: tuple(values) for key, values in grouped.items()}


def _rubric_case(
    result: CaseResult,
    reference: _RubricReference,
    grouped: Mapping[tuple[str, str], tuple[CriterionVerdict, ...]],
) -> CaseGrades:
    if result.failure is not None:
        return CaseGrades(result.case_id, recipe=None, members=(), run_failure=result.failure)
    recipe = _rubric_grade(result.case_id, "recipe", reference, grouped)
    members = tuple(
        (
            target,
            _rubric_grade(result.case_id, target, reference, grouped),
        )
        for target, _member in result._member_items
    )
    return CaseGrades(result.case_id, recipe=recipe, members=members)


def _rubric_grade(
    case_id: str,
    target: str,
    reference: _RubricReference,
    grouped: Mapping[tuple[str, str], tuple[CriterionVerdict, ...]],
) -> Grade:
    verdicts = grouped[(case_id, target)]
    resolved = sum(verdict.status is not None for verdict in verdicts)
    coverage = resolved / len(verdicts)
    if resolved != len(verdicts):
        unresolved = len(verdicts) - resolved
        failure = GradeFailure(
            case_id,
            target,
            "incomplete_verdicts",
            f"{unresolved} of {len(verdicts)} rubric verdicts are unresolved",
        )
        return Grade(
            score=None,
            metrics={},
            coverage=coverage,
            verdicts=verdicts,
            failure=failure,
        )
    return Grade(
        score=_overall_score(verdicts),
        metrics=_rubric_metrics(verdicts, reference.section_metrics),
        coverage=1.0,
        verdicts=verdicts,
    )


def _overall_score(verdicts: tuple[CriterionVerdict, ...]) -> float:
    passes = _passes(verdicts)
    return fmean(_weighted_score(values) for values in passes.values())


def _rubric_metrics(
    verdicts: tuple[CriterionVerdict, ...], section_metrics: tuple[str, ...]
) -> dict[str, float]:
    metrics = {"pass_rate": _pass_rate(verdicts)}
    passes = _passes(verdicts)
    for section in section_metrics:
        metrics[section] = fmean(
            _weighted_score(
                tuple(value for value in values if _metric_key(value.section) == section)
            )
            for values in passes.values()
        )
    return metrics


def _passes(
    verdicts: tuple[CriterionVerdict, ...],
) -> dict[int, tuple[CriterionVerdict, ...]]:
    grouped: dict[int, list[CriterionVerdict]] = {}
    for verdict in verdicts:
        grouped.setdefault(verdict.pass_number, []).append(verdict)
    return {key: tuple(values) for key, values in grouped.items()}


def _weighted_score(verdicts: tuple[CriterionVerdict, ...]) -> float:
    denominator = sum(verdict.weight for verdict in verdicts if verdict.weight > 0)
    numerator = sum(verdict.weight for verdict in verdicts if verdict.status == "MET")
    return min(1.0, max(0.0, numerator / denominator))


def _pass_rate(verdicts: tuple[CriterionVerdict, ...]) -> float:
    passed = sum(
        (verdict.weight > 0 and verdict.status == "MET")
        or (verdict.weight < 0 and verdict.status == "UNMET")
        for verdict in verdicts
    )
    return passed / len(verdicts)


__all__ = ["grade_run"]
