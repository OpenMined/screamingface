"""Composition root for the model-catalog port (spec §6.4).

FEATURE: model-catalog discovery. ``create_app`` stays purely dependency-injected (tests hand it
fakes); this module is the ONE place that turns ``Settings`` into a live, cached, aigateway-backed
service — so prod and local mode share a single wiring path.

INVARIANT: there is no credential to configure. The catalog endpoint forwards the CALLER's
credential upstream, so ``aigateway_base_url`` is the only precondition and url4-cloud stores no
aigateway secret of its own (spec D2).
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
    compute_etag,
)
from url4_cloud.config import Settings

# WHY a short timeout: this is a synchronous dependency of an interactive request, and the cache
# already absorbs the cost of a miss. Blocking a client on a wedged upstream is strictly worse
# than a fast 504 it can retry.
_UPSTREAM_TIMEOUT_S = 10.0


def _default_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=_UPSTREAM_TIMEOUT_S)


def build_catalog_service(
    settings: Settings,
    *,
    client_factory: Callable[[str], httpx.AsyncClient] = _default_client,
) -> CachedCatalog | None:
    """Return the cached catalog service, or ``None`` when aigateway is not configured.

    INVARIANT: total over the configuration space, mirroring
    :func:`~url4_cloud.jobs.factory.build_job_runner`'s "unconfigured ⇒ ``None``" contract — which
    the route turns into a 503 rather than letting a ``None`` raise ``AttributeError`` (500).

    ``client_factory`` is injectable so this composition path is testable headless; importing this
    module must never open a socket.
    """
    # WHY a local: it narrows `str | None` to `str` for the type checker across the guard, so
    # the client factory needs no assert or cast.
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
    "build_catalog_service",
    "compute_etag",
]
