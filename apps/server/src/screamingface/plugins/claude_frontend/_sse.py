"""Anthropic Messages SSE → JSON reconstruction.

The proxy mirrors Claude's streaming SSE chunks back to the client
verbatim, but for session-save we also need the equivalent unary
response so the hook can persist the assistant turn.

:func:`parse_sse_response` walks the buffered raw SSE string and
rebuilds the response dict. Extracted from ``proxy.py`` during SF-131.
"""

from __future__ import annotations

import json
from typing import Any


def parse_sse_response(raw: str) -> dict[str, Any] | None:
    """Reconstruct an Anthropic Messages response from SSE stream data."""
    response: dict[str, Any] = {}
    content_blocks: list[dict[str, Any]] = []
    current_block: dict[str, Any] = {}

    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            event = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")
        if etype == "message_start":
            msg = event.get("message", {})
            response.update(
                {
                    "id": msg.get("id"),
                    "type": msg.get("type", "message"),
                    "role": msg.get("role", "assistant"),
                    "model": msg.get("model"),
                    "usage": msg.get("usage", {}),
                }
            )
        elif etype == "content_block_start":
            current_block = dict(event.get("content_block", {}))
        elif etype == "content_block_delta":
            delta = event.get("delta", {})
            dtype = delta.get("type")
            if dtype == "text_delta":
                current_block.setdefault("text", "")
                current_block["text"] += delta.get("text", "")
            elif dtype == "thinking_delta":
                current_block.setdefault("thinking", "")
                current_block["thinking"] += delta.get("thinking", "")
            elif dtype == "signature_delta":
                current_block.setdefault("signature", "")
                current_block["signature"] += delta.get("signature", "")
            elif dtype == "input_json_delta":
                current_block.setdefault("_input_json", "")
                current_block["_input_json"] += delta.get("partial_json", "")
        elif etype == "content_block_stop":
            if "_input_json" in current_block:
                try:
                    current_block["input"] = json.loads(current_block.pop("_input_json"))
                except json.JSONDecodeError:
                    current_block["input"] = {}
                    current_block.pop("_input_json", None)
            content_blocks.append(current_block)
            current_block = {}
        elif etype == "message_delta":
            delta = event.get("delta", {})
            if "stop_reason" in delta:
                response["stop_reason"] = delta["stop_reason"]
            usage = event.get("usage", {})
            if usage:
                existing_usage = response.get("usage", {})
                existing_usage.update(usage)
                response["usage"] = existing_usage

    if not response:
        return None

    response["content"] = content_blocks
    return response
