"""SSE parser for OpenAI Responses API event streams.

The chatgpt.com/backend-api/codex/responses endpoint returns server-
sent events. We collect text deltas and final usage metadata into a
single :class:`CoreMessage`.

Pulled out of ``backend.py`` so the parser can be unit-tested and
shared across paths without touching the OAuth/HTTP machinery.
"""

from __future__ import annotations

import json

from screamingface.plugins.llm_base.messages import CoreMessage, TextPart


def parse_responses_sse(sse_text: str) -> CoreMessage:
    """Parse an SSE stream from the OpenAI Responses API.

    Recognized event types:

    - ``response.output_text.delta`` — incremental text chunk; we
      concatenate ``data.delta``.
    - ``response.completed`` — final event carrying ``usage`` and
      ``model`` metadata; surfaced under ``provider_metadata`` as
      ``openai.usage`` and ``openai.model``.

    Lines that don't start with ``"data: "`` or that don't parse as
    JSON are skipped — keepalives and partial frames are tolerated.
    """
    text_parts: list[str] = []
    provider_metadata: dict = {}

    for line in sse_text.split("\n"):
        if not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "")
        if event_type == "response.output_text.delta":
            text_parts.append(data.get("delta", ""))
        elif event_type == "response.completed":
            resp = data.get("response", {})
            usage = resp.get("usage", {})
            if usage:
                provider_metadata["openai.usage"] = usage
            provider_metadata["openai.model"] = resp.get("model", "")

    return CoreMessage(
        role="assistant",
        content=[TextPart(text="".join(text_parts))],
        provider_metadata=provider_metadata or None,
    )
