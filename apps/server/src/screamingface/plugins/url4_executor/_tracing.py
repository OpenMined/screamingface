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


# OpenInference attribute names (stable spec strings; literals avoid a hard dep
# on openinference-semantic-conventions so this stays no-op without OTel).
# Phoenix reads these to populate its kind / input / output columns.
_OI_KIND = "openinference.span.kind"
_OI_INPUT = "input.value"
_OI_INPUT_MIME = "input.mime_type"
_OI_OUTPUT = "output.value"
_OI_OUTPUT_MIME = "output.mime_type"


def set_openinference(
    kind: str,
    *,
    input_value: str | None = None,
    output_value: str | None = None,
    mime_type: str = "text/plain",
    span: Any = None,
) -> None:
    """Tag the current span with OpenInference semantics (no-op without OTel).

    ``kind`` is an OpenInference span kind ("LLM", "CHAIN", "RETRIEVER", …).
    ``input_value`` / ``output_value`` populate Phoenix's input / output columns.
    """
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if not (span and span.is_recording()):
            return
        span.set_attribute(_OI_KIND, kind)
        if input_value is not None:
            span.set_attribute(_OI_INPUT, input_value)
            span.set_attribute(_OI_INPUT_MIME, mime_type)
        if output_value is not None:
            span.set_attribute(_OI_OUTPUT, output_value)
            span.set_attribute(_OI_OUTPUT_MIME, mime_type)
    except ImportError:
        pass
