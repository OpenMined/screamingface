from __future__ import annotations

import json

import httpx
import pytest

from screamingface.errors import GatewayError, ProviderCallError
from screamingface.gateway import AIGatewayClient


def _connection(connection_id: str = "conn-1") -> dict:
    return {
        "id": connection_id,
        "provider": "anthropic",
        "label": "work",
        "status": "active",
        "auth_type": "oauth",
    }


async def _exercise_connection_lifecycle(client: AIGatewayClient) -> None:
    assert (await client.list_connections())[0].id == "conn-1"
    assert (await client.get_connection("conn-1")).status == "active"
    oauth = await client.start_oauth_connection(
        "anthropic", "work", "http://localhost:9999/callback"
    )
    assert oauth.connection_id == "pending-1"
    keyed = await client.create_api_key_connection("anthropic", "keyed", "secret")
    assert keyed.auth_type == "api_key"
    replaced = await client.replace_api_key_connection("key-1", "replacement")
    assert replaced.id == "key-1"
    await client.delete_connection("key-1")


@pytest.mark.asyncio
async def test_gateway_connection_lifecycle_request_shapes() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/v1/oauth/connections":
            response = httpx.Response(200, json={"connections": [_connection()]})
        elif request.method == "GET":
            response = httpx.Response(200, json=_connection(path.rsplit("/", 1)[-1]))
        elif path == "/v1/oauth/connections/api-key":
            body = json.loads(request.content)
            assert body == {"provider": "anthropic", "label": "keyed", "api_key": "secret"}
            response = httpx.Response(201, json={**_connection("key-1"), "auth_type": "api_key"})
        elif request.method == "PUT":
            assert json.loads(request.content) == {"api_key": "replacement"}
            response = httpx.Response(200, json={**_connection("key-1"), "auth_type": "api_key"})
        elif request.method == "POST":
            body = json.loads(request.content)
            assert body["redirect_uri"] == "http://localhost:9999/callback"
            response = httpx.Response(
                201,
                json={
                    "connection_id": "pending-1",
                    "authorize_url": "https://provider.test/auth",
                    "expires_in": 600,
                },
            )
        else:
            response = httpx.Response(204)
        return response

    client = AIGatewayClient(
        "https://gateway.test", token="jwt", transport=httpx.MockTransport(handler)
    )
    await _exercise_connection_lifecycle(client)
    await client.aclose()
    assert len(requests) == 6


@pytest.mark.asyncio
async def test_gateway_connection_and_provider_error_boundaries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(409)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                502,
                json={
                    "detail": {
                        "code": "provider_unavailable",
                        "message": "Code Assist project is not provisioned",
                    }
                },
            )
        return httpx.Response(200, json={"connections": []})

    client = AIGatewayClient(
        "https://gateway.test", token="jwt", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(GatewayError, match="deleting"):
        await client.delete_connection("bad")
    with pytest.raises(ProviderCallError) as error:
        await client.complete(model="gemini-cli/model", messages=[])
    assert error.value.code == "provider_unavailable"
    assert "not provisioned" in str(error.value)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised", "code"),
    [(httpx.ReadTimeout("slow"), "timeout"), (httpx.ConnectError("offline"), "network_error")],
)
async def test_provider_transport_errors_are_typed(raised: httpx.HTTPError, code: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise raised

    client = AIGatewayClient(
        "https://gateway.test", token="jwt", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderCallError) as error:
        await client.complete(model="provider/model", messages=[])
    assert error.value.code == code
    await client.aclose()
