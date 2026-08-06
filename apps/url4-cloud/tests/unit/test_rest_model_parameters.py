"""Model details cross URL4 Cloud without changing the AI Gateway contract.

FEATURE: OME-480 — the Client discovers model parameters through its one Engine endpoint.
STORY: as an SDK user with explicit Model parameters, Evaluation preflight receives the same
profile-bound contract AI Gateway would have returned directly.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.catalog.aigateway import AigatewayModelDetailsSource
from url4_cloud.catalog.port import Credential, ModelDetails
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

pytestmark = pytest.mark.asyncio

_MODEL = "openrouter/openai/gpt-5.5"
_DETAILS = {
    "schema_version": 1,
    "model": {"id": _MODEL},
    "context": {},
    "parameters": {},
    "tools": {},
    "transport": {},
    "freshness": {"stale": False, "degraded": False},
}


class FakeModels:
    def __init__(self, details: ModelDetails | None = None) -> None:
        self.seen: list[tuple[str, Credential]] = []
        self.details = details or ModelDetails(body=_DETAILS)

    async def fetch_details(self, model: str, credential: Credential) -> ModelDetails:
        self.seen.append((model, credential))
        return self.details

    async def aclose(self) -> None:
        pass


def _app(models: FakeModels) -> FastAPI:
    return create_app(
        Settings(jwt_secret="model-parameters-secret"),
        stream=InMemoryEventStream(),
        model_details=models,
    )


async def test_model_details_are_forwarded_for_the_callers_profile() -> None:
    models = FakeModels()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(models)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/model-parameters",
            params={"model": _MODEL},
            headers={"X-User-Email": "alice@example.com", "X-Profile": "research"},
        )

    assert response.status_code == 200
    assert response.json() == _DETAILS
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "X-Profile, X-User-Email"
    assert models.seen == [
        (
            _MODEL,
            Credential.derive("research", {"X-User-Email": "alice@example.com"}),
        )
    ]


async def test_aigateway_adapter_preserves_the_authoritative_document() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_DETAILS)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url="http://aigateway.test",
    ) as client:
        source = AigatewayModelDetailsSource(client)
        details = await source.fetch_details(
            _MODEL,
            Credential.derive("research", {"X-User-Email": "alice@example.com"}),
        )

    assert details == ModelDetails(body=_DETAILS)
    assert seen[0].url.path == "/v1/model-parameters"
    assert seen[0].url.params["model"] == _MODEL
    assert seen[0].headers["X-User-Email"] == "alice@example.com"
    assert seen[0].headers["X-Profile"] == "research"


async def test_aigateway_model_not_found_remains_a_model_not_found() -> None:
    body: dict[str, object] = {"detail": {"code": "model_not_found", "model": _MODEL}}
    models = FakeModels(ModelDetails(body=body, status_code=404))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(models)),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == 404
    assert response.json() == body
    assert response.headers["Cache-Control"] == "private, no-store"


async def test_unconfigured_model_details_are_a_503() -> None:
    app = create_app(
        Settings(jwt_secret="model-parameters-secret"),
        stream=InMemoryEventStream(),
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _MODEL})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_model_details_route_is_in_openapi() -> None:
    assert "/v1/model-parameters" in _app(FakeModels()).openapi()["paths"]
