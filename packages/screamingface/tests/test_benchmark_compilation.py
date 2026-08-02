"""Candidate compilation and one-fetch Benchmark linkage contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from url4 import RelExpr, build, expr, iterate, render, src, text

import screamingface as sf
from screamingface._core.ports import _RunOutcome
from screamingface._evaluation.benchmark import _decode_benchmark_resource
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.compilation import compile_evaluation
from screamingface._evaluation.linking import link_candidate
from screamingface._evaluation.model import Candidate


def _benchmark_url4() -> str:
    return render(
        expr(
            src(
                RelExpr(
                    path="/candidate",
                    context="A question with commas, (parentheses), and $variables.",
                    intent=text("$candidate"),
                ),
                name="answer",
                weight=0.0,
            ),
            src(
                RelExpr(
                    path="/provider/judge",
                    context="$answer",
                    intent=text("Grade the answer."),
                ),
                name="grade",
                weight=0.0,
            ),
            intent=text("$grade"),
        )
    )


def _resource(*, url4: str | None = None) -> dict[str, object]:
    return {
        "schema": "screamingface.benchmark.v1",
        "id": "bench@1",
        "revision": "fixture-revision",
        "case_count": 1,
        "total_case_count": 3,
        "required_models": ["provider/judge"],
        "url4": _benchmark_url4() if url4 is None else url4,
    }


def test_benchmark_resource_is_data_plus_one_ordinary_url4_expression() -> None:
    benchmark = _decode_benchmark_resource(
        _resource(),
        requested_id="bench@1",
        requested_limit=1,
    )

    assert benchmark.info.id == "bench@1"
    assert benchmark.info.case_count == 3
    assert benchmark.case_count == 1
    assert benchmark.required_models == ("provider/judge",)
    assert benchmark.info.revision == "fixture-revision"
    assert render(build(benchmark.url4)) == benchmark.url4
    assert not hasattr(benchmark, "protocol")
    assert not hasattr(benchmark, "plan_route")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema": "other"}, "schema"),
        ({"id": "other"}, "wrong Benchmark id"),
        ({"revision": ""}, "revision"),
        ({"url4": "not valid ("}, "URL4"),
    ],
)
def test_benchmark_resource_contract_is_validated(
    change: dict[str, object],
    message: str,
) -> None:
    payload = {**_resource(), **change}

    with pytest.raises(sf.PlanningError, match=message):
        _decode_benchmark_resource(
            payload,
            requested_id="bench@1",
            requested_limit=1,
        )


def test_model_compilation_uses_candidate_owned_defaults_and_input_binding() -> None:
    compiled = compile_candidate(sf.Model("provider/model"))

    assert compiled.kind == "model"
    assert compiled.models == ("provider/model",)
    assert "$input" in compiled.url4
    assert "Answer the request accurately and completely." in compiled.url4
    assert "Follow every instruction and formatting constraint" in compiled.url4
    assert "reasoning=low" in compiled.url4
    assert "max_output_tokens=4096" in compiled.url4
    assert [operation.kind for operation in compiled.operations] == ["model"]


def test_fusion_compilation_is_benchmark_agnostic_and_uses_sdk_defaults() -> None:
    compiled = compile_candidate(
        sf.Fusion(
            [
                sf.Model("provider/a", prompt="Answer from A."),
                sf.Model("provider/b"),
            ],
            name="pair",
        )
    )

    assert compiled.kind == "fusion"
    assert compiled.models == (
        "provider/a",
        "provider/b",
        "openrouter/anthropic/claude-haiku-4.5",
    )
    assert "/provider/a" in compiled.url4
    assert "/provider/b" in compiled.url4
    assert "/openrouter/anthropic/claude-haiku-4.5" in compiled.url4
    assert "Answer from A." in compiled.url4
    assert "Synthesize the strongest supported answer" in compiled.url4
    assert "follow every instruction and formatting constraint" in compiled.url4
    assert [operation.kind for operation in compiled.operations] == [
        "model",
        "model",
        "synthesis",
    ]
    assert [member.name for member in compiled.members] == ["a", "b"]


def test_linker_preserves_a_top_level_benchmark_iteration_without_templates() -> None:
    candidate = compile_candidate(sf.Model("provider/model"))
    benchmark = render(
        iterate(
            ("one", "two"),
            body=src(
                RelExpr(
                    path="/candidate",
                    context="$item",
                    intent=text("$candidate"),
                ),
                name="answer",
                weight=0.0,
            ),
            intent=text("$answer"),
            on_error="fail",
        )
    )

    linked = link_candidate(candidate.url4, benchmark)

    assert render(build(linked)) == linked
    assert linked.count("/provider/model") == 1
    assert "/candidate" in linked
    assert "$input" in linked


def test_evaluation_inspection_combines_benchmark_and_candidate_requirements() -> None:
    benchmark = _decode_benchmark_resource(
        _resource(),
        requested_id="bench@1",
        requested_limit=1,
    )
    recipes = (
        sf.Model("provider/a"),
        sf.Fusion(
            [sf.Model("provider/a"), sf.Model("provider/b")],
            name="pair",
        ),
    )

    evaluation = compile_evaluation(recipes, benchmark, 1)

    assert evaluation.required_models == (
        "provider/a",
        "provider/b",
        "openrouter/anthropic/claude-haiku-4.5",
        "provider/judge",
    )
    assert [operation.kind for operation in evaluation.candidates[0].operations] == ["model"]
    assert [operation.kind for operation in evaluation.candidates[1].operations] == [
        "model",
        "model",
        "synthesis",
    ]


class _Transport:
    def __init__(self) -> None:
        self.candidates: list[Candidate] = []

    def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        self.candidates.append(candidate)
        return _RunOutcome(
            run_id=f"run_{candidate.name}",
            started_at=datetime(2026, 8, 1, tzinfo=UTC),
            completed_at=datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
            result_body=json.dumps(
                {
                    "schema": "screamingface.candidate-result.v1",
                    "benchmark_id": "bench@1",
                    "case_count": 1,
                    "score": 0.8,
                    "metrics": {"coverage": 1.0},
                    "failures": [],
                }
            ),
            media_type="application/json",
            root_usage=None,
        )

    def close(self) -> None:
        pass


def test_client_fetches_once_then_locally_builds_every_candidate_url4() -> None:
    benchmark_requests: list[httpx.Request] = []

    def engine(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/benchmarks/bench@1":
            benchmark_requests.append(request)
            return httpx.Response(200, json=_resource())
        if request.method == "GET" and request.url.path == "/v1/models":
            models = (
                "provider/a",
                "provider/b",
                "openrouter/anthropic/claude-haiku-4.5",
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
        raise AssertionError(f"unexpected Engine request: {request.method} {request.url}")

    candidates = [
        sf.Model("provider/a", prompt="Custom answer prompt."),
        sf.Fusion(
            [sf.Model("provider/a"), sf.Model("provider/b")],
            name="pair",
        ),
    ]
    transport = _Transport()
    with sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine),
        run_transport=transport,
    ) as client:
        report = client.evaluate(candidates, benchmark="bench@1", limit=1)

    assert [candidate.name for candidate in report.candidates] == ["a", "pair"]
    assert len(benchmark_requests) == 1
    assert dict(benchmark_requests[0].url.params) == {"limit": "1"}
    assert len(transport.candidates) == 2
    for candidate in transport.candidates:
        assert render(build(candidate.url4)) == candidate.url4
        assert "/candidate" in candidate.url4
        assert "/provider/judge" in candidate.url4
    assert transport.candidates[0].url4.count("/provider/a") == 1
    assert transport.candidates[1].url4.count("/provider/a") == 1
    assert transport.candidates[1].url4.count("/provider/b") == 1
