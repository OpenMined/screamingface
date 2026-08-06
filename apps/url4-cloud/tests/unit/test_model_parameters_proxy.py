"""OME-480: the Engine exposes AI Gateway's profile-bound model details."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.catalog import build_catalog_service
from url4_cloud.catalog.aigateway import AigatewayCatalogSource
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogUnavailable,
    Credential,
    ModelParameterBadResponse,
    ModelParameterResponse,
)
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

pytestmark = pytest.mark.asyncio

_MODEL = "openrouter/openai/gpt-5.5"
_IDENTITY = {"X-User-Email": "alice@example.com"}
_CONTRACT = {
    "schema_version": 1,
    "contract_id": "pc_fixture",
    "model": {
        "id": _MODEL,
        "gateway_provider": "openrouter",
        "upstream_id": "openai/gpt-5.5",
    },
    "context": {"scope": "account_profile", "auth_mode": "api_key"},
    "parameters": {
        "temperature": {
            "request_path": "temperature",
            "schema": {"type": "number", "minimum": 0, "maximum": 2},
            "gateway": {"status": "enabled", "projection": "direct"},
        }
    },
    "tools": {},
    "transport": {},
    "freshness": {"stale": False, "degraded": False},
    "future_field": {"preserved": True},
}


async def test_adapter_returns_model_details_verbatim_for_the_callers_scope() -> None:
    seen: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_CONTRACT)

    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(upstream),
    )
    source = AigatewayCatalogSource(client)

    response = await source.fetch_model_parameters(
        Credential.derive("research", _IDENTITY),
        _MODEL,
    )

    assert response.status == 200
    assert response.body == _CONTRACT
    assert seen[0].url.path == "/v1/model-parameters"
    assert dict(seen[0].url.params) == {"model": _MODEL}
    assert seen[0].headers["X-User-Email"] == "alice@example.com"
    assert seen[0].headers["X-Profile"] == "research"
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
async def test_adapter_preserves_caller_correctable_gateway_responses(status: int) -> None:
    body = {"detail": {"code": "profile_not_ready", "name": "research"}}
    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    )

    response = await AigatewayCatalogSource(client).fetch_model_parameters(
        Credential.derive(),
        _MODEL,
    )

    assert response.status == status
    assert response.body == body


async def test_adapter_translates_a_model_details_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow upstream", request=request)

    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(timeout),
    )

    with pytest.raises(CatalogUnavailable):
        await AigatewayCatalogSource(client).fetch_model_parameters(
            Credential.derive(),
            _MODEL,
        )


@pytest.mark.parametrize(
    ("status", "content"),
    [
        (200, b"not json"),
        (200, b"[]"),
        (500, b'{"detail":"internal"}'),
    ],
)
async def test_adapter_rejects_unusable_gateway_responses(
    status: int,
    content: bytes,
) -> None:
    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                content=content,
                headers={"content-type": "application/json"},
            )
        ),
    )

    with pytest.raises(ModelParameterBadResponse):
        await AigatewayCatalogSource(client).fetch_model_parameters(
            Credential.derive(),
            _MODEL,
        )


async def test_adapter_translates_a_gateway_connection_failure() -> None:
    def disconnected(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gateway unavailable", request=request)

    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(disconnected),
    )

    with pytest.raises(ModelParameterBadResponse):
        await AigatewayCatalogSource(client).fetch_model_parameters(
            Credential.derive(),
            _MODEL,
        )


@pytest.mark.parametrize(
    "body",
    [
        {**_CONTRACT, "schema_version": True},
        {**_CONTRACT, "model": {**_CONTRACT["model"], "id": "openrouter/other"}},
        {**_CONTRACT, "parameters": []},
        {**_CONTRACT, "tools": []},
        {**_CONTRACT, "transport": []},
    ],
)
async def test_adapter_rejects_an_unusable_success_document(body: object) -> None:
    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )

    with pytest.raises(CatalogBadResponse):
        await AigatewayCatalogSource(client).fetch_model_parameters(
            Credential.derive(),
            _MODEL,
        )


async def test_adapter_names_an_unusable_model_parameter_response() -> None:
    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"detail": "internal"})
        ),
    )

    with pytest.raises(ModelParameterBadResponse) as caught:
        await AigatewayCatalogSource(client).fetch_model_parameters(
            Credential.derive(),
            _MODEL,
        )

    assert caught.value.detail == "aigateway returned an unusable model-parameter contract"


class _ParameterSource:
    def __init__(self, response: ModelParameterResponse) -> None:
        self.response = response
        self.seen: list[tuple[Credential, str]] = []

    async def fetch_model_parameters(
        self,
        credential: Credential,
        model: str,
    ) -> ModelParameterResponse:
        self.seen.append((credential, model))
        return self.response


class _FailingParameterSource:
    async def fetch_model_parameters(
        self,
        credential: Credential,
        model: str,
    ) -> ModelParameterResponse:
        raise CatalogBadResponse("upstream included a secret-shaped detail")


async def test_engine_returns_model_details_for_the_verified_identity_and_profile() -> None:
    source = _ParameterSource(ModelParameterResponse(status=200, body=_CONTRACT))
    app = create_app(
        Settings(jwt_secret="model-details-test"),
        stream=InMemoryEventStream(),
        model_parameters=source,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/model-parameters",
            params={"model": _MODEL},
            headers={"X-User-Email": "alice@example.com", "X-Profile": "research"},
        )

    assert response.status_code == 200
    assert response.json() == _CONTRACT
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"
    credential, model = source.seen[0]
    assert model == _MODEL
    assert credential.profile == "research"
    assert credential.identity == _IDENTITY


async def test_production_catalog_wiring_exposes_model_details_without_a_second_client() -> None:
    clients: list[httpx.AsyncClient] = []

    def client_factory(base_url: str) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            base_url=base_url,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=_CONTRACT)),
        )
        clients.append(client)
        return client

    settings = Settings(
        jwt_secret="model-details-test",
        aigateway_base_url="http://aigateway.test",
    )
    service = build_catalog_service(settings, client_factory=client_factory)
    assert service is not None
    app = create_app(
        settings,
        stream=InMemoryEventStream(),
        catalog=service,
        model_parameters=service.model_parameter_source,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == 200
    assert response.json() == _CONTRACT
    assert len(clients) == 1
    await service.aclose()


async def test_engine_hides_unusable_upstream_details_behind_a_private_problem() -> None:
    app = create_app(
        Settings(jwt_secret="model-details-test"),
        stream=InMemoryEventStream(),
        model_parameters=_FailingParameterSource(),
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"
    assert "secret-shaped" not in response.text


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
async def test_engine_preserves_caller_correctable_model_detail_responses(status: int) -> None:
    body: dict[str, object] = {"detail": {"code": "profile_not_ready", "name": "research"}}
    source = _ParameterSource(ModelParameterResponse(status=status, body=body))
    app = create_app(
        Settings(jwt_secret="model-details-test"),
        stream=InMemoryEventStream(),
        model_parameters=source,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == status
    assert response.json() == body
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_unconfigured_model_details_are_a_private_503_problem() -> None:
    app = create_app(Settings(jwt_secret="model-details-test"), stream=InMemoryEventStream())
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"


async def test_missing_model_is_a_private_400_problem() -> None:
    source = _ParameterSource(ModelParameterResponse(status=200, body=_CONTRACT))
    app = create_app(
        Settings(jwt_secret="model-details-test"),
        stream=InMemoryEventStream(),
        model_parameters=source,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"
    assert source.seen == []


async def test_engine_maps_a_model_details_timeout_to_a_private_504_problem() -> None:
    class _TimedOut:
        async def fetch_model_parameters(
            self,
            credential: Credential,
            model: str,
        ) -> ModelParameterResponse:
            raise CatalogUnavailable(CatalogUnavailable.detail)

    app = create_app(
        Settings(jwt_secret="model-details-test"),
        stream=InMemoryEventStream(),
        model_parameters=_TimedOut(),
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == 504
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"


async def test_model_details_are_published_in_openapi_under_catalog() -> None:
    app = create_app(Settings(jwt_secret="model-details-test"), stream=InMemoryEventStream())
    operation = app.openapi()["paths"]["/v1/model-parameters"]["get"]

    assert operation["tags"] == ["Catalog"]
    assert operation["parameters"][0]["name"] == "model"
