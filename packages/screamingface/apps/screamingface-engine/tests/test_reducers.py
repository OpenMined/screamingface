from __future__ import annotations

import json

import httpx
import pytest
from screamingface import Case
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


def test_majority_vote_parses_resolved_context_and_orders_panels_numerically() -> None:
    assert majority_vote(_request('{"panel_3":"A","panel_1":"B","panel_2":"A"}')) == "A"
    assert majority_vote(_request('{"panel_2":"A","panel_1":"B"}')) == "B"


@pytest.mark.parametrize(
    ("reducer_request", "message"),
    [
        (_request("not json"), "JSON object"),
        (_request("[]"), "JSON object"),
        (_request('{"panel_1":"A"}'), "n >= 2"),
        (_request('{"panel_1":"A","panel_3":"B"}'), "contiguous"),
        (_request('{"panel_01":"A","panel_2":"B"}'), "keys"),
        (_request('{"member_1":"A","panel_2":"B"}'), "keys"),
        (_request('{"panel_1":"A","panel_2":2}'), "strings"),
        (_request('{"panel_1":"A","panel_2":" "}'), "blank"),
        (_request('{"panel_1":"A","panel_2":"B"}', intent="vote"), "intent"),
        (
            _request('{"panel_1":"A","panel_2":"B"}', params={"mode": "strict"}),
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
        case_loaders={"gpqa@1": lambda: (Case("q", "Q", reference="A"),), "draco@1": lambda: ()},
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
            params={"q": '({"panel_2":"B","panel_1":"A","panel_3":"B"})'},
        )
        evaluated = await client.get(
            "/v1",
            params={
                "q": (
                    "(panel_answers={panel_1:'A',panel_2:'B',panel_3:'A'},"
                    "fusion_answer=/reducers/majority-vote($panel_answers),"
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
    requests: list[dict[str, object]] = []
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
        "panel_1=/codex/gpt-5.5($question)!'Answer',"
        "panel_2=/gemini/2.5($question)!'Answer',"
        "panel_3=/claude/sonnet-4.6($question)!'Answer',"
        "panel_answers={panel_1:'$panel_1',panel_2:'$panel_2',panel_3:'$panel_3'},"
        "fusion_answer=/reducers/majority-vote($panel_answers),"
        "{schema:'screamingface.fusion-result.v1',"
        "members:{panel_1:{model:'codex/gpt-5.5',answer:'$panel_1'},"
        "panel_2:{model:'gemini/2.5',answer:'$panel_2'},"
        "panel_3:{model:'claude/sonnet-4.6',answer:'$panel_3'}},"
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
                    "(answers={panel_1:'A',panel_3:'B'},"
                    "winner=/reducers/majority-vote($answers),{answer:'$winner'})"
                )
            },
        )
    await gateway.aclose()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "malformed_source"
