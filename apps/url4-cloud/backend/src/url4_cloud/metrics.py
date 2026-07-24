"""OpenMetrics instrumentation (docs/protocol.md §9).

A per-app :class:`prometheus_client.CollectorRegistry` (never the process-global default) so
building several apps in one test process cannot raise a duplicate-timeseries error and each app's
counters stay isolated. :class:`MetricsMiddleware` is a pure-ASGI shim (not ``BaseHTTPMiddleware``)
so it never buffers responses or perturbs the WebSocket/streaming paths — it only bumps a counter
on ``http.response.start``.
"""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter
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
