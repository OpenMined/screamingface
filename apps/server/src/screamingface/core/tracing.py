"""Lightweight tracing utilities — no-op safe when OpenTelemetry is absent."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class _NoOpSpan:
    """Fallback when opentelemetry is not installed."""

    __slots__ = ()

    def set_attribute(self, *a: Any, **kw: Any) -> None:
        pass

    def record_exception(self, *a: Any, **kw: Any) -> None:
        pass

    def set_status(self, *a: Any, **kw: Any) -> None:
        pass

    def add_event(self, *a: Any, **kw: Any) -> None:
        pass

    def end(self, *a: Any, **kw: Any) -> None:
        pass

    def is_recording(self) -> bool:
        return False


_NOOP = _NoOpSpan()


def get_tracer(name: str = "screamingface.proxy") -> Any | None:
    """Return an OpenTelemetry tracer, or ``None`` if OTel is unavailable."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return None


def current_span() -> Any:
    """Return the active span, or a no-op stub if OTel is unavailable."""
    try:
        from opentelemetry import trace

        return trace.get_current_span()
    except ImportError:
        return _NOOP


def set_span_headers(span: Any, prefix: str, headers: dict[str, str]) -> None:
    """Set each header as a prefixed span attribute."""
    for k, v in headers.items():
        span.set_attribute(f"{prefix}.{k}", v)


@asynccontextmanager
async def traced_http(
    method: str,
    url: str,
    *,
    request_headers: dict[str, str] | None = None,
    request_body: str | None = None,
    trace_id: str | None = None,
) -> AsyncIterator[Any]:
    """Create a CLIENT span, record request attrs, yield the span.

    Works for both streaming (inside async generators) and non-streaming.
    Yields a no-op stub when tracing is unavailable — all span calls become
    silent no-ops.
    """
    tracer = get_tracer()
    if tracer is None:
        yield _NOOP
        return

    from opentelemetry.trace import SpanKind, Status, StatusCode

    span = tracer.start_span(f"{method} {url}", kind=SpanKind.CLIENT)
    span.set_attribute("http.method", method)
    span.set_attribute("http.url", url)
    if trace_id:
        span.set_attribute("sf.trace_id", trace_id)
    if request_body is not None:
        span.set_attribute("request.body", request_body)
    if request_headers is not None:
        set_span_headers(span, "request.headers", request_headers)
    try:
        yield span
    except BaseException as exc:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
        raise
    finally:
        span.end()
