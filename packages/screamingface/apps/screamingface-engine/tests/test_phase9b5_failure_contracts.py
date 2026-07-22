from __future__ import annotations

import httpx
import pytest
from model_fixtures import MODEL_ROUTES
from url4 import Request, ResolutionError

from screamingface_engine.app import create_app
from screamingface_engine.catalog import ModelRoute
from screamingface_engine.executor import ModelExecutor
from screamingface_engine.gateway import AssistantTurn, GatewayClient, ToolCall
from screamingface_engine.settings import Settings
from screamingface_engine.tool_policy import FetchPolicy, SearchPolicy

HF_MODEL = ModelRoute(
    "huggingface/zai-org/GLM-5.2~deepinfra",
    "huggingface/zai-org/GLM-5.2:deepinfra",
    "huggingface",
    ("web_search", "web_fetch"),
    "tavily",
)


class _Gateway:
    def __init__(self) -> None:
        self.turns = 0

    async def turn(self, *_args: object, **_kwargs: object) -> AssistantTurn:
        self.turns += 1
        name = "web_search" if self.turns == 1 else "web_fetch"
        arguments = (
            '{"query":"evidence"}' if name == "web_search" else '{"url":"https://example.org"}'
        )
        return AssistantTurn(None, (ToolCall(str(self.turns), name, arguments),))


class _Tavily:
    async def is_connected(self) -> bool:
        return True

    async def search(self, query: str, policy: SearchPolicy) -> dict[str, object]:
        del query, policy
        return {"results": []}

    async def extract(
        self,
        url: str,
        policy: FetchPolicy,
        *,
        query: str | None,
    ) -> dict[str, object]:
        del policy
        return {"url": url, "content": "Evidence", "query": query}


@pytest.mark.asyncio
async def test_payment_required_survives_the_public_engine_boundary() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"detail": {"message": "Payment Required"}})

    settings = Settings(gateway_url="http://gateway.test")
    gateway = GatewayClient(
        settings.gateway_url,
        timeout=settings.gateway_timeout,
        transport=httpx.MockTransport(handler),
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=settings, gateway=gateway)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://engine.test",
    ) as client:
        response = await client.get("/gemini/2.5-flash", params={"q": "(Question)!Answer"})
    await gateway.aclose()

    assert response.status_code == 402
    assert response.json()["error"] == {
        "code": "payment_required",
        "message": "AI Gateway returned HTTP 402 (payment_required) for 'gemini/2.5-flash'",
    }


@pytest.mark.asyncio
async def test_round_budget_failure_reports_limit_and_safe_tool_counts() -> None:
    params = {
        "tools": "web_search:web_fetch",
        "tools.max_calls": "2",
        "web_search.max_results": "5",
    }
    executor = ModelExecutor(_Gateway(), _Tavily())

    with pytest.raises(ResolutionError) as captured:
        await executor.complete(HF_MODEL, Request(HF_MODEL.route, "Question", "Answer", params))

    assert captured.value.code == "tool_budget_exhausted"
    assert str(captured.value) == (
        "model route 'huggingface/zai-org/GLM-5.2~deepinfra' exceeded the total tool-call limit"
    )
