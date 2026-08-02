from __future__ import annotations

import asyncio
import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from url4 import RelExpr, Text, iterate, render, src

import screamingface as sf
from screamingface._core.ports import _RunOutcome
from screamingface._engine.benchmark import BenchmarkResources, _success
from screamingface._evaluation.benchmark import _decode_benchmark_resource
from screamingface._evaluation.candidate import _url4_text, compile_candidate
from screamingface._evaluation.compilation import compile_evaluation
from screamingface._evaluation.model import Candidate
from screamingface._evaluation.results import _candidate_result


def _draco_url4() -> str:
    judge = RelExpr(
        path="/provider/judge",
        context="answer: $answer; criterion: $criterion",
        intent=Text("Return JSON."),
        params=(("temperature", "0.2"),),
    )
    criteria = iterate(
        "/draco/criteria/$item.id",
        body=(
            src("$item.requirement", name="criterion", weight=0.0),
            src(judge, name="verdict", weight=1.0),
        ),
        intent=Text("criterion"),
    )
    reducer = render(
        RelExpr(
            path="/benchmark",
            context="aggregate",
            intent=Text("Aggregate Candidate case grades."),
        )
    )
    return render(
        iterate(
            "/draco/cases",
            body=(
                src("$item.id", name="case_id", weight=0.0),
                src("$item.input", name="question", weight=0.0),
                src(
                    RelExpr(
                        path="/candidate",
                        context="$question",
                        intent=Text("$candidate"),
                    ),
                    name="answer",
                    weight=0.0,
                ),
                src(criteria, name="graded", weight=1.0),
            ),
            intent=Text("case"),
            reduce=reducer,
            on_error="collect",
        )
    )


BENCHMARK: dict[str, object] = {
    "schema": "screamingface.benchmark.v1",
    "object": "benchmark",
    "id": "draco-lite",
    "title": "DRACO Lite",
    "description": "Research-quality rubric evaluation.",
    "case_count": 1,
    "total_case_count": 1,
    "metrics": {"primary": "normalized_score", "direction": "maximize"},
    "capabilities": {
        "candidate": ["web_search", "web_fetch"],
        "runtime": [],
    },
    "required_models": ["provider/judge"],
    "candidate_invocations": 1,
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
                    "benchmark_id": "draco-lite",
                    "case_count": 1,
                    "score": 0.7,
                    "metrics": {
                        "normalized_score": 0.7,
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
    if request.url.path in {
        "/v1/benchmarks/default",
        "/v1/benchmarks/draco-lite",
    }:
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


def test_client_evaluates_the_complete_draco_lite_vertical_slice() -> None:
    client, transport = _client()

    with client:
        report = client.evaluate(
            sf.Model("anthropic/claude-haiku-4-5", name="haiku"),
            limit=1,
        )

    result = report.candidates.only
    assert report.benchmark.id == "draco-lite"
    assert result.models == ("anthropic/claude-haiku-4-5",)
    assert tuple(operation.kind for operation in result.operations) == ("model",)
    assert result.url4.count("/candidate") == 1
    assert result.url4.count("/benchmark") == 1
    assert "/draco/cases" in result.url4
    assert "/draco/criteria/$item.id" in result.url4
    assert "/provider/judge" in result.url4
    assert "/benchmark(aggregate)" in result.url4
    assert "temperature=0.2" in result.url4
    assert "reasoning=low" in result.url4
    assert "max_output_tokens=4096" in result.url4
    assert "\n" not in result.url4
    assert result.name == "haiku"
    assert result.score == 0.7
    assert result.metrics == {"normalized_score": 0.7, "coverage": 1.0}
    assert result.usage.input_tokens == 120
    assert result.duration_ms == 2000
    assert transport.closed is True


@pytest.mark.asyncio
async def test_async_client_evaluates_the_same_draco_lite_contract() -> None:
    transport = _AsyncFakeTransport()
    client = sf.AsyncClient(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(_engine),
        run_transport=transport,
    )

    async with client:
        report = await client.evaluate(
            sf.Model("anthropic/claude-haiku-4-5", name="haiku"),
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
        report = client.evaluate(candidates, limit=1)

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
        report = await client.evaluate(candidates, limit=1)

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
        report = client.evaluate(fusion, benchmark="draco-lite", limit=1)

    result = report.candidates.only
    assert result.kind == "fusion"
    assert result.models == (
        "provider/first",
        "provider/second",
        "anthropic/claude-haiku-4-5",
    )
    assert tuple(member.name for member in result.members) == ("first", "second")
    assert tuple(operation.kind for operation in result.operations) == (
        "model",
        "model",
        "synthesis",
    )
    assert "/provider/first" in result.url4
    assert "/provider/second" in result.url4
    assert "/anthropic/claude-haiku-4-5" in result.url4
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
        report = client.evaluate(fusion, benchmark="draco-lite", limit=1)

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
            benchmark="draco-lite",
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
            benchmark="draco-lite",
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
            BenchmarkResources(http).load("draco-lite", 1)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="{")),
    ) as http:
        with pytest.raises(sf.PlanningError, match="must be JSON"):
            BenchmarkResources(http).load("draco-lite", 1)


def test_benchmark_decoder_rejects_required_field_boundaries() -> None:
    bad_capabilities = deepcopy(BENCHMARK)
    bad_capabilities["capabilities"] = []
    bad_count = deepcopy(BENCHMARK)
    bad_count["case_count"] = 0
    bad_direction = deepcopy(BENCHMARK)
    assert isinstance(bad_direction["metrics"], dict)
    bad_direction["metrics"]["direction"] = "sideways"
    bad_invocations = deepcopy(BENCHMARK)
    bad_invocations["candidate_invocations"] = 0

    invalid_values: tuple[object, ...] = (
        [],
        {},
        bad_capabilities,
        bad_count,
        bad_direction,
        bad_invocations,
    )
    for value in invalid_values:
        with pytest.raises(sf.PlanningError):
            _decode_benchmark_resource(
                value,
                requested_id="draco-lite",
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
        requested_id="draco-lite",
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
        "benchmark_id": "draco-lite",
        "case_count": 1,
        "score": 0.7,
        "metrics": {"normalized_score": 0.7},
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
        {**valid, "metrics": {"normalized_score": True}},
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
