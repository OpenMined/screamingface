"""The Engine advertises only Gateway models its declared world can execute.

FEATURE: OME-625 — model discovery is an Engine capability contract, not a raw copy of every
route AI Gateway could serve directly.
STORY: an SDK user can select any id returned by Engine ``GET /v1/models`` without discovering
at render time that the route is absent or cannot be expressed as URL4.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from url4_cloud import job_env
from url4_cloud.app import create_app
from url4_cloud.catalog import build_executable_catalog_service
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
from url4_cloud.world_config import WorldConfigError

pytestmark = pytest.mark.asyncio

_DECLARED = "openrouter/openai/gpt-5.5"
_GATEWAY_ONLY = "huggingface/google/gemma-2-2b-it:featherless-ai"


class _GatewayCatalog:
    counters = None
    entry_count = 0
    model_parameter_source = None

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
        content = f'{{"model":{{"id":"{model}"}}}}'.encode()
        return ModelParameterResponse(status=200, content=content)

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


async def test_empty_executable_intersection_is_a_valid_catalog() -> None:
    catalog = ExecutableCatalog(_GatewayCatalog(), frozenset())

    result = await catalog.fetch(Credential.derive())

    assert result.body == {
        "object": "list",
        "gateway_extension": {"kept": True},
        "data": [],
    }
    assert result.etag == compute_etag(result.body)


async def test_production_builder_wraps_the_gateway_source_with_the_declared_routes(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": _DECLARED, "object": "model"},
                    {"id": _GATEWAY_ONLY, "object": "model"},
                ],
            },
        )

    config = tmp_path / "url4.toml"
    config.write_text(
        '[aigateway]\ndefault_route = "openrouter/openai/gpt-5.5"\n'
        'models = ["openrouter/openai/gpt-5.5"]\n'
    )
    service = build_executable_catalog_service(
        Settings(aigateway_base_url="http://aigateway.test"),
        {job_env.RUNNER_CONFIG: str(config)},
        client_factory=lambda base_url: httpx.AsyncClient(
            base_url=base_url,
            transport=httpx.MockTransport(handler),
        ),
    )

    assert service is not None
    catalog = await service.fetch(Credential.derive())
    assert catalog.body["data"] == [{"id": _DECLARED, "object": "model"}]
    await service.aclose()


async def test_production_builder_snapshots_declared_routes_at_startup(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": _DECLARED, "object": "model"}]},
        )

    config = tmp_path / "url4.toml"
    config.write_text(f'[aigateway]\ndefault_route = "{_DECLARED}"\nmodels = ["{_DECLARED}"]\n')
    service = build_executable_catalog_service(
        Settings(aigateway_base_url="http://aigateway.test"),
        {job_env.RUNNER_CONFIG: str(config)},
        client_factory=lambda base_url: httpx.AsyncClient(
            base_url=base_url,
            transport=httpx.MockTransport(handler),
        ),
    )
    assert service is not None

    config.write_text('[aigateway]\nmodels = ["openrouter/other/model"]\n')
    catalog = await service.fetch(Credential.derive())

    assert catalog.body["data"] == [{"id": _DECLARED, "object": "model"}]
    await service.aclose()


async def test_unconfigured_builder_stays_unconfigured() -> None:
    service = build_executable_catalog_service(
        Settings(aigateway_base_url=None),
        {job_env.RUNNER_CONFIG: "/missing/url4.toml"},
    )

    assert service is None


async def test_configured_builder_fails_when_declared_routes_cannot_be_read() -> None:
    with pytest.raises(WorldConfigError, match="cannot read world config"):
        build_executable_catalog_service(
            Settings(aigateway_base_url="http://aigateway.test"),
            {job_env.RUNNER_CONFIG: "/missing/url4.toml"},
        )


async def test_configured_builder_accepts_the_valid_empty_engine_world(tmp_path: Path) -> None:
    config = tmp_path / "url4.toml"
    config.write_text("")
    service = build_executable_catalog_service(
        Settings(aigateway_base_url="http://aigateway.test"),
        {job_env.RUNNER_CONFIG: str(config)},
        client_factory=lambda base_url: httpx.AsyncClient(
            base_url=base_url,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"object": "list", "data": [{"id": _DECLARED}]},
                )
            ),
        ),
    )
    assert service is not None

    catalog = await service.fetch(Credential.derive())

    assert catalog.body["data"] == []
    await service.aclose()


async def test_configured_builder_rejects_a_runner_invalid_model_capability(
    tmp_path: Path,
) -> None:
    config = tmp_path / "url4.toml"
    config.write_text(
        '[aigateway]\ndefault_route = "model"\n'
        '[[aigateway.models]]\nid = "model"\nweb_tools = "yes"\n'
    )

    with pytest.raises(WorldConfigError, match="web_tools must be a boolean"):
        build_executable_catalog_service(
            Settings(aigateway_base_url="http://aigateway.test"),
            {job_env.RUNNER_CONFIG: str(config)},
        )


async def test_malformed_gateway_catalog_cannot_bypass_the_projection() -> None:
    catalog = ExecutableCatalog(_MalformedGatewayCatalog(), frozenset({_DECLARED}))

    with pytest.raises(CatalogBadResponse, match="not a list"):
        await catalog.fetch(Credential.derive())


async def test_malformed_gateway_model_cannot_bypass_the_projection() -> None:
    class _MalformedGatewayModel(_GatewayCatalog):
        async def fetch(self, credential: Credential) -> ModelCatalog:
            body: dict[str, object] = {"object": "list", "data": [{"object": "model"}]}
            return ModelCatalog(body=body, etag=compute_etag(body))

    catalog = ExecutableCatalog(_MalformedGatewayModel(), frozenset({_DECLARED}))

    with pytest.raises(CatalogBadResponse, match="missing a string id"):
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
