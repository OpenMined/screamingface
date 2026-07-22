"""Real benchmark route milestones forwarded through evaluation SSE."""

from __future__ import annotations

import json

import httpx
import pytest
import screamingface as sf
import screamingface._benchmarks.gpqa as gpqa_source
from model_fixtures import MODEL_ROUTES
from screamingface._compiler import compile_benchmark_expression

from screamingface_engine.aggregators import MEAN_ROUTE
from screamingface_engine.app import create_app
from screamingface_engine.benchmarks import GPQA_CASES_ROUTE
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.graders import EXACT_CHOICE_ROUTE
from screamingface_engine.settings import Settings


@pytest.mark.asyncio
async def test_gpqa_stream_reports_dataset_models_cases_and_aggregation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_test_not_a_real_secret")
    monkeypatch.setattr(
        gpqa_source,
        "gpqa_cases",
        lambda: (
            sf.Case("q1", "Pick A", reference="A"),
            sf.Case("q2", "Pick A again", reference="A"),
        ),
    )

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        answer = "A" if model == "codex/gpt-5.5" else "B"
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
        first=2,
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
        response = await client.get(
            "/v1",
            params={"q": expression},
            headers={"accept": "text/event-stream"},
        )
    await gateway.aclose()

    events = _events(response.text)
    progress = [payload for name, payload in events if name == "progress"]
    assert response.status_code == 200
    assert events[0][0] == "accepted"
    assert events[-1][0] == "complete"
    assert [(event["stage"], event["status"]) for event in progress[:2]] == [
        ("dataset", "started"),
        ("dataset", "completed"),
    ]
    assert (
        sum(event["stage"] == "model" and event["status"] == "started" for event in progress) == 4
    )
    assert (
        sum(event["stage"] == "model" and event["status"] == "completed" for event in progress) == 4
    )
    graded: list[tuple[str, str, str]] = []
    for event in progress:
        if event["stage"] != "grading":
            continue
        label = event["label"]
        status = event["status"]
        operation_id = event["operation_id"]
        assert isinstance(label, str)
        assert isinstance(status, str)
        assert isinstance(operation_id, str)
        graded.append((status, label, operation_id))
    assert sorted(graded) == [
        ("completed", "Graded case q1", "grading:gpqa@1:q1"),
        ("completed", "Graded case q2", "grading:gpqa@1:q2"),
        ("started", "Grading case q1", "grading:gpqa@1:q1"),
        ("started", "Grading case q2", "grading:gpqa@1:q2"),
    ]
    assert progress[-1] == {
        "schema": "screamingface.evaluation-event.v1",
        "type": "progress",
        "stage": "aggregating",
        "status": "started",
        "label": "Aggregating 2 benchmark cases",
    }


def _events(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        payload = json.loads(data)
        assert isinstance(payload, dict)
        events.append((event, payload))
    return events
