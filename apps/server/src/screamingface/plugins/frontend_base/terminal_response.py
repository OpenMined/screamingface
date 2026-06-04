"""Shared terminal-response builders and streamers for all four frontends.

Centralizes:
- error formatting (extract_error_text)
- transcript serialization (serialize_transcript) — Decision A conversation-aware
- usage estimation (estimate_tokens) + deterministic ids (deterministic_id)
- all eight builder/streamer functions (sole location)

Per-frontend modules import and re-export only — no wire-format logic outside.
Decision A (conversation-aware): builders take optional ``prompt_text`` and
``response_id`` so responses echo a deterministic id plus plausible non-zero usage
derived from the serialized transcript and the resolved result text.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from collections.abc import AsyncIterator

import httpx


def extract_error_text(exc: BaseException, spec_name: str, expression: str) -> str:
    """Format error text uniformly for all providers.

    Handles BOTH an ``httpx.HTTPStatusError`` (the ``/ensemble`` 502 path, whose
    ``PlainTextResponse`` body carries ``"url4 evaluation failed: ..."``) AND a raw
    in-process ``Url4Interpreter`` exception. Always prefixed ``"[url4 error] "`` and
    always includes the full traceback. The frontends inject the returned text into a
    provider-native fake-200 envelope (Decision: blocking and screaming, PR #244).
    """
    tb_str = "".join(traceback.format_exception(exc))
    expr_preview = expression[:200] if expression else "(empty)"
    lines = [
        f"[url4 error] {spec_name}",
        "",
        f"Expression: {expr_preview}",
        "",
        f"Error: {exc.__class__.__name__}: {exc}",
    ]
    # /ensemble 502 path: surface the upstream PlainText body so the CLI sees the
    # real evaluation failure, not just the opaque "502 Bad Gateway" status line.
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        lines += [
            "",
            f"Status: {exc.response.status_code}",
            f"Body: {exc.response.text}",
        ]
    lines += ["", "Traceback:", tb_str]
    return "\n".join(lines)


def serialize_transcript(turns: list[tuple[str, str]]) -> str:
    r"""Render conversation turns as ``"User: ...\nAssistant: ...\n..."`` (Decision A).

    Args:
        turns: list of (role, text) tuples, e.g. ``[("user", "Hello"), ("assistant", "Hi")]``.

    Returns:
        Serialized transcript string for use as the ``$prompt`` blob.
    """
    lines = []
    for role, text in turns:
        role_upper = role.capitalize()
        lines.append(f"{role_upper}: {text}")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Estimate token count: ``max(1, len(text) // 4)`` if text else ``0``."""
    return max(1, len(text) // 4) if text else 0


def deterministic_id(prefix: str, model: str, prompt_text: str, result_text: str) -> str:
    """Generate a deterministic id from model + prompt + result via SHA256.

    Returns ``f"{prefix}{sha256((model + prompt_text + result_text).encode()).hexdigest()[:24]}"``.
    """
    combined = model + prompt_text + result_text
    digest = hashlib.sha256(combined.encode()).hexdigest()[:24]
    return f"{prefix}{digest}"


# ============================================================================
# Anthropic (claude_frontend)
# ============================================================================


def build_anthropic_message(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
) -> dict:
    """Build the unary Anthropic Messages response envelope."""
    msg_id = response_id or deterministic_id("msg_", model, prompt_text, result_text)
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": result_text}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


async def stream_anthropic_sse(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
) -> AsyncIterator[bytes]:
    r"""Stream the Anthropic response as SSE (``event:`` lines, blank-line terminated).

    Frame sequence:
    message_start -> ping -> content_block_start -> content_block_delta
    -> content_block_stop -> message_delta -> message_stop

    All text rides in ONE ``text_delta``. No ``[DONE]``. Every frame is ``\n\n``-terminated.
    """
    msg_id = response_id or deterministic_id("msg_", model, prompt_text, result_text)
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    def sse_frame(event_name: str, payload: dict) -> bytes:
        return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode()

    yield sse_frame(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    )
    yield sse_frame("ping", {"type": "ping"})
    yield sse_frame(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    )
    yield sse_frame(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": result_text},
        },
    )
    yield sse_frame(
        "content_block_stop",
        {
            "type": "content_block_stop",
            "index": 0,
        },
    )
    yield sse_frame(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        },
    )
    yield sse_frame("message_stop", {"type": "message_stop"})


# ============================================================================
# OpenAI (codex_frontend)
# ============================================================================


def build_openai_response(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
    status: str = "completed",
) -> dict:
    """Build the unary OpenAI Responses envelope.

    NOTE (#244 error visibility): the error path uses ``status="completed"`` carrying
    the error text, NOT ``status="failed"``, so the Codex CLI renders the visible error.
    """
    resp_id = response_id or deterministic_id("resp_", model, prompt_text, result_text)
    item_id = deterministic_id("msg_", model, prompt_text, result_text)
    created_at = int(time.time())
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    return {
        "id": resp_id,
        "object": "response",
        "created_at": created_at,
        "model": model,
        "status": status,
        "output": [
            {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": result_text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


async def stream_openai_sse(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
    status: str = "completed",
) -> AsyncIterator[bytes]:
    r"""Stream the OpenAI response as SSE (full canonical 9-event sequence).

    response.created -> response.in_progress -> response.output_item.added
    -> response.content_part.added -> response.output_text.delta
    -> response.output_text.done -> response.content_part.done
    -> response.output_item.done -> response.completed

    Every frame is ``data: {json}\n\n``. Stable ``item_id``. Monotonic ``sequence_number``.
    No ``[DONE]``.
    """
    resp_id = response_id or deterministic_id("resp_", model, prompt_text, result_text)
    item_id = deterministic_id("msg_", model, prompt_text, result_text)
    created_at = int(time.time())
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)
    seq = 0

    def event(payload: dict) -> bytes:
        nonlocal seq
        payload.setdefault("sequence_number", seq)
        seq += 1
        return f"data: {json.dumps(payload)}\n\n".encode()

    base_resp = {
        "id": resp_id,
        "object": "response",
        "created_at": created_at,
        "model": model,
        "output": [],
        "usage": None,
    }

    yield event({"type": "response.created", "response": {**base_resp, "status": "in_progress"}})
    yield event(
        {"type": "response.in_progress", "response": {**base_resp, "status": "in_progress"}}
    )
    yield event(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": item_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        }
    )
    yield event(
        {
            "type": "response.content_part.added",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        }
    )
    yield event(
        {
            "type": "response.output_text.delta",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "delta": result_text,
        }
    )
    yield event(
        {
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "text": result_text,
        }
    )
    yield event(
        {
            "type": "response.content_part.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": result_text, "annotations": []},
        }
    )
    yield event(
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": result_text, "annotations": []}],
            },
        }
    )
    yield event(
        {
            "type": "response.completed",
            "response": {
                **base_resp,
                "status": status,
                "output": [
                    {
                        "id": item_id,
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": result_text, "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        }
    )


# ============================================================================
# Google Gemini (gemini_frontend)
# ============================================================================


def build_gemini_response(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
) -> dict:
    """Build the unary Gemini GenerateContentResponse envelope.

    O12: includes a synthetic (deterministic) ``responseId``. ``usageMetadata`` is
    camelCase (authoritative for gemini). ``modelVersion`` mirrors the requested model.
    """
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)
    resp_id = response_id or deterministic_id("", model, prompt_text, result_text)

    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": result_text}]},
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [],
            }
        ],
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "totalTokenCount": input_tokens + output_tokens,
        },
        "modelVersion": model,
        "responseId": resp_id,
    }


async def stream_gemini_chunks(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
    alt_sse: bool = False,
) -> AsyncIterator[bytes]:
    r"""Stream the Gemini response.

    Default (``alt_sse=False``) yields a true JSON ARRAY ``[{...}]`` matching Gemini's
    real ``streamGenerateContent`` REST wire format (``application/json``). With
    ``alt_sse=True``, emits ``data: {...}\n\n`` for ``text/event-stream``. No ``[DONE]``.
    """
    obj = build_gemini_response(
        result_text, model, prompt_text=prompt_text, response_id=response_id
    )

    if alt_sse:
        yield f"data: {json.dumps(obj)}\n\n".encode()
    else:
        yield b"["
        yield json.dumps(obj).encode()
        yield b"]"


# ============================================================================
# Ollama (ollama_frontend)
# ============================================================================


def build_ollama_response(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
) -> dict:
    """Build the unary Ollama ``/api/chat`` response envelope.

    Ollama uses durations, not tokens; durations are zero, while the eval counts carry
    the conversation-aware estimates.
    """
    created_at = "2025-06-04T00:00:00Z"
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    return {
        "model": model,
        "created_at": created_at,
        "message": {"role": "assistant", "content": result_text},
        "done": True,
        "done_reason": "stop",
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": input_tokens,
        "prompt_eval_duration": 0,
        "eval_count": output_tokens,
        "eval_duration": 0,
    }


async def stream_ollama_ndjson(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
) -> AsyncIterator[bytes]:
    """Stream the Ollama response as NDJSON (NOT SSE).

    Emits TWO complete JSON objects, each on its own line:
    1. In-progress frame with the full ``result_text`` (``done=false``).
    2. Terminal frame with empty content and ``done=true``, ``done_reason="stop"``.
    Every frame carries a complete ``message`` field. Content-Type: ``application/x-ndjson``.
    No ``data:`` prefix, no blank-line separators, no ``[DONE]``.
    """
    created_at = "2025-06-04T00:00:00Z"
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    yield (
        json.dumps(
            {
                "model": model,
                "created_at": created_at,
                "message": {"role": "assistant", "content": result_text},
                "done": False,
            }
        )
        + "\n"
    ).encode()

    yield (
        json.dumps(
            {
                "model": model,
                "created_at": created_at,
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": input_tokens,
                "prompt_eval_duration": 0,
                "eval_count": output_tokens,
                "eval_duration": 0,
            }
        )
        + "\n"
    ).encode()


__all__ = [
    "extract_error_text",
    "serialize_transcript",
    "estimate_tokens",
    "deterministic_id",
    "build_anthropic_message",
    "stream_anthropic_sse",
    "build_openai_response",
    "stream_openai_sse",
    "build_gemini_response",
    "stream_gemini_chunks",
    "build_ollama_response",
    "stream_ollama_ndjson",
]
