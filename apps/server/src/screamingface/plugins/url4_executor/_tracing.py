"""Optional OTel tracing helpers for url4-executor.

All functions are no-ops when opentelemetry is not installed.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

_PLUGIN = "url4-executor"


def _get_tracer():  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        return trace.get_tracer(f"screamingface.{_PLUGIN}")
    except ImportError:
        return None


def traced(name: str, kind: str = "internal"):  # type: ignore[no-untyped-def]
    """Return a span context manager, or nullcontext if OTel not available."""
    tracer = _get_tracer()
    if not tracer:
        return nullcontext()
    from opentelemetry.trace import SpanKind

    kind_map = {
        "internal": SpanKind.INTERNAL,
        "client": SpanKind.CLIENT,
        "server": SpanKind.SERVER,
    }
    return tracer.start_as_current_span(name, kind=kind_map.get(kind, SpanKind.INTERNAL))


def set_span_attrs(attrs: dict[str, Any], span: Any = None) -> None:
    """Set attributes on the current or provided span (no-op without OTel)."""
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("sf.plugin", _PLUGIN)
            for k, v in attrs.items():
                span.set_attribute(k, v)
    except ImportError:
        pass
