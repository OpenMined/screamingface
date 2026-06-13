"""Optional OTel HTTP-client tracing helpers for backend plugins.

All functions are no-ops when opentelemetry is not installed, so backend
modules can call them unconditionally. Mirrors
``url4_executor/_tracing.py`` but parametrized by provider so each span
carries the real provider identity (Anthropic, gemini, ollama, aigw, …).

Lives in ``llm_base`` (the lowest backend layer) on purpose: ``frontend_base``
already imports ``llm_base.constants``, so ``llm_base`` must not depend on
``frontend_base``. ``aigw_base`` already depends on ``llm_base`` and reuses
these helpers.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any

_TRACER_NAME = "screamingface.llm-base"


def _get_tracer():  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        return trace.get_tracer(_TRACER_NAME)
    except ImportError:
        return None


@contextmanager
def traced_provider_post(provider: str, url: str, *, method: str = "POST"):  # type: ignore[no-untyped-def]
    """Open a CLIENT span ``llm.{method} {provider}`` for an outbound POST.

    Yields the span (or ``None`` without OTel) so callers can record
    response attributes via :func:`set_provider_attrs`. Exceptions raised
    inside the ``with`` are recorded on the span by OTel on context exit.
    """
    tracer = _get_tracer()
    if tracer is None:
        with nullcontext() as span:
            yield span
        return
    from opentelemetry.trace import SpanKind

    with tracer.start_as_current_span(f"llm.{method} {provider}", kind=SpanKind.CLIENT) as span:
        if span.is_recording():
            span.set_attribute("sf.plugin", provider)
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", url[:500])
        yield span


def set_provider_attrs(attrs: dict[str, Any], span: Any = None) -> None:
    """Set attributes on the current (or provided) span; no-op without OTel.

    ``None`` values are skipped — OTel rejects ``None`` attribute values.
    """
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if span and span.is_recording():
            for k, v in attrs.items():
                if v is not None:
                    span.set_attribute(k, v)
    except ImportError:
        pass
