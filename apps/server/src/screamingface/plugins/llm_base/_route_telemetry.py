"""OTEL recording helpers used by the shared backend-API router.

Pulled out of ``routes_shared.py`` during SF-133 so the router factory
stays focused on FastAPI wiring. Each helper is a no-op when OTEL
isn't importable or when there's no recording span on the context.
"""

from __future__ import annotations

import json
from typing import Any

from screamingface.plugins.backend_api_base.models import RunRequest
from screamingface.plugins.llm_base.constants import (
    CLI_ONLY_FIELDS,
    PROMPT_PREVIEW_LIMIT,
    STDOUT_PREVIEW_LIMIT,
)
from screamingface.plugins.llm_base.messages import CoreMessage


def record_ignored_fields(request: RunRequest, plugin_name: str) -> None:
    """Record which CLI-only fields were present on an OTEL span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return

    attr_prefix = plugin_name.replace("-", "_")
    for field_name in CLI_ONLY_FIELDS:
        value = getattr(request, field_name, None)
        if value:  # truthy — non-empty list/str or True
            span.set_attribute(f"{attr_prefix}.ignored_field.{field_name}", True)


def record_span_success(
    result: CoreMessage,
    duration: float,
    stdout: str,
    plugin_name: str,
    span_prefix: str,
) -> None:
    """Record success-path attributes on the current OTEL span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return

    span.set_attribute("sf.plugin", plugin_name)
    span.set_attribute(f"{span_prefix}.exit_code", 0)
    span.set_attribute(f"{span_prefix}.duration_seconds", round(duration, 3))
    span.set_attribute(f"{span_prefix}.stdout_length", len(stdout))
    preview = stdout[:STDOUT_PREVIEW_LIMIT]
    if len(stdout) > STDOUT_PREVIEW_LIMIT:
        preview += f"\n... ({len(stdout) - STDOUT_PREVIEW_LIMIT} more chars)"
    span.set_attribute(f"{span_prefix}.stdout_preview", preview)

    if result.provider_metadata:
        for key, value in result.provider_metadata.items():
            try:
                span.set_attribute(key, _otel_attr_value(value))
            except Exception:
                pass


def record_url4_span(q: str, result: str, plugin_name: str) -> None:
    """Record url4-endpoint attributes on the current OTEL span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return

    span.set_attribute("sf.plugin", plugin_name)
    span.set_attribute("url4.expression", q[:500])
    span.set_attribute("url4.result_length", len(result))
    preview = result[:PROMPT_PREVIEW_LIMIT]
    if len(result) > PROMPT_PREVIEW_LIMIT:
        preview += f"\n... ({len(result) - PROMPT_PREVIEW_LIMIT} more chars)"
    span.set_attribute("url4.response_body", preview)


def _otel_attr_value(value: Any) -> Any:
    """Coerce a value to something OTEL spans accept."""
    if isinstance(value, str | bool | int | float):
        return value
    return json.dumps(value)
