from __future__ import annotations

import json

import httpx
import pytest
import screamingface as sf
from model_fixtures import MODEL_ROUTES
from screamingface._compiler import compile_benchmark_expression

import screamingface_engine.benchmark_definitions.gpqa as gpqa_source
from screamingface_engine.aggregators import MEAN_ROUTE
from screamingface_engine.app import create_app
from screamingface_engine.benchmarks import GPQA_CASES_ROUTE
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.graders import EXACT_CHOICE_ROUTE
from screamingface_engine.settings import Settings


@pytest.mark.asyncio
async def test_one_url4_request_slices_runs_grades_and_aggregates_gpqa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_test_not_a_real_secret")
    monkeypatch.setattr(
        gpqa_source,
        "gpqa_cases",
        lambda: (
            sf.Case("q1", "Pick A", reference="A"),
            sf.Case("q2", "This row must not run", reference="B"),
        ),
    )
    gateway_requests: list[dict[str, object]] = []

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        gateway_requests.append(payload)
        answer = "A" if payload["model"] == "codex/gpt-5.5" else "B"
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    recipe = sf.Fusion(
        "duo",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )
    expression = compile_benchmark_expression(
        benchmark_id="gpqa@1",
        cases_route=GPQA_CASES_ROUTE,
        grader_route=EXACT_CHOICE_ROUTE,
        aggregator_route=MEAN_ROUTE,
        recipe=recipe,
        first=1,
    )
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(gateway_handler),
    )
    app = create_app(
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
        model_routes=MODEL_ROUTES,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/v1", params={"q": expression})
    await gateway.aclose()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.json() == {
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
            "member_2": {"model": "gemini/2.5-flash", "score": 0.0, "metrics": {}},
        },
        "metrics": {},
        "failures": [],
        "complete": True,
    }
    assert [request["model"] for request in gateway_requests] == [
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-flash",
    ]
