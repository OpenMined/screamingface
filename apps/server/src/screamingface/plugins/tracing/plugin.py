"""Tracing plugin — lightweight local observability via OpenTelemetry + Phoenix."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class TracingSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_TRACING__",
        env_nested_delimiter="__",
    )
    service_name: str = "screamingface"
    exporter: str = "phoenix"  # "phoenix" | "console" | "otlp"
    otlp_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_port: int = 6006
    phoenix_launch: bool = True  # auto-launch Phoenix as background thread


class TracingPlugin(Plugin):
    name = "tracing"
    description = "Lightweight local tracing via OpenTelemetry + Phoenix"
    settings_class = TracingSettings

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason
        try:
            import opentelemetry  # noqa: F401
        except ImportError:
            return False, ("OpenTelemetry not installed. Run: uv sync --extra tracing")
        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: TracingSettings = self.settings  # type: ignore[assignment]

        self._phoenix_session = None
        self._provider = None

        # 1. Launch Phoenix if requested
        if settings.exporter == "phoenix" and settings.phoenix_launch:
            try:
                import os
                import socket

                phoenix_port = settings.phoenix_port

                # Disable Phoenix's gRPC server — we only need HTTP OTLP
                os.environ.setdefault("PHOENIX_GRPC_PORT", "0")

                # Kill any stale Phoenix process on the target port
                # (can happen after uvicorn reloader kills the child process)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    port_in_use = s.connect_ex(("127.0.0.1", phoenix_port)) == 0
                # Socket is now closed — lsof won't see this process
                if port_in_use:
                    logger.info("Port %d in use — killing stale Phoenix", phoenix_port)
                    import subprocess

                    my_pid = os.getpid()
                    result = subprocess.run(
                        ["lsof", "-ti", f"tcp:{phoenix_port}"],
                        capture_output=True,
                        text=True,
                    )
                    for pid_str in result.stdout.strip().split("\n"):
                        pid_str = pid_str.strip()
                        if not pid_str:
                            continue
                        try:
                            pid = int(pid_str)
                            if pid == my_pid:
                                continue  # Never kill ourselves
                            os.kill(pid, 9)
                        except (ProcessLookupError, ValueError):
                            pass
                    import time

                    time.sleep(0.5)

                os.environ["PHOENIX_PORT"] = str(phoenix_port)

                import phoenix as px

                self._phoenix_session = px.launch_app(run_in_thread=True)
                phoenix_url = getattr(
                    self._phoenix_session, "url", f"http://localhost:{phoenix_port}"
                )
                logger.info("Phoenix UI available at %s", phoenix_url)

                # Update OTLP endpoint to match the actual Phoenix port
                settings.otlp_endpoint = f"http://localhost:{phoenix_port}/v1/traces"

                # Safety net: close Phoenix on process exit even if shutdown hook doesn't fire
                import atexit

                atexit.register(self._stop_phoenix)
            except Exception:
                logger.warning(
                    "Failed to launch Phoenix — spans will still be exported",
                    exc_info=True,
                )

        # 2. Configure OTEL TracerProvider with a filtering processor
        #    that drops noisy ASGI http send/receive child spans.
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SpanExporter

        resource = Resource.create({"service.name": settings.service_name})
        provider = TracerProvider(resource=resource)

        span_exporter: SpanExporter | None = None
        if settings.exporter in ("phoenix", "otlp"):
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            span_exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
            provider.add_span_processor(_FilteringSpanProcessor(BatchSpanProcessor(span_exporter)))
            logger.info("OTEL exporting to %s", settings.otlp_endpoint)
        elif settings.exporter == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

            span_exporter = ConsoleSpanExporter()
            provider.add_span_processor(_FilteringSpanProcessor(SimpleSpanProcessor(span_exporter)))
            logger.info("OTEL exporting to console")

        trace.set_tracer_provider(provider)
        self._provider = provider

        # Store tracer on app state so proxy can create custom spans
        app.state.otel_tracer = trace.get_tracer(settings.service_name)

        # 3. Auto-instrument FastAPI (httpx spans are created manually in the proxy)
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            server_request_hook=_server_request_hook,
        )

        # Ensure httpx auto-instrumentation is disabled — we create manual spans
        # in the proxy with full body/header visibility instead.
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().uninstrument()
        except Exception:
            pass

        logger.info("FastAPI auto-instrumented with OpenTelemetry")

        # 4. Register shutdown hook
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)

    def _stop_phoenix(self) -> None:
        if self._phoenix_session is not None:
            try:
                self._phoenix_session.close()
                logger.info("Phoenix session closed")
            except Exception:
                logger.debug("Phoenix session close failed", exc_info=True)
            self._phoenix_session = None

    async def _on_shutdown(self) -> None:
        if self._provider:
            self._provider.shutdown()
            logger.info("OTEL TracerProvider shut down")
        self._stop_phoenix()

    def teardown(self) -> None:
        if self._provider:
            self._provider.shutdown()
        self._stop_phoenix()


class _FilteringSpanProcessor:
    """Wraps a SpanProcessor and drops spans whose names contain 'http send' or 'http receive'."""

    def __init__(self, inner) -> None:  # type: ignore[no-untyped-def]
        self._inner = inner

    def on_start(self, span, parent_context=None) -> None:  # type: ignore[no-untyped-def]
        self._inner.on_start(span, parent_context)

    def _on_ending(self, span) -> None:  # type: ignore[no-untyped-def]
        if hasattr(self._inner, "_on_ending"):
            self._inner._on_ending(span)

    def on_end(self, span) -> None:  # type: ignore[no-untyped-def]
        name = span.name
        if "http send" in name or "http receive" in name:
            return  # drop — noisy ASGI per-message spans
        # Drop health check spans
        if span.attributes and span.attributes.get("_sf.internal"):
            return
        self._inner.on_end(span)

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return self._inner.force_flush(timeout_millis)


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... ({len(text) - limit} more chars)"


def _server_request_hook(span, scope) -> None:  # type: ignore[no-untyped-def]
    """Add useful attributes to the server span from the ASGI scope."""
    if not span or not span.is_recording():
        return
    path = scope.get("path", "")
    if path == "/health":
        # Mark as internal so the filtering processor can drop it
        span.set_attribute("_sf.internal", True)
        return
    qs = scope.get("query_string", b"")
    if qs:
        span.set_attribute("http.query_string", qs.decode(errors="replace"))
