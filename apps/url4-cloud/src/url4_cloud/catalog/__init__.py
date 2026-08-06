"""Public surface of the model-catalog subsystem.

Re-exports the hexagonal port (``catalog/port.py``), the aigateway adapter
(``catalog/aigateway.py``), and the caching layer (``catalog/cache.py``), and
provides raw Gateway builders plus the Engine composition builders that project discovery and
model details onto its declared executable routes.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from url4_cloud.catalog.aigateway import AigatewayCatalogSource, AigatewayModelDetailsSource
from url4_cloud.catalog.cache import CacheCounters, CachedCatalog, CatalogService
from url4_cloud.catalog.executable import ExecutableCatalog, ExecutableModelDetailsSource
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogError,
    CatalogRejected,
    CatalogSource,
    CatalogUnavailable,
    Credential,
    ModelCatalog,
    ModelDetails,
    ModelDetailsError,
    ModelDetailsNotInstalled,
    ModelDetailsSource,
    ModelDetailsUnavailable,
    compute_etag,
)
from url4_cloud.config import Settings

_UPSTREAM_TIMEOUT_S = 10.0


def _default_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=_UPSTREAM_TIMEOUT_S)


def build_catalog_service(
    settings: Settings,
    *,
    client_factory: Callable[[str], httpx.AsyncClient] = _default_client,
) -> CachedCatalog | None:
    """Wire the aigateway-backed, cached catalog service from ``settings``.

    Returns None when no aigateway base URL is configured, matching the 503
    "not configured" response `rest/catalog.py` raises for that case.
    """
    base_url = settings.aigateway_base_url
    if not base_url:
        return None
    client = client_factory(base_url)
    return CachedCatalog(
        AigatewayCatalogSource(client),
        ttl_s=settings.models_cache_ttl_s,
        stale_max_s=settings.models_cache_stale_max_s,
        error_backoff_s=settings.models_cache_error_backoff_s,
        max_entries=settings.models_cache_max_entries,
        upstream_concurrency=settings.models_upstream_concurrency,
        source_aclose=client.aclose,
    )


def build_model_details_source(
    settings: Settings,
    *,
    client_factory: Callable[[str], httpx.AsyncClient] = _default_client,
) -> AigatewayModelDetailsSource | None:
    """Wire the uncached, profile-bound AI Gateway model-details adapter."""

    base_url = settings.aigateway_base_url
    if not base_url:
        return None
    return AigatewayModelDetailsSource(client_factory(base_url))


def build_executable_catalog_service(
    settings: Settings,
    model_ids: frozenset[str],
    *,
    client_factory: Callable[[str], httpx.AsyncClient] = _default_client,
) -> ExecutableCatalog | None:
    """Wire caller-scoped Gateway discovery through the Engine's declared route set."""

    source = build_catalog_service(settings, client_factory=client_factory)
    return None if source is None else ExecutableCatalog(source, model_ids)


def build_executable_model_details_source(
    settings: Settings,
    model_ids: frozenset[str],
    *,
    client_factory: Callable[[str], httpx.AsyncClient] = _default_client,
) -> ExecutableModelDetailsSource | None:
    """Wire model details through the same Engine route-set guard as discovery."""

    source = build_model_details_source(settings, client_factory=client_factory)
    return None if source is None else ExecutableModelDetailsSource(source, model_ids)


__all__ = [
    "AigatewayCatalogSource",
    "AigatewayModelDetailsSource",
    "CacheCounters",
    "CachedCatalog",
    "CatalogBadResponse",
    "CatalogError",
    "CatalogRejected",
    "CatalogService",
    "CatalogSource",
    "CatalogUnavailable",
    "Credential",
    "ExecutableCatalog",
    "ExecutableModelDetailsSource",
    "ModelCatalog",
    "ModelDetails",
    "ModelDetailsError",
    "ModelDetailsNotInstalled",
    "ModelDetailsSource",
    "ModelDetailsUnavailable",
    "build_catalog_service",
    "build_executable_catalog_service",
    "build_executable_model_details_source",
    "build_model_details_source",
    "compute_etag",
]
