"""Protocol variants are ordinary Engine-owned Benchmark identities."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
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
                    "default": "ifeval",
                    "data": [
                        {
                            "object": "benchmark",
                            "id": "ifeval",
                            "variant": "canonical",
                            "title": "IFEval",
                            "description": "One deterministic check.",
                            "href": "/v1/benchmarks/ifeval",
                        },
                        {
                            "object": "benchmark",
                            "id": "ifeval/self-corrective",
                            "variant": "self-corrective",
                            "title": "IFEval Self-corrective",
                            "description": "Three whole-Candidate attempts.",
                            "href": "/v1/benchmarks/ifeval/self-corrective",
                        },
                    ],
                },
            )
        if request.url.path in {
            "/v1/benchmarks/ifeval",
            "/v1/benchmarks/ifeval/self-corrective",
        }:
            corrective = request.url.path.endswith("self-corrective")
            variant = "self-corrective" if corrective else "canonical"
            title = "IFEval Self-corrective" if corrective else "IFEval"
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

    canonical, corrective = benchmarks
    assert [value.id for value in benchmarks] == ["ifeval", "ifeval/self-corrective"]
    assert all(not hasattr(value, "family") for value in benchmarks)
    assert canonical.variant == "canonical"
    assert corrective.variant == "self-corrective"
    assert engine.paths.count("/v1/benchmarks/ifeval") == 1
    assert engine.paths.count("/v1/benchmarks/ifeval/self-corrective") == 1


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
                    "benchmark_id": "ifeval/self-corrective",
                    "benchmark_revision": "self-revision",
                    "case_count": 1,
                    "score": 1.0,
                    "metrics": {},
                    "cases": [
                        {
                            "case_id": 1,
                            "input": "Question",
                            "output": "Answer",
                            "finish_reason": "stop",
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
        if request.url.path == "/v1/benchmarks/ifeval/self-corrective":
            benchmark_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.benchmark.v1",
                    "id": "ifeval/self-corrective",
                    "variant": "self-corrective",
                    "title": "IFEval Self-corrective",
                    "description": "Three attempts.",
                    "revision": "self-revision",
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
            benchmark="ifeval/self-corrective",
            limit=1,
        )

    assert report.benchmark.id == "ifeval/self-corrective"
    assert report.benchmark.revision == "self-revision"
    assert len(benchmark_requests) == 1
    assert dict(benchmark_requests[0].url.params) == {"limit": "1"}
