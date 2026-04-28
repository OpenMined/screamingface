"""OTEL tracing helper for the final Ollama request body.

Walks the body and emits one span per message, annotated with role,
content length / preview, and tool-call count. Pulled out of
``proxy.py`` during SF-132. Mirrors the SF-131 split for
claude_frontend.
"""

from __future__ import annotations

from typing import Any

from screamingface.plugins.frontend_base import truncate


def trace_request_context(body: dict[str, Any], tracer: Any) -> None:
    """Record request-level attributes and per-message child spans."""
    if not tracer.enabled:
        return

    messages = body.get("messages", [])
    tracer.set_attrs(
        {
            "ollama.model": body.get("model", "?"),
            "ollama.stream": body.get("stream", True),
            "ollama.messages_count": len(messages),
            "ollama.has_tools": bool(body.get("tools")),
        }
    )

    for i, msg in enumerate(messages):
        role = msg.get("role", "?") if isinstance(msg, dict) else "?"
        with tracer.start_current_span(f"message[{i}] {role}") as span:
            tracer.set_attrs({"role": role}, span=span)
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    tracer.set_attrs(
                        {"content_length": len(content), "content": truncate(content, limit=1000)},
                        span=span,
                    )
                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    tracer.set_attrs({"tool_calls_count": len(tool_calls)}, span=span)
