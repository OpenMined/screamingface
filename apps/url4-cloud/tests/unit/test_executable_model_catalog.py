"""The Engine advertises only Gateway models its declared world can execute.

FEATURE: OME-625 — model discovery is an Engine capability contract, not a raw copy of every
route AI Gateway could serve directly.
STORY: an SDK user can select any id returned by Engine ``GET /v1/models`` without discovering
at render time that the route is absent or cannot be expressed as URL4.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.catalog.executable import ExecutableCatalog, ExecutableModelParameterSource
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    Credential,
    ModelCatalog,
    ModelParameterResponse,
    compute_etag,
)
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

pytestmark = pytest.mark.asyncio

_DECLARED = "openrouter/openai/gpt-5.5"
_GATEWAY_ONLY = "huggingface/google/gemma-2-2b-it:featherless-ai"


class _GatewayCatalog:
    counters = None
    entry_count = 0

    async def fetch(self, credential: Credential) -> ModelCatalog:
        body: dict[str, object] = {
            "object": "list",
            "gateway_extension": {"kept": True},
            "data": [
                {"id": _DECLARED, "object": "model", "future_field": 7},
                {"id": _GATEWAY_ONLY, "object": "model"},
            ],
        }
        return ModelCatalog(body=body, etag=compute_etag(body))

    def max_age_s(self, credential: Credential) -> int:
        return 60

    async def aclose(self) -> None:
        pass


class _MalformedGatewayCatalog(_GatewayCatalog):
    async def fetch(self, credential: Credential) -> ModelCatalog:
        body: dict[str, object] = {"object": "list", "data": "not-a-list"}
        return ModelCatalog(body=body, etag=compute_etag(body))


class _GatewayDetails:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def fetch_model_parameters(
        self,
        credential: Credential,
        model: str,
    ) -> ModelParameterResponse:
        self.seen.append(model)
        return ModelParameterResponse(status=200, body={"model": {"id": model}})

    async def aclose(self) -> None:
        pass


def _app(details: _GatewayDetails | None = None):
    return create_app(
        Settings(jwt_secret="executable-catalog-secret"),
        stream=InMemoryEventStream(),
        catalog=ExecutableCatalog(_GatewayCatalog(), frozenset({_DECLARED})),
        model_parameters=(
            ExecutableModelParameterSource(details, frozenset({_DECLARED}))
            if details is not None
            else None
        ),
    )


async def test_catalog_contains_only_declared_executable_models_without_reshaping_them() -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "gateway_extension": {"kept": True},
        "data": [{"id": _DECLARED, "object": "model", "future_field": 7}],
    }
    assert response.headers["ETag"] == f'"{compute_etag(response.json())}"'


async def test_malformed_gateway_catalog_cannot_bypass_the_projection() -> None:
    catalog = ExecutableCatalog(_MalformedGatewayCatalog(), frozenset({_DECLARED}))

    with pytest.raises(CatalogBadResponse, match="not a list"):
        await catalog.fetch(Credential.derive())


async def test_undeclared_model_details_fail_without_contacting_gateway() -> None:
    details = _GatewayDetails()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(details)), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _GATEWAY_ONLY})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "the model is not installed on this Engine"
    assert details.seen == []


async def test_declared_model_details_keep_the_gateway_contract() -> None:
    details = _GatewayDetails()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(details)), base_url="http://test"
    ) as client:
        response = await client.get("/v1/model-parameters", params={"model": _DECLARED})

    assert response.status_code == 200
    assert response.json() == {"model": {"id": _DECLARED}}
    assert details.seen == [_DECLARED]
