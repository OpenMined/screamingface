from __future__ import annotations

import asyncio
import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
import yaml

import screamingface as sf
from screamingface._benchmark_manifest import (
    _decode_manifest,
    _select_benchmark,
    _success,
    load_manifest,
)
from screamingface._compiler import _url4_text
from screamingface._evaluation import Candidate
from screamingface._ports import _RunOutcome
from screamingface._result_decoder import _candidate_result
from screamingface.client import _compile_sync

MANIFEST = b"""\
id: draco-lite
title: DRACO Lite
cases:
  count: 1
  route: /draco/cases
answer:
  instructions: Answer completely.
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
synthesis:
  model: provider/synthesizer
  instructions: Combine the panel answers.
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
grader:
  kind: rubric
  criteria_route: /draco/criteria/{case_id}
  criteria_per_case: 10
  model: provider/judge
  passes: 1
  instructions: Return JSON.
  params:
    temperature: 0.2
aggregator:
  kind: mean
  route: /benchmark
metrics:
  primary: normalized_score
  direction: maximize
tools:
  - web_search
  - web_fetch
"""


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
        response = httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": model, "object": "model", "owned_by": model.split("/", 1)[0]}
                    for model in models
                ],
            },
        )
    elif request.url.path == "/v1/benchmarks":
        response = httpx.Response(
            200,
            json={
                "object": "list",
                "default": "draco-lite",
                "data": [{"id": "draco-lite", "object": "benchmark"}],
            },
        )
    elif request.url.path == "/v1/benchmarks/draco-lite":
        response = httpx.Response(200, content=MANIFEST)
    else:
        response = httpx.Response(404)
    return response


def _client() -> tuple[sf.Client, _FakeTransport]:
    client = sf.Client(engine_url="https://engine.example")
    private_client = cast(Any, client)
    private_client._http.close()
    private_client._http = httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(_engine),
    )
    transport = _FakeTransport()
    private_client._transport = transport
    return client, transport


def test_client_evaluates_the_complete_draco_lite_vertical_slice() -> None:
    client, transport = _client()

    model = sf.Model("anthropic/claude-haiku-4-5", name="haiku")

    with client:
        report = client.evaluate(model, limit=1)

    result = report.candidates.only
    assert report.benchmark.id == "draco-lite"
    assert result.models == ("anthropic/claude-haiku-4-5",)
    assert tuple(operation.kind for operation in result.operations) == (
        "model",
        "judge",
        "grading",
        "aggregation",
    )
    assert result.url4.count("/benchmark") == 1
    assert result.url4.startswith("(/draco/cases*")
    assert "/draco/criteria/$case_id" in result.url4
    assert "/provider/judge" in result.url4
    assert "/benchmark(aggregate)" in result.url4
    assert "temperature=0.2" in result.url4
    assert "reasoning=low" in result.url4
    assert "max_output_tokens=4096" in result.url4
    assert "\n" not in result.url4

    assert result.name == "haiku"
    assert result.score == 0.7
    assert result.metrics == {
        "normalized_score": 0.7,
        "coverage": 1.0,
    }
    assert result.usage.input_tokens == 120
    assert result.duration_ms == 2000
    assert transport.closed is True


@pytest.mark.asyncio
async def test_async_client_evaluates_the_same_draco_lite_contract() -> None:
    client = sf.AsyncClient(engine_url="https://engine.example")
    private_client = cast(Any, client)
    await private_client._http.aclose()
    private_client._http = httpx.AsyncClient(
        base_url="https://engine.example",
        transport=httpx.MockTransport(_engine),
    )
    transport = _AsyncFakeTransport()
    private_client._transport = transport

    async with client:
        report = await client.evaluate(
            sf.Model("anthropic/claude-haiku-4-5", name="haiku"),
            limit=1,
        )

    assert report.candidates.only.name == "haiku"
    assert report.candidates.only.score == 0.7
    assert transport.closed is True


def test_client_runs_candidates_concurrently_and_preserves_declared_order() -> None:
    client, previous = _client()
    previous.close()
    transport = _ConcurrentFakeTransport(expected=3)
    cast(Any, client)._transport = transport
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
    client = sf.AsyncClient(engine_url="https://engine.example")
    private_client = cast(Any, client)
    await private_client._http.aclose()
    private_client._http = httpx.AsyncClient(
        base_url="https://engine.example",
        transport=httpx.MockTransport(_engine),
    )
    await private_client._transport.close()
    transport = _AsyncConcurrentFakeTransport(expected=3)
    private_client._transport = transport
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
        "provider/synthesizer",
    )
    assert tuple(member.name for member in result.members) == ("first", "second")
    assert tuple(operation.kind for operation in result.operations) == (
        "model",
        "model",
        "synthesis",
        "judge",
        "grading",
        "aggregation",
    )
    assert "/provider/first" in result.url4
    assert "/provider/second" in result.url4
    assert "/provider/synthesizer" in result.url4
    assert "Combine the panel answers." in result.url4


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
    assert tuple(member.name for member in result.members) == (
        "gemini-pro",
        "claude-opus-4.8",
    )
    assert "gemini-pro:" not in result.url4
    assert "claude-opus-4.8:" not in result.url4
    assert "member_1: {name: 'gemini-pro', answer: '$model_1'}" in result.url4
    assert "member_2: {name: 'claude-opus-4.8', answer: '$model_2'}" in result.url4


def test_compiler_deduplicates_equivalent_model_values_by_content() -> None:
    left = sf.Fusion(
        [sf.Model("provider/first"), sf.Model("provider/second")],
        name="left",
    )
    right = sf.Fusion(
        [sf.Model("provider/first"), sf.Model("provider/judge")],
        name="right",
    )
    candidate = sf.Fusion([left, right], name="outer")
    client, _transport = _client()

    with client:
        report = client.evaluate(candidate, benchmark="draco-lite", limit=1)

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
    candidate = sf.Fusion([left, right], name="outer")
    client, _transport = _client()

    with client:
        report = client.evaluate(candidate, benchmark="draco-lite", limit=1)

    result = report.candidates.only
    assert tuple(operation.kind for operation in result.operations).count("model") == 4
    assert result.url4.count("/provider/first") == 2


def test_manifest_reader_rejects_transport_and_integrity_failures() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(unreachable),
    ) as http:
        with pytest.raises(sf.PlanningError, match="Could not reach"):
            load_manifest(http, "draco-lite")

    malformed = b"schema: [unterminated"

    def invalid_yaml(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "default": "draco-lite",
                    "data": [{"id": "draco-lite", "object": "benchmark"}],
                },
            )
        return httpx.Response(200, content=malformed)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(invalid_yaml),
    ) as http:
        with pytest.raises(sf.PlanningError, match="valid YAML"):
            load_manifest(http, "draco-lite")


def test_manifest_decoder_rejects_every_required_field_boundary() -> None:
    base = yaml.safe_load(MANIFEST)
    assert isinstance(base, dict)

    bad_tools = deepcopy(base)
    bad_tools["tools"] = "web_search"
    bad_count = deepcopy(base)
    bad_count["cases"]["count"] = 0
    bad_direction = deepcopy(base)
    bad_direction["metrics"]["direction"] = "sideways"
    bad_route = deepcopy(base)
    bad_route["aggregator"]["route"] = "relative"
    bad_criteria_route = deepcopy(base)
    bad_criteria_route["grader"]["criteria_route"] = "/draco/criteria"
    bad_cases = deepcopy(base)
    bad_cases["cases"] = []

    invalid_values: tuple[object, ...] = (
        [],
        {},
        bad_tools,
        bad_count,
        bad_direction,
        bad_route,
        bad_criteria_route,
        bad_cases,
    )
    for value in invalid_values:
        with pytest.raises(sf.PlanningError):
            _decode_manifest(value)


def test_manifest_catalogue_rejects_malformed_and_unknown_records() -> None:
    with pytest.raises(sf.PlanningError, match="must be JSON"):
        _select_benchmark(httpx.Response(200, text="{"), "draco-lite")
    with pytest.raises(sf.PlanningError, match="must be an object"):
        _select_benchmark(httpx.Response(200, json=[]), "draco-lite")
    with pytest.raises(sf.PlanningError, match="object must be 'list'"):
        _select_benchmark(httpx.Response(200, json={}), "draco-lite")
    with pytest.raises(sf.PlanningError, match="entry"):
        _select_benchmark(
            httpx.Response(
                200,
                json={"object": "list", "default": "draco-lite", "data": [None]},
            ),
            "draco-lite",
        )
    with pytest.raises(sf.PlanningError, match="duplicate id"):
        _select_benchmark(
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "default": "draco-lite",
                    "data": [
                        {"id": "draco-lite", "object": "benchmark"},
                        {"id": "draco-lite", "object": "benchmark"},
                    ],
                },
            ),
            "draco-lite",
        )
    with pytest.raises(sf.PlanningError, match="does not expose"):
        _select_benchmark(
            httpx.Response(200, json={"object": "list", "default": None, "data": []}),
            "draco-lite",
        )
    with pytest.raises(sf.PlanningError, match="no Benchmarks"):
        _select_benchmark(
            httpx.Response(200, json={"object": "list", "default": None, "data": []}),
            None,
        )
    assert (
        _select_benchmark(
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "default": "healthbench",
                    "data": [
                        {"id": "draco-lite", "object": "benchmark"},
                        {"id": "healthbench", "object": "benchmark"},
                    ],
                },
            ),
            None,
        )
        == "healthbench"
    )
    with pytest.raises(sf.PlanningError, match="HTTP 404"):
        _success(httpx.Response(404), "load Benchmark")


def test_compiler_normalizes_url4_parameters_and_rejects_control_characters() -> None:
    assert _url4_text("line 1\r\nline 2\t$value") == "line 1\u2028line 2 $$value"
    with pytest.raises(ValueError, match="U\\+0001"):
        _url4_text("bad\x01text")


def test_candidate_result_decoder_rejects_contract_drift() -> None:
    client, _ = _client()
    with client:
        private_client = cast(Any, client)
        evaluation = _compile_sync(
            private_client._http,
            sf.Model("anthropic/claude-haiku-4-5"),
            "draco-lite",
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
