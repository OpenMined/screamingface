"""Prometheus/OpenMetrics wiring for the url4-cloud App: a per-request counter middleware and a
custom collector that surfaces the model-catalog cache counters at scrape time."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from prometheus_client import CollectorRegistry, Counter
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(frozen=True)
class Metrics:
    """The App's private Prometheus registry and metric handles, held on `app.state.metrics`.

    Uses a per-instance `CollectorRegistry` rather than the global default one so multiple
    `create_app()` calls (e.g. across tests) don't collide on duplicate metric registration.
    """

    registry: CollectorRegistry
    requests: Counter


def build_metrics() -> Metrics:
    registry = CollectorRegistry()
    requests = Counter(
        "url4_cloud_requests",
        "HTTP requests handled by the url4-cloud control plane.",
        ["method", "path", "status"],
        registry=registry,
    )
    return Metrics(registry=registry, requests=requests)


class MetricsMiddleware:
    """ASGI middleware that increments `Metrics.requests`, labeled by method/path/status, for
    every HTTP response the App sends."""

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
    """Best-effort lookup of `Metrics` off the ASGI scope's app state; None if unset or the wrong
    type (e.g. a bare test double without `create_app`'s wiring)."""
    app = scope.get("app")
    state = getattr(app, "state", None)
    metrics = getattr(state, "metrics", None)
    return metrics if isinstance(metrics, Metrics) else None


class _CatalogCollector:
    """A `prometheus_client` custom collector that exposes the catalog service's cache counters."""

    def __init__(self, get_service: Callable[[], Any]) -> None:
        self._get_service = get_service

    def collect(self) -> Iterable[Any]:
        """Called by `prometheus_client` once per `/metrics` scrape."""
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
    """Register a `_CatalogCollector` for `get_service` on `metrics.registry`."""
    metrics.registry.register(_CatalogCollector(get_service))
