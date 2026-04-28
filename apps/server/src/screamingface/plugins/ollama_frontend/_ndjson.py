"""Ollama NDJSON → JSON reconstruction.

The proxy mirrors Ollama's NDJSON stream chunks back to the client
verbatim, but for session-save we need the equivalent unary response
so the hook can persist the assistant turn.

:func:`parse_ndjson_response` walks the buffered raw stream and
rebuilds the response dict. Extracted from ``proxy.py`` during
SF-132. Pure function — no OTEL / I/O dependencies.
"""

from __future__ import annotations

import json
from typing import Any


def parse_ndjson_response(raw: str) -> dict[str, Any] | None:
    """Reconstruct a single Ollama /api/chat response from NDJSON stream.

    Concatenates ``message.content`` across chunks; keeps the final
    chunk's metadata (model, created_at, done_reason, usage fields).
    """
    final: dict[str, Any] = {}
    content_acc = ""
    role = "assistant"

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg = event.get("message") or {}
        if isinstance(msg, dict):
            role = msg.get("role", role)
            content_acc += msg.get("content", "") or ""

        if event.get("done"):
            final = dict(event)

    if not final:
        return None

    final["message"] = {"role": role, "content": content_acc}
    return final
