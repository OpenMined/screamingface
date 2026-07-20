from __future__ import annotations

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings
from screamingface_engine.tavily_connection import MAX_TAVILY_RESPONSE_BYTES, TavilyConnection


def _settings() -> Settings:
    return Settings(gateway_url="http://gateway.test")


def _usage_response() -> dict[str, object]:
    return {
        "key": {"usage": 1, "limit": 1000},
        "account": {"plan": "researcher"},
    }


def _gateway_that_must_not_be_called() -> GatewayClient:
    return GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("Tavily connection traffic reached AI Gateway")
        ),
    )


@pytest.mark.asyncio
async def test_tavily_is_advertised_as_an_engine_owned_api_key_connection() -> None:
    tavily = TavilyConnection(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("registry discovery contacted Tavily")
        )
    )
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/.well-known/screamingface")

    await tavily.aclose()
    await gateway.aclose()
    providers = response.json()["providers"]
    assert providers[-1] == {
        "id": "tavily",
        "display_name": "Tavily",
        "auth_methods": ["api_key"],
    }
    assert all(model["supported_tools"] == [] for model in response.json()["models"])


@pytest.mark.asyncio
async def test_tavily_key_is_validated_directly_and_public_state_is_sanitized() -> None:
    secret = "tvly-phase9b2-private-secret"
    tavily_requests: list[httpx.Request] = []

    async def tavily_handler(request: httpx.Request) -> httpx.Response:
        tavily_requests.append(request)
        return httpx.Response(200, json=_usage_response())

    tavily = TavilyConnection(transport=httpx.MockTransport(tavily_handler))
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        connected = await client.put("/v1/connections/tavily/api-key", json={"api_key": secret})
        status = await client.get("/v1/connections/tavily")

    await tavily.aclose()
    await gateway.aclose()
    expected = {
        "provider": "tavily",
        "status": "connected",
        "auth_method": "api_key",
        "account_label": None,
    }
    assert connected.status_code == 200
    assert connected.json() == status.json() == expected
    assert len(tavily_requests) == 1
    assert tavily_requests[0].method == "GET"
    assert str(tavily_requests[0].url) == "https://api.tavily.com/usage"
    assert tavily_requests[0].headers["authorization"] == f"Bearer {secret}"
    assert secret not in connected.text
    assert secret not in status.text
    assert secret not in repr(tavily)


@pytest.mark.asyncio
async def test_tavily_list_merges_gateway_and_engine_owned_connection_state() -> None:
    gateway_calls: list[str] = []

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        gateway_calls.append(request.url.path)
        return httpx.Response(200, json={"connections": []})

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(gateway_handler)
    )
    tavily = TavilyConnection(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=_usage_response()))
    )
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        before = await client.get("/v1/connections")
        await client.put("/v1/connections/tavily/api-key", json={"api_key": "tvly-valid-secret"})
        after = await client.get("/v1/connections")

    await tavily.aclose()
    await gateway.aclose()
    assert before.json()["connections"][-1] == {
        "provider": "tavily",
        "status": "not_connected",
        "auth_method": None,
        "account_label": None,
    }
    assert after.json()["connections"][-1]["status"] == "connected"
    assert gateway_calls == ["/v1/oauth/connections", "/v1/oauth/connections"]


@pytest.mark.asyncio
async def test_failed_tavily_replacement_is_atomic_and_restart_clears_memory() -> None:
    async def tavily_handler(request: httpx.Request) -> httpx.Response:
        if request.headers["authorization"] == "Bearer tvly-first-valid-secret":
            return httpx.Response(200, json=_usage_response())
        return httpx.Response(401, text="private rejected credential diagnostic")

    tavily = TavilyConnection(transport=httpx.MockTransport(tavily_handler))
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        first = await client.put(
            "/v1/connections/tavily/api-key",
            json={"api_key": "tvly-first-valid-secret"},
        )
        rejected = await client.put(
            "/v1/connections/tavily/api-key",
            json={"api_key": "tvly-rejected-secret"},
        )
        retained = await client.get("/v1/connections/tavily")
        disconnected = await client.delete("/v1/connections/tavily")
        cleared = await client.get("/v1/connections/tavily")

    fresh = TavilyConnection(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("fresh connection status contacted Tavily")
        )
    )
    await tavily.aclose()
    await gateway.aclose()
    assert first.status_code == 200
    assert rejected.status_code == 401
    assert rejected.json() == {
        "schema": "screamingface.error.v1",
        "code": "invalid_credentials",
        "message": "The Tavily API key is invalid.",
        "provider": "tavily",
        "retryable": False,
    }
    assert "private rejected" not in rejected.text
    assert "tvly-rejected-secret" not in rejected.text
    assert retained.json()["status"] == "connected"
    assert disconnected.status_code == 204
    assert cleared.json()["status"] == "not_connected"
    assert (await fresh.get_public())["status"] == "not_connected"
    await fresh.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream", "status", "code", "retryable"),
    [
        (httpx.Response(403, text="private forbidden"), 401, "invalid_credentials", False),
        (httpx.Response(429, text="private quota"), 429, "rate_limited", True),
        (httpx.Response(500, text="private outage"), 503, "provider_unavailable", True),
        (httpx.Response(200, json={"unexpected": True}), 502, "invalid_provider_response", True),
    ],
)
async def test_tavily_failures_are_stable_safe_and_retryable_when_appropriate(
    upstream: httpx.Response,
    status: int,
    code: str,
    retryable: bool,
) -> None:
    tavily = TavilyConnection(transport=httpx.MockTransport(lambda _request: upstream))
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put(
            "/v1/connections/tavily/api-key", json={"api_key": "tvly-candidate-secret"}
        )

    await tavily.aclose()
    await gateway.aclose()
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["retryable"] is retryable
    assert "private" not in response.text
    assert "tvly-candidate-secret" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (httpx.ConnectError("private network detail"), 503, "provider_unavailable"),
        (httpx.ReadTimeout("private timeout detail"), 503, "provider_unavailable"),
    ],
)
async def test_tavily_transport_failures_are_sanitized(
    failure: httpx.RequestError,
    status: int,
    code: str,
) -> None:
    async def tavily_handler(_request: httpx.Request) -> httpx.Response:
        raise failure

    tavily = TavilyConnection(transport=httpx.MockTransport(tavily_handler))
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put(
            "/v1/connections/tavily/api-key", json={"api_key": "tvly-candidate-secret"}
        )

    await tavily.aclose()
    await gateway.aclose()
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["retryable"] is True
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_tavily_validation_response_is_byte_bounded() -> None:
    tavily = TavilyConnection(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"x" * (MAX_TAVILY_RESPONSE_BYTES + 1))
        )
    )
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put(
            "/v1/connections/tavily/api-key", json={"api_key": "tvly-candidate-secret"}
        )

    await tavily.aclose()
    await gateway.aclose()
    assert response.status_code == 502
    assert response.json()["code"] == "invalid_provider_response"
    assert response.json()["retryable"] is True


@pytest.mark.asyncio
async def test_tavily_oauth_is_rejected_without_tavily_or_gateway_traffic() -> None:
    tavily = TavilyConnection(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("unsupported Tavily OAuth contacted Tavily")
        )
    )
    gateway = _gateway_that_must_not_be_called()
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=_settings(),
        gateway=gateway,
        tavily=tavily,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.post("/v1/connections/tavily/oauth")

    await tavily.aclose()
    await gateway.aclose()
    assert response.status_code == 400
    assert response.json()["code"] == "auth_method_not_supported"
