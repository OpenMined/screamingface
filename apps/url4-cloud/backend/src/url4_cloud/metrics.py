"""OpenMetrics instrumentation (docs/protocol.md §9).

A per-app :class:`prometheus_client.CollectorRegistry` (never the process-global default) so
building several apps in one test process cannot raise a duplicate-timeseries error and each app's
counters stay isolated. :class:`MetricsMiddleware` is a pure-ASGI shim (not ``BaseHTTPMiddleware``)
so it never buffers responses or perturbs the WebSocket/streaming paths — it only bumps a counter
on ``http.response.start``.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from prometheus_client import CollectorRegistry, Counter
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(frozen=True)
class Metrics:
    """The app's isolated metric registry + the counters exposed at ``/metrics``."""

    registry: CollectorRegistry
    requests: Counter


def build_metrics() -> Metrics:
    """Create a fresh registry with the HTTP request counter."""
    registry = CollectorRegistry()
    requests = Counter(
        "url4_cloud_requests",
        "HTTP requests handled by the url4-cloud control plane.",
        ["method", "path", "status"],
        registry=registry,
    )
    return Metrics(registry=registry, requests=requests)


class MetricsMiddleware:
    """Count every HTTP response by method/path/status; non-HTTP scopes pass straight through."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", ""))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                metrics = _metrics_of(scope)
                if metrics is not None:
                    status = str(message.get("status", 0))
                    metrics.requests.labels(method=method, path=path, status=status).inc()
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _metrics_of(scope: Scope) -> Metrics | None:
    app = scope.get("app")
    state = getattr(app, "state", None)
    metrics = getattr(state, "metrics", None)
    return metrics if isinstance(metrics, Metrics) else None


class _CatalogCollector:
    """Reads the catalog cache's counters at SCRAPE time (spec §9).

    WHY a collector rather than ``Counter.inc()`` calls inside the cache: the cache keeps plain
    ints so its own tests need no registry, and pulling at scrape time cannot double-count or
    drift from the real values.

    INVARIANT: no metric here carries a label. ``/metrics`` is scraped by infrastructure and is
    often widely readable, so labelling by credential or cache key would reintroduce at the metrics
    endpoint exactly the identity leak the hashed cache key exists to prevent.
    """

    def __init__(self, get_service: Callable[[], Any]) -> None:
        self._get_service = get_service

    def collect(self) -> Iterable[Any]:
        service = self._get_service()
        counters = getattr(service, "counters", None)
        if counters is None:
            return
        yield CounterMetricFamily(
            "url4_cloud_catalog_cache_hits",
            "Catalog served from a fresh cache entry.",
            value=counters.hits,
        )
        yield CounterMetricFamily(
            "url4_cloud_catalog_cache_misses",
            "Catalog fetched from aigateway.",
            value=counters.misses,
        )
        yield CounterMetricFamily(
            "url4_cloud_catalog_stale_serves",
            "Stale catalog served because a refresh failed.",
            value=counters.stale_serves,
        )
        yield CounterMetricFamily(
            "url4_cloud_catalog_errors",
            "Upstream catalog fetches that failed.",
            value=counters.errors,
        )
        yield CounterMetricFamily(
            "url4_cloud_catalog_bulkhead_waits",
            "Catalog fetches that waited on the upstream concurrency bulkhead.",
            value=counters.bulkhead_waits,
        )
        yield GaugeMetricFamily(
            "url4_cloud_catalog_entries",
            "Cached catalog entries currently held.",
            value=float(getattr(service, "entry_count", 0)),
        )


def register_catalog_metrics(metrics: Metrics, get_service: Callable[[], Any]) -> None:
    """Expose the catalog cache's counters on ``metrics.registry``.

    ``get_service`` is read lazily so an app whose catalog is injected after build still reports,
    and an app with no catalog simply contributes no series.
    """
    metrics.registry.register(_CatalogCollector(get_service))
