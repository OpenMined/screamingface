"""Protocol variants are ordinary Engine-owned Benchmark identities."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from _model_parameter_fixtures import details as _model_details

import screamingface as sf
from screamingface._core.ports import _RunOutcome
from screamingface._evaluation.model import Candidate


class _Engine:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/v1/benchmarks":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "object": "benchmark",
                            "id": "research",
                            "variant": "canonical",
                            "title": "Research",
                            "description": "Canonical protocol.",
                            "revision": "canonical-revision",
                            "case_count": 541,
                            "href": "/v1/benchmarks/research",
                        },
                        {
                            "object": "benchmark",
                            "id": "research/alternate",
                            "variant": "alternate",
                            "title": "Research Alternate",
                            "description": "Alternative protocol.",
                            "revision": "alternate-revision",
                            "case_count": 541,
                            "href": "/v1/benchmarks/research/alternate",
                        },
                    ],
                },
            )
        if request.url.path in {
            "/v1/benchmarks/research",
            "/v1/benchmarks/research/alternate",
        }:
            alternate = request.url.path.endswith("alternate")
            variant = "alternate" if alternate else "canonical"
            title = "Research Alternate" if alternate else "Research"
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.benchmark.v1",
                    "id": request.url.path.removeprefix("/v1/benchmarks/"),
                    "variant": variant,
                    "title": title,
                    "description": title,
                    "revision": f"{variant}-revision",
                    "case_count": 541,
                    "url4": "(/candidate('question')!'$candidate')!'answer'",
                },
            )
        return httpx.Response(404)


def test_discovery_reads_each_flat_benchmark_resource() -> None:
    engine = _Engine()
    with sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine),
    ) as client:
        benchmarks = client.benchmarks.list()

    canonical, alternate = benchmarks
    assert [value.id for value in benchmarks] == ["research", "research/alternate"]
    assert all(not hasattr(value, "family") for value in benchmarks)
    assert canonical.variant == "canonical"
    assert alternate.variant == "alternate"
    assert engine.paths == ["/v1/benchmarks"]


class _RunTransport:
    def __init__(self) -> None:
        self.candidates: list[Candidate] = []

    def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        self.candidates.append(candidate)
        return _RunOutcome(
            run_id="run-1",
            started_at=datetime(2026, 8, 4, tzinfo=UTC),
            completed_at=datetime(2026, 8, 4, 0, 0, 1, tzinfo=UTC),
            result_body=json.dumps(
                {
                    "schema": "screamingface.candidate-result.v1",
                    "benchmark_id": "research/alternate",
                    "benchmark_revision": "alternate-revision",
                    "case_count": 1,
                    "score": 1.0,
                    "coverage": 1.0,
                    "metrics": {},
                    "cases": [
                        {
                            "status": "scored",
                            "case_id": 1,
                            "input": "Question",
                            "output": "Answer",
                            "finish_reason": "stop",
                            "refusal": None,
                            "stop_reason": None,
                            "rounds_executed": None,
                            "grade": {
                                "method": "deterministic",
                                "score": 1.0,
                                "metrics": {},
                                "checks": [],
                            },
                            "failures": [],
                            "metadata": {},
                        }
                    ],
                    "failures": [],
                }
            ),
            media_type="application/json",
            root_usage=None,
        )

    def cancel_active(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_evaluation_fetches_the_explicit_flat_benchmark() -> None:
    benchmark_requests: list[httpx.Request] = []

    def engine(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks/research/alternate":
            benchmark_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.benchmark.v1",
                    "id": "research/alternate",
                    "variant": "alternate",
                    "title": "Research Alternate",
                    "description": "Three attempts.",
                    "revision": "alternate-revision",
                    "case_count": 541,
                    "url4": "(/candidate('question')!'$candidate')!'answer'",
                },
            )
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "provider/model",
                            "object": "model",
                            "owned_by": "provider",
                            "supported_parameters": [],
                            "supported_tools": [],
                            "unsupported_parameter_behavior": "reject",
                            "parameter_contract_url": ("/v1/model-parameters?model=provider/model"),
                        }
                    ],
                },
            )
        if request.url.path == "/v1/model-parameters":
            return httpx.Response(200, json=_model_details(request.url.params["model"]))
        raise AssertionError(f"unexpected Engine request: {request.url}")

    transport = _RunTransport()
    with sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine),
        run_transport=transport,
    ) as client:
        report = client.evaluate(
            sf.Model("provider/model"),
            benchmark="research/alternate",
            limit=1,
        )

    assert report.benchmark.id == "research/alternate"
    assert report.benchmark.revision == "alternate-revision"
    assert len(benchmark_requests) == 1
    assert benchmark_requests[0].url.raw_path == (b"/v1/benchmarks/research/alternate?limit=1")
    assert dict(benchmark_requests[0].url.params) == {"limit": "1"}


@pytest.mark.parametrize("benchmark_id", ("../token", "research/../token", "./research"))
def test_benchmark_paths_reject_navigation_segments(benchmark_id: str) -> None:
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"invalid Benchmark id reached the Engine: {request.url}")

    with sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(unexpected_request),
    ) as client:
        with pytest.raises(sf.PlanningError) as error:
            client.evaluate(sf.Model("provider/model"), benchmark=benchmark_id)

    assert error.value.code == "invalid_benchmark_selection"
