"""Composition + observability tests for the catalog service (OME-625; plan Batch 5).

Covers the factory contract, app wiring in both factories, client teardown, and the two secret-
hygiene invariants that only hold at the wiring layer: no setting stores an aigateway credential,
and no metric label carries one.
"""

from __future__ import annotations

import httpx
import pytest

from url4_cloud.app import create_app, make_local_app
from url4_cloud.catalog import build_catalog_service
from url4_cloud.catalog.cache import CachedCatalog
from url4_cloud.catalog.port import Credential, ModelCatalog, compute_etag
from url4_cloud.config import Settings
from url4_cloud_nats import InMemoryBus

pytestmark = pytest.mark.asyncio

BODY: dict[str, object] = {"object": "list", "data": [{"id": "m", "object": "model"}]}
TOKEN = "wiring-secret-token"


class FakeCatalog:
    def __init__(self) -> None:
        self.seen: list[Credential] = []

    async def fetch(self, credential: Credential) -> ModelCatalog:
        self.seen.append(credential)
        return ModelCatalog(body=BODY, etag=compute_etag(BODY))

    def max_age_s(self, credential: Credential) -> int:
        return 60


# --- the factory ----------------------------------------------------------


async def test_no_base_url_means_no_catalog_service() -> None:
    # INVARIANT: mirrors `build_job_runner`'s "unconfigured ⇒ None" contract, which the route
    # turns into a 503 rather than an AttributeError.
    assert build_catalog_service(Settings(aigateway_base_url=None)) is None


async def test_a_base_url_yields_a_cached_service() -> None:
    service = build_catalog_service(Settings(aigateway_base_url="http://aigw.test"))
    assert isinstance(service, CachedCatalog)
    await service.aclose()


async def test_the_factory_needs_no_credential_setting() -> None:
    # ACCEPTANCE 10 (spec §11): r3's whole point — url4-cloud holds NO aigateway credential, so a
    # service is buildable from a base URL alone.
    service = build_catalog_service(Settings(aigateway_base_url="http://aigw.test"))
    assert service is not None
    await service.aclose()


async def test_cache_tunables_are_taken_from_settings() -> None:
    settings = Settings(
        aigateway_base_url="http://aigw.test",
        models_cache_ttl_s=11.0,
        models_cache_max_entries=3,
        models_upstream_concurrency=2,
    )
    service = build_catalog_service(settings)
    assert service is not None
    assert service._ttl_s == 11.0  # noqa: SLF001 - asserting the wiring, not behaviour
    assert service._max_entries == 3  # noqa: SLF001
    await service.aclose()


# --- secret hygiene at the settings layer ---------------------------------


async def test_no_setting_holds_an_aigateway_credential() -> None:
    # INVARIANT: r3 introduces no secret. If a future change adds a token setting, this fails and
    # forces the chart's Secret-reference question to be answered deliberately (spec §8).
    suspicious = {
        name
        for name in Settings.model_fields
        if any(word in name for word in ("token", "secret", "key", "password", "credential"))
    }
    assert suspicious == {"jwt_secret", "tavily_secret_name", "tavily_secret_key"}, (
        "a new secret-shaped setting appeared — confirm it is sourced from a Secret reference"
    )


# --- app wiring -----------------------------------------------------------


async def test_create_app_exposes_an_injected_catalog() -> None:
    catalog = FakeCatalog()
    app = create_app(Settings(jwt_secret="s"), bus=InMemoryBus(), catalog=catalog)
    assert app.state.catalog is catalog


async def test_create_app_without_a_catalog_leaves_state_none() -> None:
    app = create_app(Settings(jwt_secret="s"), bus=InMemoryBus())
    assert app.state.catalog is None


async def test_local_app_exposes_an_injected_catalog() -> None:
    # WHY local mode too: the endpoint is a discovery aid, and a laptop run is exactly where a
    # developer wants to see which models are addressable.
    catalog = FakeCatalog()
    app = make_local_app(settings=Settings(jwt_secret="s"), catalog=catalog)
    assert app.state.catalog is catalog


async def test_the_shutdown_hook_closes_the_upstream_client() -> None:
    closed: list[bool] = []

    async def aclose() -> None:
        closed.append(True)

    service = CachedCatalog(FakeCatalog(), source_aclose=aclose)
    await service.aclose()
    assert closed == [True]


async def test_closing_a_service_with_no_client_is_a_noop() -> None:
    await CachedCatalog(FakeCatalog()).aclose()


async def test_the_built_service_closes_its_own_httpx_client() -> None:
    service = build_catalog_service(Settings(aigateway_base_url="http://aigw.test"))
    assert service is not None
    await service.aclose()
    # A second close must not raise — ASGI shutdown can run alongside an explicit close.
    await service.aclose()


# --- metrics --------------------------------------------------------------


async def test_cache_counters_are_exposed_on_the_metrics_endpoint() -> None:
    catalog = build_catalog_service(
        Settings(aigateway_base_url="http://aigw.test"),
        client_factory=lambda _: httpx.AsyncClient(
            base_url="http://aigw.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=BODY)),
        ),
    )
    assert catalog is not None
    app = create_app(Settings(jwt_secret="s"), bus=InMemoryBus(), catalog=catalog)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        await client.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        scrape = await client.get("/metrics")
    body = scrape.text
    assert "url4_cloud_catalog_cache_hits" in body
    assert "url4_cloud_catalog_cache_misses" in body
    assert "url4_cloud_catalog_entries" in body
    await catalog.aclose()


async def test_no_metric_line_ever_carries_a_credential_or_cache_key() -> None:
    # INVARIANT: /metrics is scraped by infrastructure and often widely readable. Labelling by
    # credential or cache key would reintroduce at the metrics endpoint exactly the identity leak
    # the hashed cache key exists to prevent (spec §9).
    catalog = build_catalog_service(
        Settings(aigateway_base_url="http://aigw.test"),
        client_factory=lambda _: httpx.AsyncClient(
            base_url="http://aigw.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=BODY)),
        ),
    )
    assert catalog is not None
    app = create_app(Settings(jwt_secret="s"), bus=InMemoryBus(), catalog=catalog)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        scrape = await client.get("/metrics")
    assert TOKEN not in scrape.text
    assert Credential.derive(TOKEN).key not in scrape.text
    await catalog.aclose()
