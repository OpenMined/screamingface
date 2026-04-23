"""frontend-base — shared tracing + redaction helpers for proxy plugins.

Every ``*_frontend`` plugin (``claude_frontend``, ``codex_frontend``,
``gemini_frontend``, ``ollama_frontend``) proxies a provider's API and
each copy-pasted the same seven helpers:

- ``_redact_headers`` — mask sensitive auth headers in spans/logs.
- ``_truncate`` — cap strings sent to OTEL span attributes at a fixed
  byte budget.
- ``_get_tracer`` / ``_set_span_attrs`` / ``_set_span_headers`` /
  ``_start_client_span`` / ``_start_client_span_detached`` — a plugin-
  scoped tracer wrapper that silently no-ops when OTEL isn't installed.

This module owns those helpers once. The sensitive-header set and the
plugin name are parameters, so each frontend passes its own values.

Plugin-agnostic — no routes, no settings, no hooks. Lives as an SF
plugin only so other plugins can declare ``depends = ["frontend-base"]``.
"""

from __future__ import annotations

from screamingface.plugins.frontend_base.tracing import (
    ProxyTracer,
    make_tracer,
    redact_headers,
    truncate,
)

__all__ = [
    "ProxyTracer",
    "make_tracer",
    "redact_headers",
    "truncate",
]
