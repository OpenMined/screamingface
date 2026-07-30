from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
import yaml

import screamingface as sf
from screamingface._benchmark_manifest import (
    _catalog_record,
    _decode_manifest,
    _success,
    load_manifest,
)
from screamingface._compiler import _parameter, _url4_text
from screamingface._evaluation import Candidate
from screamingface._ports import _RunOutcome
from screamingface._result_decoder import _candidate_result
from screamingface.client import _compile_sync

MANIFEST = b"""\
schema: screamingface.benchmark-manifest.v1
name: draco-lite
id: draco-lite
title: DRACO Lite
cases:
  route: /benchmarks/draco-lite/cases
  count: 1
grader:
  route: /benchmarks/draco-lite/grade
  criteria_per_case: 10
aggregator:
  route: /benchmarks/draco-lite/aggregate
metrics:
  primary: normalized_score
  direction: maximize
tools:
  - web_search
  - web_fetch
"""
DIGEST = f"sha256:{hashlib.sha256(MANIFEST).hexdigest()}"


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
                    "manifest_digest": DIGEST,
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


def _engine(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/benchmarks":
        return httpx.Response(
            200,
            json={
                "benchmarks": [
                    {
                        "name": "draco-lite",
                        "id": "draco-lite",
                        "manifest_digest": DIGEST,
                    }
                ]
            },
        )
    if request.url.path == "/v1/benchmarks/draco-lite/manifest":
        return httpx.Response(200, content=MANIFEST)
    return httpx.Response(404)


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

    model = sf.Model(
        "anthropic/claude-haiku-4-5",
        name="haiku",
        instructions="Answer fully.\nPreserve $evidence.",
        temperature=0.2,
        reasoning="low",
        max_output_tokens=4096,
    )

    with client:
        report = client.evaluate(model, benchmark="draco-lite", limit=1)

    result = report.candidates.only
    assert report.benchmark.id == "draco-lite"
    assert report.benchmark.manifest_digest == DIGEST
    assert result.models == ("anthropic/claude-haiku-4-5",)
    assert tuple(operation.kind for operation in result.operations) == (
        "model",
        "grading",
        "aggregation",
    )
    assert "/benchmarks/draco-lite/cases" in result.url4
    assert "/benchmarks/draco-lite/grade" in result.url4
    assert "/benchmarks/draco-lite/aggregate" in result.url4
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
            benchmark="draco-lite",
            limit=1,
        )

    assert report.candidates.only.name == "haiku"
    assert report.candidates.only.score == 0.7
    assert transport.closed is True


def test_evaluate_compiles_every_candidate_before_starting_paid_work() -> None:
    client, transport = _client()
    first = sf.Model("anthropic/claude-haiku-4-5", name="haiku")
    unsupported = sf.Fusion(
        "pair",
        members=[first, sf.Model("provider/second")],
        reducer=sf.reducers.Synthesis("provider/reducer"),
    )
    with client, pytest.raises(sf.PlanningError, match="accepts Model Candidates"):
        client.evaluate([first, unsupported], benchmark="draco-lite", limit=1)

    assert transport.calls == []


def test_manifest_reader_rejects_transport_and_integrity_failures() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(unreachable),
    ) as http:
        with pytest.raises(sf.PlanningError, match="Could not reach"):
            load_manifest(http, "draco-lite")

    def mismatch(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks":
            return httpx.Response(
                200,
                json={
                    "benchmarks": [
                        {
                            "name": "draco-lite",
                            "id": "draco-lite",
                            "manifest_digest": f"sha256:{'0' * 64}",
                        }
                    ]
                },
            )
        return httpx.Response(200, content=MANIFEST)

    with httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(mismatch),
    ) as http:
        with pytest.raises(sf.PlanningError, match="advertised digest"):
            load_manifest(http, "draco-lite")

    malformed = b"schema: [unterminated"
    malformed_digest = f"sha256:{hashlib.sha256(malformed).hexdigest()}"

    def invalid_yaml(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks":
            return httpx.Response(
                200,
                json={
                    "benchmarks": [
                        {
                            "name": "draco-lite",
                            "id": "draco-lite",
                            "manifest_digest": malformed_digest,
                        }
                    ]
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
    bad_name = deepcopy(base)
    bad_name["name"] = " "
    bad_count = deepcopy(base)
    bad_count["cases"]["count"] = 0
    bad_direction = deepcopy(base)
    bad_direction["metrics"]["direction"] = "sideways"
    bad_route = deepcopy(base)
    bad_route["cases"]["route"] = "relative"
    bad_cases = deepcopy(base)
    bad_cases["cases"] = []

    invalid_values: tuple[object, ...] = (
        [],
        {},
        bad_tools,
        bad_name,
        bad_count,
        bad_direction,
        bad_route,
        bad_cases,
    )
    for value in invalid_values:
        with pytest.raises(sf.PlanningError):
            _decode_manifest(value, DIGEST)


def test_manifest_catalogue_rejects_malformed_and_unknown_records() -> None:
    with pytest.raises(sf.PlanningError, match="must be JSON"):
        _catalog_record(httpx.Response(200, text="{"), "draco-lite")
    with pytest.raises(sf.PlanningError, match="benchmarks array"):
        _catalog_record(httpx.Response(200, json={}), "draco-lite")
    with pytest.raises(sf.PlanningError, match="record must be an object"):
        _catalog_record(httpx.Response(200, json={"benchmarks": [None]}), "draco-lite")
    with pytest.raises(sf.PlanningError, match="does not expose"):
        _catalog_record(httpx.Response(200, json={"benchmarks": []}), "draco-lite")
    with pytest.raises(sf.PlanningError, match="HTTP 404"):
        _success(httpx.Response(404), "load Benchmark")


def test_compiler_normalizes_url4_parameters_and_rejects_control_characters() -> None:
    assert _parameter(True) == "true"
    assert _parameter(False) == "false"
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
        "manifest_digest": DIGEST,
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
        {**valid, "manifest_digest": "wrong"},
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
