from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest

import screamingface as sf
import screamingface._benchmark_execution as execution
from screamingface._engine_http import (
    engine_error,
    exact_fields,
    nonblank,
    object_value,
    require_eval_request_target,
    unique_json_object,
)
from screamingface._profile import (
    BenchmarkRecord,
    ModelRecord,
    ProviderRecord,
    ReducerRecord,
    Registry,
    StrategyRecord,
)
from screamingface.reducers import Reducer


def _benchmark(*, tools: tuple[sf.tools.Tool, ...] = ()) -> sf.Benchmark:
    return sf.Benchmark._from_engine(
        "gpqa@1",
        title="GPQA Diamond",
        cases_route="/benchmarks/gpqa/1/cases",
        grader=sf.graders.ExactChoice(),
        grader_route="/graders/exact-choice/1",
        aggregator=sf.aggregators.Mean(),
        aggregator_route="/aggregators/mean/1",
        tool_policy_route="/benchmarks/gpqa/1/tool-policy" if tools else None,
        tools=tools,
        max_tool_calls=8 if tools else None,
    )


def _recipe() -> sf.Fusion:
    return sf.Fusion(
        "duo",
        members=["codex/gpt-5.5", "gemini/2.5"],
        reducer=sf.reducers.MajorityVote(),
    )


def _registry(
    *,
    models: tuple[ModelRecord, ...] | None = None,
    reducers: tuple[ReducerRecord, ...] | None = None,
    benchmarks: tuple[BenchmarkRecord, ...] | None = None,
) -> Registry:
    benchmark = BenchmarkRecord(
        "gpqa@1",
        "GPQA Diamond",
        "/benchmarks/gpqa/1/cases",
        StrategyRecord("exact_choice", "/graders/exact-choice/1"),
        StrategyRecord("mean", "/aggregators/mean/1"),
        (),
        None,
        None,
    )
    return Registry(
        models=models
        or (
            ModelRecord("codex/gpt-5.5", (), "codex"),
            ModelRecord("gemini/2.5", (), "gemini"),
        ),
        reducers=reducers
        if reducers is not None
        else (ReducerRecord("majority_vote", "/reducers/majority-vote/1"),),
        response_schemas=(
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ),
        max_request_target_bytes=131_072,
        providers=(
            ProviderRecord("codex", "Codex", ("oauth",)),
            ProviderRecord("gemini", "Gemini", ("api_key",)),
            ProviderRecord("tavily", "Tavily", ("api_key",)),
        ),
        benchmarks=(benchmark,) if benchmarks is None else benchmarks,
    )


def _payload() -> dict[str, object]:
    return {
        "schema": "screamingface.report.v1",
        "benchmark_id": "gpqa@1",
        "case_ids": ["q1"],
        "n_cases": 1,
        "n_scored": 1,
        "coverage": 1.0,
        "score": 1.0,
        "baseline": 1.0,
        "gain": 0.0,
        "members": {
            "member_1": {"model": "codex/gpt-5.5", "score": 1.0, "metrics": {}},
            "member_2": {"model": "gemini/2.5", "score": 0.0, "metrics": {}},
        },
        "metrics": {},
        "failures": [],
        "complete": True,
    }


def _response(payload: object, *, content_type: str = "text/plain") -> httpx.Response:
    return httpx.Response(
        200,
        text=json.dumps(payload),
        headers={"content-type": content_type},
    )


def test_evaluate_rejects_wrong_public_value_types() -> None:
    with pytest.raises(TypeError, match="sf.Benchmark"):
        execution.evaluate_benchmark(cast(Any, "gpqa@1"), _recipe(), first=1)
    with pytest.raises(TypeError, match="sf.Model or sf.Fusion"):
        execution.evaluate_benchmark(_benchmark(), cast(Any, "model"), first=1)


def test_evaluate_reports_preflight_errors_to_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(execution, "load_registry", lambda: _registry(benchmarks=()))
    with pytest.raises(sf.UnknownBenchmarkError):
        execution.evaluate_benchmark(_benchmark(), _recipe(), first=1, progress=False)


def test_evaluate_returns_a_partial_engine_report(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload()
    payload.update(
        case_ids=["q1", "row_2"],
        n_cases=2,
        n_scored=1,
        coverage=0.5,
        failures=[
            {
                "case_id": "row_2",
                "kind": "url4",
                "message": "resolution failed",
                "status": 502,
                "code": "resolution_failed",
            }
        ],
        complete=False,
    )
    monkeypatch.setattr(execution, "load_registry", _registry)
    monkeypatch.setattr(execution, "require_connections", lambda *_args: None)
    monkeypatch.setattr(execution, "_request", lambda _expression: _response(payload))

    report = execution.evaluate_benchmark(_benchmark(), _recipe(), first=2, progress=False)

    assert report.n_scored == 1
    assert not report.complete


@pytest.mark.parametrize("first", [0, -1, True, 1.5])
def test_evaluate_rejects_invalid_slices(first: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        execution.evaluate_benchmark(_benchmark(), _recipe(), first=cast(Any, first))


def test_request_maps_transport_and_engine_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("late")

    monkeypatch.setattr(execution.httpx, "get", timeout)
    with pytest.raises(sf.EngineConnectionError, match="timed out"):
        execution._request("expression")

    def unavailable(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(execution.httpx, "get", unavailable)
    with pytest.raises(sf.EngineConnectionError, match="could not reach"):
        execution._request("expression")

    monkeypatch.setattr(execution.httpx, "get", lambda *_args, **_kwargs: httpx.Response(502))
    with pytest.raises(sf.EngineProtocolError, match="HTTP 502 for benchmark"):
        execution._request("expression")

    error = {"error": {"code": "provider_unavailable", "message": "provider is unavailable"}}
    monkeypatch.setattr(
        execution.httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(502, text=json.dumps(error)),
    )
    with pytest.raises(sf.EngineProtocolError, match="provider_unavailable"):
        execution._request("expression")

    monkeypatch.setattr(
        execution.httpx,
        "get",
        lambda *_args, **_kwargs: _response(_payload(), content_type="application/json"),
    )
    with pytest.raises(sf.EngineProtocolError, match="must be plaintext"):
        execution._request("expression")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(schema="wrong"), "expected schema"),
        (lambda value: value.update(benchmark_id="other@1"), "benchmark ID"),
        (lambda value: value.update(case_ids="q1"), "case_ids must be a list"),
        (lambda value: value.update(case_ids=["q1", "q1"]), "must be unique"),
        (lambda value: value.update(n_cases=2), "length must equal"),
        (lambda value: value.update(n_scored=-1), "integer >= 0"),
        (lambda value: value.update(members={}), "member slots"),
        (
            lambda value: cast(dict[str, Any], value["members"])["member_1"].update(model="wrong"),
            "model does not match",
        ),
        (lambda value: value.update(metrics=[]), "metrics must be an object"),
        (lambda value: value.update(failures={}), "failures must be a list"),
        (lambda value: value.update(complete=False), "complete must equal"),
        (lambda value: value.update(coverage=2.0), "between 0 and 1"),
        (lambda value: value.update(score="one"), "must be numeric"),
        (lambda value: value.update(extra=True), "unknown field"),
    ],
)
def test_report_decoder_rejects_protocol_drift(mutate, message: str) -> None:
    payload = _payload()
    mutate(payload)
    with pytest.raises(sf.EngineProtocolError, match=message):
        execution._report(_response(payload), _benchmark(), _recipe(), "expression")


def test_report_decoder_accepts_typed_partial_failures() -> None:
    payload = _payload()
    payload.update(
        n_cases=2,
        case_ids=["q1", "row_2"],
        n_scored=1,
        coverage=0.5,
        failures=[
            {
                "case_id": "row_2",
                "kind": "url4",
                "message": "resolution failed",
                "status": 502,
                "code": "resolution_failed",
            }
        ],
        complete=False,
    )

    report = execution._report(_response(payload), _benchmark(), _recipe(), "expression")

    assert report.failures == (
        sf.EvaluationFailure(
            "row_2", "url4", "resolution failed", status=502, code="resolution_failed"
        ),
    )
    assert report.url4 == "expression"


def test_report_failure_fields_are_strict() -> None:
    payload = _payload()
    payload.update(
        failures=[
            {
                "case_id": "q1",
                "kind": "unknown",
                "message": "failed",
                "status": None,
                "code": None,
            }
        ],
        complete=False,
    )
    with pytest.raises(sf.EngineProtocolError, match="unknown report failure kind"):
        execution._report(_response(payload), _benchmark(), _recipe(), "expression")

    cast(list[dict[str, object]], payload["failures"])[0]["kind"] = "http"
    cast(list[dict[str, object]], payload["failures"])[0]["status"] = 99
    with pytest.raises(sf.EngineProtocolError, match="integer >= 100"):
        execution._report(_response(payload), _benchmark(), _recipe(), "expression")


def test_manifest_and_capability_preflight_are_strict() -> None:
    benchmark = _benchmark()
    recipe = _recipe()
    with pytest.raises(sf.UnknownBenchmarkError):
        execution._manifest(benchmark, _registry(benchmarks=()))

    changed = BenchmarkRecord(
        "gpqa@1",
        "Changed",
        "/benchmarks/gpqa/1/cases",
        StrategyRecord("exact_choice", "/graders/exact-choice/1"),
        StrategyRecord("mean", "/aggregators/mean/1"),
        (),
        None,
        None,
    )
    with pytest.raises(sf.EngineProtocolError, match="no longer matches"):
        execution._manifest(benchmark, _registry(benchmarks=(changed,)))

    with pytest.raises(sf.UnknownModelError):
        execution._preflight(recipe, benchmark, _registry(models=(ModelRecord("x", (), "codex"),)))

    tool_benchmark = _benchmark(tools=(sf.tools.WebSearch(),))
    with pytest.raises(sf.UnsupportedToolError, match="web_search"):
        execution._preflight(recipe, tool_benchmark, _registry())

    with pytest.raises(sf.UnsupportedReducerError):
        execution._preflight(recipe, benchmark, _registry(reducers=()))

    class Unsupported(Reducer):
        kind = "unsupported"

    unsupported = sf.Fusion(
        "unsupported",
        members=["codex/gpt-5.5"],
        reducer=Unsupported(),
    )
    with pytest.raises(sf.UnsupportedReducerError, match="Unsupported"):
        execution._preflight(unsupported, benchmark, _registry())


def test_small_execution_helpers_are_explicit() -> None:
    assert execution._first(None) is None
    assert execution._optional_integer(None, "status") is None
    with pytest.raises(ValueError, match="no engine cases route"):
        execution._required_route(None, "cases")


def test_shared_http_helpers_reject_ambiguous_data() -> None:
    with pytest.raises(sf.EngineRequestTooLargeError):
        require_eval_request_target("a b", 1, "test")
    assert engine_error(httpx.Response(500, text="not json")) is None
    assert unique_json_object('{"a":1}') == {"a": 1}
    with pytest.raises(ValueError, match="duplicate"):
        unique_json_object('{"a":1,"a":2}')
    with pytest.raises(TypeError, match="JSON object"):
        unique_json_object("[]")
    with pytest.raises(ValueError, match="missing"):
        exact_fields({}, {"required"}, "value")
    with pytest.raises(ValueError, match="unknown"):
        exact_fields({"extra": True}, set(), "value")
    with pytest.raises(TypeError, match="object"):
        object_value([], "value")
    with pytest.raises(ValueError, match="non-blank"):
        nonblank(" ", "value")
