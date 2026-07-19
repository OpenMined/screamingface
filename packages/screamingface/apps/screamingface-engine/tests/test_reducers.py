from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import screamingface as sf
from screamingface._compiler import compile_fusion
from url4 import Request, ResolutionError

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.reducers import majority_vote
from screamingface_engine.settings import Settings


def _request(
    context: str,
    *,
    intent: str = "",
    params: dict[str, str] | None = None,
) -> Request:
    return Request(
        path="/reducers/majority-vote",
        context=context,
        intent=intent,
        params=params or {},
    )


def test_majority_vote_parses_resolved_context_and_orders_members_numerically() -> None:
    assert majority_vote(_request('{"member_3":"A","member_1":"B","member_2":"A"}')) == "A"
    assert majority_vote(_request('{"member_2":"A","member_1":"B"}')) == "B"


@pytest.mark.parametrize(
    ("reducer_request", "message"),
    [
        (_request("not json"), "JSON object"),
        (_request("[]"), "JSON object"),
        (_request('{"member_1":"A"}'), "n >= 2"),
        (_request('{"member_1":"A","member_3":"B"}'), "contiguous"),
        (_request('{"member_01":"A","member_2":"B"}'), "keys"),
        (_request('{"panel_1":"A","member_2":"B"}'), "keys"),
        (_request('{"member_1":"A","member_2":2}'), "strings"),
        (_request('{"member_1":"A","member_2":" "}'), "blank"),
        (_request('{"member_1":"A","member_2":"B"}', intent="vote"), "intent"),
        (
            _request('{"member_1":"A","member_2":"B"}', params={"mode": "strict"}),
            "parameters",
        ),
    ],
)
def test_majority_vote_rejects_malformed_requests(reducer_request: Request, message: str) -> None:
    with pytest.raises(ResolutionError, match=message) as raised:
        majority_vote(reducer_request)

    assert raised.value.code == "malformed_source"
    assert raised.value.permanent is True


def _app(gateway: GatewayClient):
    return create_app(
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
    )


@pytest.mark.asyncio
async def test_reducer_route_and_complete_literal_expression_return_plaintext() -> None:
    calls = 0

    async def reject_gateway(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(reject_gateway),
    )
    transport = httpx.ASGITransport(app=_app(gateway))
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        direct = await client.get(
            "/reducers/majority-vote",
            params={"q": '({"member_2":"B","member_1":"A","member_3":"B"})'},
        )
        evaluated = await client.get(
            "/v1",
            params={
                "q": (
                    "(member_answers={member_1:'A',member_2:'B',member_3:'A'},"
                    "fusion_answer=/reducers/majority-vote($member_answers),"
                    "{schema:'screamingface.fusion-result.v1',answer:'$fusion_answer'})"
                )
            },
        )
    await gateway.aclose()

    assert direct.status_code == 200
    assert direct.text == "B"
    assert evaluated.status_code == 200
    assert evaluated.json() == {"schema": "screamingface.fusion-result.v1", "answer": "A"}
    assert calls == 0


@pytest.mark.asyncio
async def test_complete_model_and_reducer_expression_makes_only_panel_gateway_calls() -> None:
    requests: list[dict[str, Any]] = []
    answers = {
        "codex/gpt-5.5": "A",
        "gemini-cli/gemini-2.5-pro": "B",
        "anthropic/claude-sonnet-4-6": "A",
    }

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answers[payload["model"]]}}]},
        )

    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(gateway_handler),
    )
    transport = httpx.ASGITransport(app=_app(gateway))
    expression = (
        "(question='Choose',"
        "member_1=/codex/gpt-5.5($question)!'Answer',"
        "member_2=/gemini/2.5($question)!'Answer',"
        "member_3=/claude/sonnet-4.6($question)!'Answer',"
        "member_answers={member_1:'$member_1',member_2:'$member_2',member_3:'$member_3'},"
        "fusion_answer=/reducers/majority-vote($member_answers),"
        "{schema:'screamingface.fusion-result.v1',"
        "members:{member_1:{model:'codex/gpt-5.5',answer:'$member_1'},"
        "member_2:{model:'gemini/2.5',answer:'$member_2'},"
        "member_3:{model:'claude/sonnet-4.6',answer:'$member_3'}},"
        "answer:'$fusion_answer'})"
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/v1", params={"q": expression})
    await gateway.aclose()

    assert response.status_code == 200
    assert response.json()["answer"] == "A"
    assert [request["model"] for request in requests] == [
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-6",
    ]


@pytest.mark.asyncio
async def test_sdk_compiler_expression_executes_on_the_persistent_node() -> None:
    answers = {
        "codex/gpt-5.5": "A",
        "gemini-cli/gemini-2.5-pro": "B",
        "anthropic/claude-sonnet-4-6": "A",
    }

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answers[payload["model"]]}}]},
        )

    fusion = sf.Fusion(
        "compiled",
        ["codex/gpt-5.5", "gemini/2.5", "claude/sonnet-4.6"],
        reducer=sf.reducers.MajorityVote(),
    )
    expression = compile_fusion(fusion, question="Choose A or B")
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(gateway_handler),
    )
    transport = httpx.ASGITransport(app=_app(gateway))
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/v1", params={"q": expression})
    await gateway.aclose()

    assert response.status_code == 200
    assert response.json() == {
        "schema": "screamingface.fusion-result.v1",
        "members": {
            "member_1": {"model": "codex/gpt-5.5", "answer": "A"},
            "member_2": {"model": "gemini/2.5", "answer": "B"},
            "member_3": {"model": "claude/sonnet-4.6", "answer": "A"},
        },
        "answer": "A",
    }


@pytest.mark.asyncio
async def test_sdk_model_reducer_receives_resolved_question_and_labeled_answers() -> None:
    requests: list[dict[str, Any]] = []

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        system = payload["messages"][0]["content"]
        if system == "Synthesize the panel answers.":
            answer = "combined"
        elif payload["model"] == "codex/gpt-5.5":
            answer = "alpha"
        else:
            answer = "beta"
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    fusion = sf.Fusion(
        "compiled-model-reducer",
        ["codex/gpt-5.5", "gemini/2.5"],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Synthesize the panel answers.",
        ),
    )
    expression = compile_fusion(fusion, question="Research question")
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(gateway_handler),
    )
    transport = httpx.ASGITransport(app=_app(gateway))
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/v1", params={"q": expression})
    await gateway.aclose()

    reducer_request = next(
        request
        for request in requests
        if request["messages"][0]["content"] == "Synthesize the panel answers."
    )
    assert reducer_request["messages"][1]["content"] == (
        "Question:\nResearch question\n\nPanel answers:\n"
        "Panel 1 [codex/gpt-5.5]:\nalpha\n\n"
        "Panel 2 [gemini/2.5]:\nbeta"
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "combined"


@pytest.mark.asyncio
async def test_reducer_errors_surface_as_atomic_url4_failures() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    transport = httpx.ASGITransport(app=_app(gateway))
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get(
            "/v1",
            params={
                "q": (
                    "(answers={member_1:'A',member_3:'B'},"
                    "winner=/reducers/majority-vote($answers),{answer:'$winner'})"
                )
            },
        )
    await gateway.aclose()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "malformed_source"
