"""OTEL tracing helper for the final Anthropic request body.

Walks the body and emits one span per system block and per message,
each annotated with type-specific attributes (text length / preview,
tool_use input, tool_result content, thinking content, etc.).

Pulled out of ``proxy.py`` during SF-131. The caller passes a
:class:`frontend_base.ProxyTracer` so this module has no direct OTEL
dependency.
"""

from __future__ import annotations

import json
from typing import Any

from screamingface.plugins.frontend_base import truncate


def trace_request_context(body: dict[str, Any], tracer: Any) -> None:
    """Create child spans for each system block and message in the final request."""
    if not tracer.enabled:
        return

    tracer.set_attrs(
        {
            "anthropic.model": body.get("model", "?"),
            "anthropic.max_tokens": body.get("max_tokens", 0),
            "anthropic.stream": body.get("stream", False),
            "anthropic.system_block_count": len(body.get("system", []))
            if isinstance(body.get("system"), list)
            else (1 if body.get("system") else 0),
            "anthropic.message_count": len(body.get("messages", [])),
        }
    )

    _trace_system(body.get("system"), tracer)
    _trace_messages(body.get("messages", []), tracer)


def _trace_system(system: Any, tracer: Any) -> None:
    if isinstance(system, list):
        for i, block in enumerate(system):
            with tracer.start_current_span(f"system[{i}]") as span:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    attrs: dict[str, Any] = {
                        "type": block.get("type", "?"),
                        "text_length": len(text),
                        "text": truncate(text, limit=1000),
                    }
                    if "cache_control" in block:
                        attrs["cache_control"] = str(block["cache_control"])
                    tracer.set_attrs(attrs, span=span)
    elif isinstance(system, str):
        with tracer.start_current_span("system") as span:
            tracer.set_attrs(
                {"text_length": len(system), "text": truncate(system, limit=1000)},
                span=span,
            )


def _trace_messages(messages: list[Any], tracer: Any) -> None:
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        with tracer.start_current_span(f"message[{i}] {role}") as span:
            tracer.set_attrs({"role": role}, span=span)
            content = msg.get("content")
            if isinstance(content, str):
                tracer.set_attrs(
                    {"content_length": len(content), "content": truncate(content, limit=1000)},
                    span=span,
                )
            elif isinstance(content, list):
                tracer.set_attrs({"block_count": len(content)}, span=span)
                for j, block in enumerate(content):
                    btype = block.get("type", "?") if isinstance(block, dict) else "?"
                    block_attrs: dict[str, Any] = {f"block[{j}].type": btype}
                    if btype == "text":
                        text = block.get("text", "")
                        block_attrs[f"block[{j}].text_length"] = len(text)
                        block_attrs[f"block[{j}].text"] = truncate(text, limit=1000)
                    elif btype == "thinking":
                        thinking = block.get("thinking", "")
                        block_attrs[f"block[{j}].thinking_length"] = len(thinking)
                        block_attrs[f"block[{j}].thinking"] = truncate(thinking, limit=1000)
                        block_attrs[f"block[{j}].has_signature"] = "signature" in block
                    elif btype == "tool_use":
                        block_attrs[f"block[{j}].tool_name"] = block.get("name", "?")
                        block_attrs[f"block[{j}].tool_id"] = block.get("id", "?")
                        inp = json.dumps(block.get("input", {}))
                        block_attrs[f"block[{j}].input"] = truncate(inp, limit=1000)
                    elif btype == "tool_result":
                        block_attrs[f"block[{j}].tool_use_id"] = block.get("tool_use_id", "?")
                        block_attrs[f"block[{j}].is_error"] = block.get("is_error", False)
                        rc = block.get("content", "")
                        if isinstance(rc, str):
                            block_attrs[f"block[{j}].content"] = truncate(rc, limit=1000)
                        elif isinstance(rc, list):
                            block_attrs[f"block[{j}].content"] = truncate(
                                json.dumps(rc), limit=1000
                            )
                    tracer.set_attrs(block_attrs, span=span)
