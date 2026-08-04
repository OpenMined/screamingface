"""Protocol variants are ordinary Engine-owned Benchmark identities."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

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
                            "object": "benchmark_family",
                            "id": "ifeval",
                            "title": "IFEval",
                            "description": "Instruction following.",
                            "default_variant": "canonical",
                            "variants": [
                                {
                                    "id": "canonical",
                                    "title": "IFEval",
                                    "description": "One deterministic check.",
                                },
                                {
                                    "id": "self-corrective",
                                    "title": "IFEval Self-corrective",
                                    "description": "Three whole-Candidate attempts.",
                                },
                            ],
                            "href": "/v1/benchmarks/ifeval",
                        }
                    ],
                },
            )
        if request.url.path == "/v1/benchmarks/ifeval":
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.benchmark-family.v1",
                    "id": "ifeval",
                    "title": "IFEval",
                    "description": "Instruction following.",
                    "default_variant": "canonical",
                    "variants": {
                        variant: {
                            "title": title,
                            "description": title,
                            "revision": f"{variant}-revision",
                            "case_count": 1,
                            "total_case_count": 541,
                            "required_models": [],
                            "url4": "(/candidate('question')!'$candidate')!'answer'",
                        }
                        for variant, title in (
                            ("canonical", "IFEval"),
                            ("self-corrective", "IFEval Self-corrective"),
                        )
                    },
                },
            )
        return httpx.Response(404)


def test_discovery_flattens_variants_from_one_family_fetch() -> None:
    engine = _Engine()
    with sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine),
    ) as client:
        benchmarks = client.benchmarks.list()

    canonical, corrective = benchmarks
    assert [value.id for value in benchmarks] == ["ifeval", "ifeval/self-corrective"]
    assert canonical.family == corrective.family == "ifeval"
    assert canonical.variant == "canonical"
    assert corrective.variant == "self-corrective"
    assert engine.paths.count("/v1/benchmarks/ifeval") == 1


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
                    "case_count": 1,
                    "score": 1.0,
                    "metrics": {},
                    "failures": [],
                }
            ),
            media_type="application/json",
            root_usage=None,
        )

    def close(self) -> None:
        pass


def test_evaluation_fetches_one_family_and_selects_one_explicit_variant() -> None:
    benchmark_requests: list[httpx.Request] = []

    def engine(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks/ifeval":
            benchmark_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.benchmark-family.v1",
                    "id": "ifeval",
                    "title": "IFEval",
                    "description": "Instruction following.",
                    "default_variant": "canonical",
                    "variants": {
                        "canonical": {
                            "title": "Canonical",
                            "description": "One answer.",
                            "revision": "canonical-revision",
                            "case_count": 1,
                            "total_case_count": 541,
                            "required_models": [],
                            "url4": "(/candidate('question')!'$candidate')!'answer'",
                        },
                        "self-corrective": {
                            "title": "Self-corrective",
                            "description": "Three attempts.",
                            "revision": "self-revision",
                            "case_count": 1,
                            "total_case_count": 541,
                            "required_models": [],
                            "url4": "(/candidate('question')!'$candidate')!'answer'",
                        },
                    },
                },
            )
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "default_synthesizer": "provider/model",
                    "data": [{"id": "provider/model", "object": "model", "owned_by": "provider"}],
                },
            )
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
