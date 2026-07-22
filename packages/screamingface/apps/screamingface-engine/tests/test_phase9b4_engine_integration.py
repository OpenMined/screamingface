from __future__ import annotations

import json

import httpx
import pytest

from screamingface_engine.app import create_app
from screamingface_engine.catalog import GatewayModel, resolve_model_routes
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings, SettingsError
from screamingface_engine.tavily import TavilyService

HF_GATEWAY_MODELS = (
    GatewayModel("huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra", "huggingface"),
    GatewayModel("huggingface/zai-org/GLM-5.2:deepinfra", "huggingface"),
    GatewayModel("huggingface/moonshotai/Kimi-K2.6:fireworks-ai", "huggingface"),
)


def _params() -> dict[str, str]:
    return {
        "tools": "web_search:web_fetch",
        "tools.max_calls": "3",
        "web_search.max_results": "5",
    }


def test_exact_verified_hf_pins_alone_advertise_tavily_tools() -> None:
    routes = resolve_model_routes(HF_GATEWAY_MODELS)

    assert [route.tool_capabilities for route in routes] == [
        ("web_search", "web_fetch"),
        ("web_search", "web_fetch"),
        (),
    ]
    assert [route.tool_backend for route in routes] == ["tavily", "tavily", None]


def test_phase9b4_settings_use_long_evaluation_and_bounded_tavily_timeouts() -> None:
    defaults = Settings()
    configured = Settings.from_env(
        {
            "SCREAMINGFACE_ENGINE_TIMEOUT": "901",
            "SCREAMINGFACE_TAVILY_TIMEOUT": "75",
        }
    )

    assert defaults.evaluation_timeout == 900.0
    assert defaults.tavily_timeout == 75.0
    assert configured.evaluation_timeout == 901.0
    assert configured.tavily_timeout == 75.0
    with pytest.raises(SettingsError, match="TAVILY_TIMEOUT.*positive finite"):
        Settings.from_env({"SCREAMINGFACE_TAVILY_TIMEOUT": "0"})


@pytest.mark.asyncio
async def test_verified_hf_route_executes_gateway_tavily_gateway_as_plaintext() -> None:
    gateway_bodies: list[dict[str, object]] = []

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        gateway_bodies.append(body)
        if len(gateway_bodies) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "search-1",
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": '{"query":"current evidence"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "Final"}}]})

    tavily_paths: list[str] = []

    async def tavily_handler(request: httpx.Request) -> httpx.Response:
        tavily_paths.append(request.url.path)
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(200, json={"results": []})

    route = resolve_model_routes(HF_GATEWAY_MODELS[:1])[0]
    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(gateway_handler)
    )
    tavily = TavilyService(transport=httpx.MockTransport(tavily_handler))
    await tavily.set_api_key("tvly-secret")
    app = create_app(
        model_routes=(route,),
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
        tavily=tavily,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        registry = (await client.get("/.well-known/screamingface")).json()
        response = await client.get(
            route.route,
            params={**_params(), "q": "(Question)!Answer with evidence"},
        )

    await gateway.aclose()
    await tavily.aclose()
    assert registry["models"][0]["supported_tools"] == ["web_search", "web_fetch"]
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Final"
    assert tavily_paths == ["/usage", "/search"]
    assert "web_search.max_results" not in gateway_bodies[0]
    messages = gateway_bodies[1]["messages"]
    assert isinstance(messages, list)
    last_message = messages[-1]
    assert isinstance(last_message, dict)
    assert last_message["role"] == "tool"


@pytest.mark.asyncio
async def test_missing_tavily_maps_to_application_owned_401_error() -> None:
    route = resolve_model_routes(HF_GATEWAY_MODELS[:1])[0]
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(lambda _request: pytest.fail("Gateway was called")),
    )
    tavily = TavilyService(
        transport=httpx.MockTransport(lambda _request: pytest.fail("Tavily was called"))
    )
    app = create_app(
        model_routes=(route,),
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
        tavily=tavily,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get(
            route.route,
            params={**_params(), "q": "(Question)!Answer"},
        )

    await gateway.aclose()
    await tavily.aclose()
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
