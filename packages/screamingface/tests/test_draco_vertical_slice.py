from __future__ import annotations

import asyncio
import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from url4 import RelExpr, Text, expr, iterate, render, src

import screamingface as sf
from screamingface._core.ports import _RunOutcome
from screamingface._engine.benchmark import BenchmarkResources, _success
from screamingface._evaluation.benchmark import _decode_benchmark_resource
from screamingface._evaluation.candidate import _url4_text, compile_candidate
from screamingface._evaluation.compilation import compile_evaluation
from screamingface._evaluation.model import Candidate
from screamingface._evaluation.results import _candidate_result

_ROUTE_PREFIX = "/benchmarks/draco/fixture-revision"


def _draco_url4() -> str:
    judge_calls = tuple(
        src(
            RelExpr(
                path=f"{_ROUTE_PREFIX}/criterion-verdict",
                context=render(
                    RelExpr(
                        path="/provider/judge",
                        context=(
                            "<criterion_type>$item.criterion_type</criterion_type>"
                            "<criterion>$item.criterion</criterion>"
                            "<query>$item.question</query>"
                            "<response>$item.answer</response>"
                        ),
                        intent=Text("Return JSON."),
                        params=(("temperature", "0.2"),),
                    ),
                    check=False,
                ),
                intent=Text("$item.criterion_id"),
            ),
            name=f"verdict_{run}",
            weight=1.0,
        )
        for run in range(1, 6)
    )
    criteria = iterate(
        RelExpr(
            path=f"{_ROUTE_PREFIX}/tasks",
            context=render(
                RelExpr(path="/candidate", context="$item.input", intent=Text("$candidate"))
            ),
            intent=Text("$item.id"),
        ),
        body=(
            src("$item.criterion_id", name="criterion_id", weight=0.0),
            src("$item.criterion", name="criterion", weight=0.0),
            src("$item.criterion_type", name="criterion_type", weight=0.0),
            *judge_calls,
        ),
        intent=Text("criterion"),
    )
    rows = iterate(
        f"{_ROUTE_PREFIX}/cases",
        body=(
            src(
                expr(src(criteria, name="criteria", weight=0.0), intent=Text("$criteria")),
                name="graded",
                weight=1.0,
            ),
        ),
        intent=Text("case"),
        on_error="collect",
    )
    return render(
        expr(
            src(
                expr(src(rows, name="selected_rows", weight=0.0), intent=Text("$selected_rows")),
                name="rows",
                weight=0.0,
            ),
            src(
                RelExpr(
                    path=f"{_ROUTE_PREFIX}/aggregate",
                    context="$rows",
                    intent=Text("aggregate"),
                ),
                name="result",
                weight=0.0,
            ),
            intent=Text("$result"),
        )
    )


BENCHMARK: dict[str, object] = {
    "schema": "screamingface.benchmark.v1",
    "id": "draco",
    "revision": "fixture-revision",
    "case_count": 1,
    "total_case_count": 1,
    "required_models": ["provider/judge"],
    "url4": _draco_url4(),
}


class _FakeTransport:
    def __init__(self) -> None:
        self.closed = False
        self.calls: list[str] = []

    def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        assert on_event is None
        self.calls.append(candidate.name)
        return _RunOutcome(
            run_id=f"run_{candidate.name}",
            started_at=datetime(2026, 7, 28, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 7, 28, 10, 0, 2, tzinfo=UTC),
            result_body=json.dumps(
                {
                    "schema": "screamingface.candidate-result.v1",
                    "benchmark_id": "draco",
                    "case_count": 1,
                    "score": 0.7,
                    "metrics": {
                        "coverage": 1.0,
                    },
                    "failures": [],
                }
            ),
            media_type="application/json",
            root_usage=sf.Usage(
                input_tokens=120,
                output_tokens=30,
                cost_usd="0.04",
            ),
        )

    def close(self) -> None:
        self.closed = True


class _AsyncFakeTransport:
    def __init__(self) -> None:
        self.closed = False

    async def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        return _FakeTransport().run(candidate, on_event)

    async def close(self) -> None:
        self.closed = True


class _ConcurrentFakeTransport(_FakeTransport):
    def __init__(self, expected: int) -> None:
        super().__init__()
        self._barrier = threading.Barrier(expected)
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self._barrier.wait(timeout=1)
            return super().run(candidate, on_event)
        finally:
            with self._lock:
                self.active -= 1


class _AsyncConcurrentFakeTransport(_AsyncFakeTransport):
    def __init__(self, expected: int) -> None:
        super().__init__()
        self._expected = expected
        self._ready = asyncio.Event()
        self.active = 0
        self.max_active = 0

    async def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.active == self._expected:
            self._ready.set()
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=1)
            return await super().run(candidate, on_event)
        finally:
            self.active -= 1


def _engine(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        models = (
            "anthropic/claude-haiku-4-5",
            "openrouter/anthropic/claude-haiku-4.5",
            "provider/first",
            "provider/second",
            "provider/synthesizer",
            "provider/judge",
        )
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": model, "object": "model", "owned_by": model.split("/", 1)[0]}
                    for model in models
                ],
            },
        )
    if request.url.path == "/v1/benchmarks/draco":
        return httpx.Response(200, json=BENCHMARK)
    return httpx.Response(404)


def _client() -> tuple[sf.Client, _FakeTransport]:
    transport = _FakeTransport()
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(_engine),
        run_transport=transport,
    )
    return client, transport


def test_client_evaluates_the_complete_draco_vertical_slice() -> None:
    client, transport = _client()

    with client:
        report = client.evaluate(
            sf.Model("anthropic/claude-haiku-4-5", name="haiku"),
            benchmark="draco",
            limit=1,
        )

    result = report.candidates.only
    assert report.benchmark.id == "draco"
    assert result.models == ("anthropic/claude-haiku-4-5",)
    assert tuple(operation.kind for operation in result.operations) == ("model",)
    assert result.url4.count("/candidate") == 1
    assert result.url4.count("/provider/judge") == 5
    assert result.url4.count(f"{_ROUTE_PREFIX}/criterion-verdict") == 5
    assert f"{_ROUTE_PREFIX}/cases" in result.url4
    assert f"{_ROUTE_PREFIX}/tasks" in result.url4
    assert "/draco/criteria" not in result.url4
    assert "/provider/judge" in result.url4
    assert f"{_ROUTE_PREFIX}/aggregate" in result.url4
    assert "temperature=0.2" in result.url4
    assert "reasoning=" not in result.url4
    assert "max_tokens=4096" in result.url4
    assert "\n" not in result.url4
    assert result.name == "haiku"
    assert result.score == 0.7
    assert result.metrics == {"coverage": 1.0}
    assert result.usage.input_tokens == 120
    assert result.duration_ms == 2000
    assert transport.closed is True


@pytest.mark.asyncio
async def test_async_client_evaluates_the_same_draco_contract() -> None:
    transport = _AsyncFakeTransport()
    client = sf.AsyncClient(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(_engine),
        run_transport=transport,
    )

    async with client:
        report = await client.evaluate(
            sf.Model("anthropic/claude-haiku-4-5", name="haiku"),
            benchmark="draco",
            limit=1,
        )

    assert report.candidates.only.name == "haiku"
    assert report.candidates.only.score == 0.7
    assert transport.closed is True


def test_client_runs_candidates_concurrently_and_preserves_declared_order() -> None:
    transport = _ConcurrentFakeTransport(expected=3)
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(_engine),
        run_transport=transport,
    )
    candidates = [
        sf.Model("anthropic/claude-haiku-4-5", name=f"sample-{index}") for index in range(3)
    ]

    with client:
        report = client.evaluate(candidates, benchmark="draco", limit=1)

    assert transport.max_active == 3
    assert tuple(result.name for result in report.candidates) == (
        "sample-0",
        "sample-1",
        "sample-2",
    )


@pytest.mark.asyncio
async def test_async_client_runs_candidates_concurrently_and_preserves_order() -> None:
    transport = _AsyncConcurrentFakeTransport(expected=3)
    client = sf.AsyncClient(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(_engine),
        run_transport=transport,
    )
    candidates = [
        sf.Model("anthropic/claude-haiku-4-5", name=f"sample-{index}") for index in range(3)
    ]

    async with client:
        report = await client.evaluate(candidates, benchmark="draco", limit=1)

    assert transport.max_active == 3
    assert tuple(result.name for result in report.candidates) == (
        "sample-0",
        "sample-1",
        "sample-2",
    )


def test_client_compiles_and_evaluates_a_fusion_as_one_candidate_url4() -> None:
    client, _transport = _client()
    fusion = sf.Fusion(
        [
            sf.Model("provider/first", name="first"),
            sf.Model("provider/second", name="second"),
        ],
        name="research-pair",
    )

    with client:
        report = client.evaluate(fusion, benchmark="draco", limit=1)

    result = report.candidates.only
    assert result.kind == "fusion"
    assert result.models == (
        "provider/first",
        "provider/second",
        "openrouter/anthropic/claude-haiku-4.5",
    )
    assert tuple(member.name for member in result.members) == ("first", "second")
    assert tuple(operation.kind for operation in result.operations) == (
        "model",
        "model",
        "synthesis",
    )
    assert "/provider/first" in result.url4
    assert "/provider/second" in result.url4
    assert "/openrouter/anthropic/claude-haiku-4.5" in result.url4
    assert "Synthesize the strongest supported answer" in result.url4


def test_fusion_member_names_do_not_leak_into_url4_struct_keys() -> None:
    client, _transport = _client()
    fusion = sf.Fusion(
        [
            sf.Model("provider/first", name="gemini-pro"),
            sf.Model("provider/second", name="claude-opus-4.8"),
        ],
        name="named-pair",
    )

    with client:
        report = client.evaluate(fusion, benchmark="draco", limit=1)

    result = report.candidates.only
    candidate_url4 = compile_candidate(fusion).url4
    assert tuple(member.name for member in result.members) == (
        "gemini-pro",
        "claude-opus-4.8",
    )
    assert "gemini-pro:" not in candidate_url4
    assert "claude-opus-4.8:" not in candidate_url4
    assert "member_1: {name: 'gemini-pro', answer: '$model_1'}" in candidate_url4
    assert "member_2: {name: 'claude-opus-4.8', answer: '$model_2'}" in candidate_url4


def test_compiler_deduplicates_equivalent_model_values_by_content() -> None:
    left = sf.Fusion(
        [sf.Model("provider/first"), sf.Model("provider/second")],
        name="left",
    )
    right = sf.Fusion(
        [sf.Model("provider/first"), sf.Model("provider/judge")],
        name="right",
    )
    client, _transport = _client()

    with client:
        report = client.evaluate(
            sf.Fusion([left, right], name="outer"),
            benchmark="draco",
            limit=1,
        )

    result = report.candidates.only
    assert tuple(operation.kind for operation in result.operations).count("model") == 3
    assert result.url4.count("/provider/first") == 1


def test_explicit_sample_names_prevent_model_content_deduplication() -> None:
    left = sf.Fusion(
        [
            sf.Model("provider/first", name="sample-1"),
            sf.Model("provider/second"),
        ],
        name="left",
    )
    right = sf.Fusion(
        [
            sf.Model("provider/first", name="sample-2"),
            sf.Model("provider/judge"),
        ],
        name="right",
    )
    client, _transport = _client()

    with client:
        report = client.evaluate(
            sf.Fusion([left, right], name="outer"),
            benchmark="draco",
            limit=1,
        )

    result = report.candidates.only
    assert tuple(operation.kind for operation in result.operations).count("model") == 4
    assert result.url4.count("/provider/first") == 2


def test_benchmark_reader_rejects_transport_and_integrity_failures() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(unreachable),
    ) as http:
        with pytest.raises(sf.EngineUnavailableError, match="Could not reach"):
            BenchmarkResources(http).load("draco", 1)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="{")),
    ) as http:
        with pytest.raises(sf.PlanningError, match="must be JSON"):
            BenchmarkResources(http).load("draco", 1)


def test_benchmark_decoder_rejects_required_field_boundaries() -> None:
    bad_revision = deepcopy(BENCHMARK)
    bad_revision["revision"] = ""
    bad_count = deepcopy(BENCHMARK)
    bad_count["case_count"] = 0
    bad_required_models = deepcopy(BENCHMARK)
    bad_required_models["required_models"] = "provider/judge"

    invalid_values: tuple[object, ...] = (
        [],
        {},
        bad_revision,
        bad_count,
        bad_required_models,
    )
    for value in invalid_values:
        with pytest.raises(sf.PlanningError):
            _decode_benchmark_resource(
                value,
                requested_id="draco",
                requested_limit=1,
            )


def test_benchmark_http_errors_are_typed() -> None:
    with pytest.raises(sf.PlanningError, match="not installed") as caught:
        _success(httpx.Response(404))

    assert caught.value.code == "unknown_benchmark"
    assert caught.value.status == 404


def test_compiler_normalizes_url4_parameters_and_rejects_control_characters() -> None:
    assert _url4_text("line 1\r\nline 2\t$value") == "line 1\u2028line 2 $$value"
    with pytest.raises(ValueError, match="U\\+0001"):
        _url4_text("bad\x01text")


def test_candidate_result_decoder_rejects_contract_drift() -> None:
    resource = _decode_benchmark_resource(
        BENCHMARK,
        requested_id="draco",
        requested_limit=1,
    )
    evaluation = compile_evaluation(
        (sf.Model("anthropic/claude-haiku-4-5"),),
        resource,
        1,
    )
    candidate = evaluation.candidates.only
    valid: dict[str, Any] = {
        "schema": "screamingface.candidate-result.v1",
        "benchmark_id": "draco",
        "case_count": 1,
        "score": 0.7,
        "metrics": {"coverage": 1.0},
        "failures": [],
    }

    invalid_payloads: tuple[object, ...] = (
        "not-json",
        [],
        {**valid, "schema": "wrong"},
        {**valid, "benchmark_id": "wrong"},
        {**valid, "case_count": 2},
        {**valid, "score": "high"},
        {**valid, "metrics": []},
        {**valid, "metrics": {"coverage": True}},
        {**valid, "failures": [{"code": "failed"}]},
    )
    for payload in invalid_payloads:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        outcome = _RunOutcome(
            run_id="run_invalid",
            started_at=datetime(2026, 7, 28, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 7, 28, 10, 0, 1, tzinfo=UTC),
            result_body=body,
            media_type="application/json",
            root_usage=None,
        )
        with pytest.raises(sf.ExecutionError):
            _candidate_result(evaluation, candidate, outcome)


def test_candidate_result_warns_when_a_benchmark_declares_low_coverage() -> None:
    resource = _decode_benchmark_resource(
        BENCHMARK,
        requested_id="draco",
        requested_limit=1,
    )
    evaluation = compile_evaluation(
        (sf.Model("anthropic/claude-haiku-4-5"),),
        resource,
        1,
    )
    candidate = evaluation.candidates.only
    outcome = _RunOutcome(
        run_id="run_partial",
        started_at=datetime(2026, 7, 28, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 7, 28, 10, 0, 1, tzinfo=UTC),
        result_body=json.dumps(
            {
                "schema": "screamingface.candidate-result.v1",
                "benchmark_id": "draco",
                "case_count": 1,
                "score": 0.65,
                "metrics": {
                    "coverage": 0.761,
                    "coverage_target": 0.95,
                    "verdicts_expected": 159,
                    "verdicts_accepted": 121,
                },
                "failures": [],
            }
        ),
        media_type="application/json",
        root_usage=None,
    )

    with pytest.warns(
        sf.CoverageWarning,
        match="121/159 verdicts accepted.*76.1%.*target 95.0%",
    ):
        result = _candidate_result(evaluation, candidate, outcome)

    assert result.metrics["coverage"] == 0.761
