"""Public surface and production wiring for Engine model discovery.

Re-exports the hexagonal port (``catalog/port.py``), the aigateway adapter
(``catalog/aigateway.py``), and the caching layer (``catalog/cache.py``), and
provides ``build_catalog_service`` — the composition root that wires one
``AigatewayCatalogSource`` behind a ``CachedCatalog`` for model lists while retaining uncached
model-detail delegation through the same client.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from url4_cloud.catalog.aigateway import AigatewayCatalogSource
from url4_cloud.catalog.cache import CacheCounters, CachedCatalog, CatalogService
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogError,
    CatalogRejected,
    CatalogSource,
    CatalogUnavailable,
    Credential,
    ModelCatalog,
    ModelParameterBadResponse,
    ModelParameterResponse,
    ModelParameterSource,
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
    source = AigatewayCatalogSource(client)
    return CachedCatalog(
        source,
        parameter_source=source,
        ttl_s=settings.models_cache_ttl_s,
        stale_max_s=settings.models_cache_stale_max_s,
        error_backoff_s=settings.models_cache_error_backoff_s,
        max_entries=settings.models_cache_max_entries,
        upstream_concurrency=settings.models_upstream_concurrency,
        source_aclose=client.aclose,
    )


__all__ = [
    "AigatewayCatalogSource",
    "CacheCounters",
    "CachedCatalog",
    "CatalogBadResponse",
    "CatalogError",
    "CatalogRejected",
    "CatalogService",
    "CatalogSource",
    "CatalogUnavailable",
    "Credential",
    "ModelCatalog",
    "ModelParameterBadResponse",
    "ModelParameterResponse",
    "ModelParameterSource",
    "build_catalog_service",
    "compute_etag",
]
