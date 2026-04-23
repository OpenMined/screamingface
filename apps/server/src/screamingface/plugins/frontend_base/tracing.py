"""Plugin-scoped OTEL tracer wrapper and log-redaction helpers.

A :class:`ProxyTracer` bundles the plugin name + an OTEL tracer handle
into one object with friendly methods. Every frontend gets one at
router-create time:

.. code-block:: python

    tracer = make_tracer("claude-frontend")

    with tracer.start_client_span("POST /v1/messages") as span:
        tracer.set_attrs({"http.method": "POST"}, span=span)
        ...

Every method silently no-ops when OTEL isn't installed, so test
environments without the opentelemetry packages still import cleanly.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager, nullcontext
from typing import Any

from screamingface.plugins.llm_base.constants import PROMPT_PREVIEW_LIMIT

__all__ = ["ProxyTracer", "make_tracer", "redact_headers", "truncate"]


def truncate(text: str, limit: int = PROMPT_PREVIEW_LIMIT) -> str:
    """Cap ``text`` at ``limit`` and append a count footer when clipped."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more chars)"


def redact_headers(
    headers: dict[str, str],
    sensitive: Iterable[str],
    *,
    prefix_keep: int = 8,
) -> dict[str, str]:
    """Mask values of ``sensitive`` header names in a copy of ``headers``.

    Case-insensitive match. Values that are shorter than ``prefix_keep``
    are left unchanged (no point masking a short value).
    """
    sensitive_lower = {s.lower() for s in sensitive}
    return {
        k: (v[:prefix_keep] + "…" if k.lower() in sensitive_lower and len(v) > prefix_keep else v)
        for k, v in headers.items()
    }


class ProxyTracer:
    """Plugin-scoped OTEL tracer wrapper.

    ``plugin_name`` is used as both the tracer name suffix (so traces
    group by plugin) and as the ``sf.plugin`` attribute auto-added to
    every span touched via :meth:`set_attrs`.

    When OpenTelemetry isn't importable, every method is a no-op that
    still yields a context manager / returns ``None`` — callers don't
    need to branch on whether tracing is enabled.
    """

    def __init__(self, plugin_name: str) -> None:
        self._plugin = plugin_name
        self._tracer = self._resolve_tracer(plugin_name)

    @staticmethod
    def _resolve_tracer(plugin_name: str) -> Any:
        try:
            from opentelemetry import trace
        except ImportError:
            return None
        return trace.get_tracer(f"screamingface.{plugin_name}")

    @property
    def enabled(self) -> bool:
        return self._tracer is not None

    # ------------------------------------------------------------------
    # Span helpers
    # ------------------------------------------------------------------

    @contextmanager
    def start_current_span(self, name: str) -> Any:
        """Open a span as the current span for the ``with`` block."""
        if self._tracer is None:
            with nullcontext() as span:
                yield span
            return
        with self._tracer.start_as_current_span(name) as span:
            yield span

    @contextmanager
    def start_client_span(self, name: str) -> Any:
        """Open a CLIENT-kind span as the current span."""
        if self._tracer is None:
            with nullcontext() as span:
                yield span
            return
        from opentelemetry.trace import SpanKind

        with self._tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
            yield span

    def start_client_span_detached(self, name: str) -> Any:
        """Start a CLIENT-kind span without making it current.

        Returns the span (caller must ``.end()`` when done) or ``None``
        when OTEL is unavailable.
        """
        if self._tracer is None:
            return None
        from opentelemetry.trace import SpanKind

        return self._tracer.start_span(name, kind=SpanKind.CLIENT)

    # ------------------------------------------------------------------
    # Attribute helpers
    # ------------------------------------------------------------------

    def set_attrs(self, attrs: dict[str, Any], *, span: Any = None) -> None:
        """Record attributes on ``span`` (or the current span).

        Auto-adds ``sf.plugin`` = the plugin name so every frontend's
        spans carry that tag without the caller having to remember.
        """
        target = self._resolve_span(span)
        if target is None:
            return
        target.set_attribute("sf.plugin", self._plugin)
        for k, v in attrs.items():
            target.set_attribute(k, v)

    def set_headers(
        self,
        prefix: str,
        headers: dict[str, str],
        *,
        span: Any = None,
    ) -> None:
        """Record ``{prefix}.<header-name>`` attributes for each header."""
        target = self._resolve_span(span)
        if target is None:
            return
        for k, v in headers.items():
            target.set_attribute(f"{prefix}.{k}", v)

    def record_trace_id(self, trace_id: str | None) -> None:
        """Record ``sf.trace_id`` on the current span if present."""
        if trace_id:
            self.set_attrs({"sf.trace_id": trace_id})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_span(span: Any) -> Any:
        if span is not None:
            return span if getattr(span, "is_recording", lambda: False)() else None
        try:
            from opentelemetry import trace
        except ImportError:
            return None
        current = trace.get_current_span()
        return current if current and current.is_recording() else None


def make_tracer(plugin_name: str) -> ProxyTracer:
    """Build a :class:`ProxyTracer` for ``plugin_name``."""
    return ProxyTracer(plugin_name)
