"""Preflight and bounded synchronous execution for Fusion.run()."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from screamingface._compiler import MAJORITY_VOTE_ROUTE, compile_fusion
from screamingface._config import current_engine_url
from screamingface._profile import (
    FUSION_RESULT_SCHEMA,
    Registry,
    load_benchmark_from_registry,
    load_registry,
)
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import (
    InvalidBenchmarkError,
    UnknownModelError,
    UnsupportedReducerError,
    UnsupportedToolError,
)
from screamingface.fusion import Fusion
from screamingface.graders import ExactChoice, Rubric
from screamingface.reducers import MajorityVote, Model
from screamingface.run import CaseResult, FailureKind, MemberResult, Run, RunFailure

_CASE_CONCURRENCY = 4
_RUN_TIMEOUT = 130.0


def run_fusion(
    fusion: Fusion,
    benchmark: str | Benchmark,
    *,
    first: int | None,
) -> Run:
    """Preflight, execute every selected case, and preserve canonical order."""

    limit = _first(first)
    if not isinstance(benchmark, (str, Benchmark)):
        raise TypeError("benchmark must be a benchmark ID or sf.Benchmark")
    recipe = compile_fusion(fusion)
    registry = load_registry()
    resolved = (
        load_benchmark_from_registry(benchmark, registry)
        if isinstance(benchmark, str)
        else benchmark
    )
    cases = resolved._materialize_cases()
    selected = cases if limit is None else cases[:limit]
    _references(selected, resolved)
    _preflight(fusion, resolved, registry)

    expressions = tuple((case, compile_fusion(fusion, question=case.input)) for case in selected)
    base_url = current_engine_url()
    with httpx.Client(base_url=base_url, timeout=_RUN_TIMEOUT) as client:
        with ThreadPoolExecutor(max_workers=min(_CASE_CONCURRENCY, len(expressions))) as pool:
            results = tuple(
                pool.map(
                    lambda value: _execute_case(client, fusion, *value),
                    expressions,
                )
            )
    return Run(benchmark=resolved, fusion_url4=recipe, results=results)


def _execute_case(
    client: httpx.Client,
    fusion: Fusion,
    case: Case,
    expression: str,
) -> CaseResult:
    try:
        response = client.get("/v1", params={"q": expression})
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
    error = _engine_error(response)
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
        payload = _unique_json_object(response.text)
        members, answer = _fusion_result(payload, fusion)
    except (KeyError, TypeError, ValueError) as exc:
        return _protocol(case_id, f"invalid fusion result: {exc}", response.status_code)
    return CaseResult(case_id, members=members, answer=answer)


def _fusion_result(
    payload: dict[str, object], fusion: Fusion
) -> tuple[tuple[tuple[str, MemberResult], ...], str]:
    _exact_fields(payload, {"schema", "members", "answer"}, "fusion result")
    if payload["schema"] != FUSION_RESULT_SCHEMA:
        raise ValueError(f"expected schema {FUSION_RESULT_SCHEMA!r}")
    wire_members = _object(payload["members"], "fusion members")
    expected_ids = tuple(member.id for member in fusion._members)
    if set(wire_members) != set(expected_ids):
        raise ValueError("member slots do not match the Fusion")

    members: list[tuple[str, MemberResult]] = []
    for expected in fusion._members:
        item = _object(wire_members[expected.id], f"member {expected.id!r}")
        _exact_fields(item, {"model", "answer"}, f"member {expected.id!r}")
        if item["model"] != expected.model:
            raise ValueError(f"member {expected.id!r} model does not match the Fusion")
        members.append(
            (
                expected.id,
                MemberResult(
                    model=expected.model,
                    answer=_nonblank(item["answer"], f"member {expected.id!r} answer"),
                ),
            )
        )
    return tuple(members), _nonblank(payload["answer"], "fusion answer")


def _engine_error(response: httpx.Response) -> tuple[str, str] | None:
    try:
        payload = _unique_json_object(response.text)
        _exact_fields(payload, {"error"}, "engine error")
        error = _object(payload["error"], "engine error")
        _exact_fields(error, {"code", "message"}, "engine error")
        return _nonblank(error["code"], "engine error code"), _nonblank(
            error["message"], "engine error message"
        )
    except (KeyError, TypeError, ValueError):
        return None


def _unique_json_object(body: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        payload = json.loads(body, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise ValueError("response is not JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("expected a JSON object")
    return payload


def _preflight(fusion: Fusion, benchmark: Benchmark, registry: Registry) -> None:
    models = {record.id: record for record in registry.models}
    for model in _required_models(fusion, benchmark):
        if model not in models:
            raise UnknownModelError(f"unknown model {model!r}")
    for member in fusion._members:
        supported = set(models[member.model].supported_tools)
        missing = set(benchmark.tools) - supported
        if missing:
            raise UnsupportedToolError(
                f"model {member.model!r} does not support benchmark tool(s): {sorted(missing)}"
            )
    _reducer(fusion, registry)


def _required_models(fusion: Fusion, benchmark: Benchmark) -> tuple[str, ...]:
    models = list(fusion.model_ids)
    if isinstance(fusion.reducer, Model):
        models.append(fusion.reducer.model)
    if isinstance(benchmark.grader, Rubric):
        models.append(benchmark.grader.model)
    return tuple(models)


def _reducer(fusion: Fusion, registry: Registry) -> None:
    if isinstance(fusion.reducer, MajorityVote):
        reducer = next(
            (record for record in registry.reducers if record.id == fusion.reducer.kind),
            None,
        )
        if reducer is None or reducer.route != MAJORITY_VOTE_ROUTE:
            raise UnsupportedReducerError(f"engine does not advertise {MAJORITY_VOTE_ROUTE!r}")
    elif not isinstance(fusion.reducer, Model):
        raise UnsupportedReducerError(f"unsupported reducer {type(fusion.reducer).__name__!r}")


def _references(cases: Sequence[Case], benchmark: Benchmark) -> None:
    for case in cases:
        reference = case.reference
        if reference is None:
            raise InvalidBenchmarkError(f"case {case.id!r} has no grading reference")
        if isinstance(benchmark.grader, ExactChoice) and (
            not isinstance(reference, str) or not reference.strip()
        ):
            raise InvalidBenchmarkError(
                f"case {case.id!r} exact-choice reference must be a non-empty string"
            )


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


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_fields(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise ValueError(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


__all__ = ["run_fusion"]
