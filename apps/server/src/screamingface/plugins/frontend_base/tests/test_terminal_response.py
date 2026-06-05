"""Unit tests for terminal_response builders, streamers, and helpers.

Verifies, per provider:
- the unary envelope JSON structure pinned by the spec's Component Spec sections,
- conversation-aware usage (non-zero when prompt/result supplied, zero when empty),
- the EXACT streamer frame sequence — each streamer is decoded INDEPENDENTLY (SSE split
  on ``\\n\\n`` / NDJSON split on ``\\n`` then ``json.loads`` each frame) to prove valid
  framing rather than trusting a single concatenated blob,
- deterministic-id stability + formula, and
- ``extract_error_text`` formatting for BOTH an ``httpx.HTTPStatusError`` (the /ensemble
  502 PlainText path) AND a raw exception.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from screamingface.plugins.frontend_base.terminal_response import (
    build_anthropic_message,
    build_gemini_response,
    build_ollama_response,
    build_openai_response,
    deterministic_id,
    estimate_tokens,
    extract_error_text,
    serialize_transcript,
    stream_anthropic_sse,
    stream_gemini_chunks,
    stream_ollama_ndjson,
    stream_openai_sse,
)

# ---------------------------------------------------------------------------
# Independent frame decoders (do not trust the producer — re-parse the bytes)
# ---------------------------------------------------------------------------


def parse_sse_frames(sse_bytes: bytes) -> list[tuple[str | None, dict]]:
    """Split an SSE byte stream on blank lines and json.loads each ``data:`` payload.

    Asserts (implicitly, by raising) that every non-empty frame is well-formed and that
    the whole stream is blank-line (``\\n\\n``) terminated.
    """
    text = sse_bytes.decode("utf-8")
    # A well-formed SSE stream ends each frame with a blank line.
    assert text.endswith("\n\n"), "SSE stream must end with a blank-line-terminated frame"
    results: list[tuple[str | None, dict]] = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.split("\n")
        event_line = next((line for line in lines if line.startswith("event:")), None)
        data_line = next((line for line in lines if line.startswith("data:")), None)
        assert data_line is not None, f"SSE frame missing data line: {frame!r}"
        event_name = event_line.split(":", 1)[1].strip() if event_line else None
        data_json = data_line.split(":", 1)[1].strip()
        results.append((event_name, json.loads(data_json)))
    return results


def parse_ndjson_frames(ndjson_bytes: bytes) -> list[dict]:
    """Split an NDJSON byte stream on newlines and json.loads each line."""
    text = ndjson_bytes.decode("utf-8")
    assert "data: " not in text, "NDJSON must not carry an SSE data: prefix"
    return [json.loads(line) for line in text.split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def test_build_anthropic_message() -> None:
    result = build_anthropic_message("Test response", "claude-3-5-sonnet", prompt_text="User: hi")
    assert result["id"].startswith("msg_")
    assert result["type"] == "message"
    assert result["role"] == "assistant"
    assert result["content"] == [{"type": "text", "text": "Test response"}]
    assert result["model"] == "claude-3-5-sonnet"
    assert result["stop_reason"] == "end_turn"
    assert result["stop_sequence"] is None
    usage = result["usage"]
    assert usage["input_tokens"] > 0  # non-zero: prompt_text supplied (conversation-aware)
    assert usage["output_tokens"] > 0  # non-zero: result_text supplied
    assert usage["cache_creation_input_tokens"] == 0
    assert usage["cache_read_input_tokens"] == 0


def test_build_anthropic_message_empty_prompt_zero_input_tokens() -> None:
    result = build_anthropic_message("Hi", "claude-3-5-sonnet")
    assert result["usage"]["input_tokens"] == 0
    assert result["usage"]["output_tokens"] > 0


def test_build_anthropic_message_honors_response_id() -> None:
    result = build_anthropic_message("Hi", "m", response_id="msg_fixed")
    assert result["id"] == "msg_fixed"


async def test_stream_anthropic_sse() -> None:
    chunks = [c async for c in stream_anthropic_sse("Result text", "claude-3-5-sonnet")]
    assert all(isinstance(c, bytes) for c in chunks)
    sse_bytes = b"".join(chunks)
    frames = parse_sse_frames(sse_bytes)
    event_names = [name for name, _ in frames]
    assert event_names == [
        "message_start",
        "ping",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    # ping frame present, after message_start
    ping = next(d for n, d in frames if n == "ping")
    assert ping == {"type": "ping"}
    # whole text in ONE text_delta
    delta_frame = next(d for n, d in frames if n == "content_block_delta")
    assert delta_frame["delta"]["type"] == "text_delta"
    assert delta_frame["delta"]["text"] == "Result text"
    # message_delta carries output usage
    md = next(d for n, d in frames if n == "message_delta")
    assert md["delta"]["stop_reason"] == "end_turn"
    assert "output_tokens" in md["usage"]
    assert b"[DONE]" not in sse_bytes


async def test_stream_anthropic_sse_usage_is_conversation_aware() -> None:
    chunks = [c async for c in stream_anthropic_sse("Result", "m", prompt_text="User: hello there")]
    frames = parse_sse_frames(b"".join(chunks))
    start = next(d for n, d in frames if n == "message_start")
    usage = start["message"]["usage"]
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0


# ---------------------------------------------------------------------------
# OpenAI (Responses)
# ---------------------------------------------------------------------------


def test_build_openai_response() -> None:
    result = build_openai_response("Test response", "gpt-4o-mini", prompt_text="User: hi")
    assert result["id"].startswith("resp_")
    assert result["object"] == "response"
    assert result["status"] == "completed"
    assert isinstance(result["created_at"], int)
    assert result["created_at"] > 0
    assert len(result["output"]) == 1
    item = result["output"][0]
    assert item["id"].startswith("msg_")
    assert item["type"] == "message"
    assert item["status"] == "completed"
    assert item["role"] == "assistant"
    assert item["content"][0]["type"] == "output_text"
    assert item["content"][0]["text"] == "Test response"
    assert item["content"][0]["annotations"] == []
    usage = result["usage"]
    for k in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        assert k in usage
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0


def test_build_openai_response_completed_status_for_errors() -> None:
    # #244: even the error path uses status="completed" for CLI visibility.
    result = build_openai_response("[url4 error] ...", "gpt-4o-mini", status="completed")
    assert result["status"] == "completed"


async def test_stream_openai_sse() -> None:
    chunks = [c async for c in stream_openai_sse("Result", "gpt-4o-mini")]
    sse_bytes = b"".join(chunks)
    frames = parse_sse_frames(sse_bytes)
    event_names = [d["type"] for _, d in frames]
    assert event_names == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    # codex SSE has no `event:` line — pure `data:` frames.
    assert all(name is None for name, _ in frames)
    created = next(d for _, d in frames if d["type"] == "response.created")
    assert created["response"]["status"] == "in_progress"
    delta = next(d for _, d in frames if d["type"] == "response.output_text.delta")
    assert delta["delta"] == "Result"  # whole text in one delta
    completed = next(d for _, d in frames if d["type"] == "response.completed")
    assert completed["response"]["status"] == "completed"
    assert completed["response"]["usage"]["total_tokens"] >= 0
    assert "total_tokens" in completed["response"]["usage"]
    # stable item_id across item/part/delta/done frames
    item_ids = {d["item_id"] for _, d in frames if "item_id" in d} | {
        d["item"]["id"] for _, d in frames if "item" in d
    }
    assert len(item_ids) == 1
    # monotonic sequence_number
    seq_nums = [d["sequence_number"] for _, d in frames]
    assert seq_nums == sorted(seq_nums)
    assert seq_nums == list(range(len(seq_nums)))
    assert b"[DONE]" not in sse_bytes


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def test_build_gemini_response() -> None:
    result = build_gemini_response("Test response", "gemini-2.5-flash", prompt_text="User: hi")
    candidate = result["candidates"][0]
    assert candidate["finishReason"] == "STOP"
    assert candidate["index"] == 0
    assert candidate["content"]["role"] == "model"
    assert candidate["content"]["parts"][0]["text"] == "Test response"
    usage = result["usageMetadata"]  # camelCase authoritative
    for k in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"):
        assert k in usage
    assert usage["totalTokenCount"] == usage["promptTokenCount"] + usage["candidatesTokenCount"]
    assert usage["promptTokenCount"] > 0
    assert usage["candidatesTokenCount"] > 0
    assert result["modelVersion"] == "gemini-2.5-flash"
    assert "responseId" in result  # O12 synthetic response id


async def test_stream_gemini_chunks_default_json_array() -> None:
    chunks = [c async for c in stream_gemini_chunks("Result", "gemini-2.5-flash")]
    body = b"".join(chunks)
    # default is a real JSON ARRAY (application/json), NOT SSE.
    assert b"data: " not in body
    data = json.loads(body)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["candidates"][0]["finishReason"] == "STOP"
    assert data[0]["candidates"][0]["content"]["parts"][0]["text"] == "Result"


async def test_stream_gemini_chunks_alt_sse() -> None:
    chunks = [c async for c in stream_gemini_chunks("Result", "gemini-2.5-flash", alt_sse=True)]
    body = b"".join(chunks)
    assert body.startswith(b"data: ")
    assert body.endswith(b"\n\n")
    assert b"[DONE]" not in body
    # decode the single SSE frame independently
    payload = body.decode("utf-8").split("data:", 1)[1].strip()
    obj = json.loads(payload)
    assert obj["candidates"][0]["content"]["parts"][0]["text"] == "Result"


# ---------------------------------------------------------------------------
# Ollama (NDJSON)
# ---------------------------------------------------------------------------


def test_build_ollama_response() -> None:
    result = build_ollama_response("Test response", "llama3.2", prompt_text="User: hi")
    assert result["model"] == "llama3.2"
    assert result["created_at"] == "2025-06-04T00:00:00Z"
    assert result["message"] == {"role": "assistant", "content": "Test response"}
    assert result["done"] is True
    assert result["done_reason"] == "stop"
    assert result["total_duration"] == 0
    assert result["load_duration"] == 0
    assert result["prompt_eval_count"] > 0  # conversation-aware (prompt_text supplied)
    assert result["eval_count"] > 0


async def test_stream_ollama_ndjson() -> None:
    chunks = [c async for c in stream_ollama_ndjson("Result text", "llama3.2")]
    ndjson_bytes = b"".join(chunks)
    frames = parse_ndjson_frames(ndjson_bytes)
    assert len(frames) == 2
    # first frame: full content, not done
    assert frames[0]["done"] is False
    assert frames[0]["message"] == {"role": "assistant", "content": "Result text"}
    # terminal frame: empty content, done + done_reason, still structurally complete
    assert frames[1]["done"] is True
    assert frames[1]["done_reason"] == "stop"
    assert frames[1]["message"] == {"role": "assistant", "content": ""}
    # every frame carries a complete message field (fixes abbreviated-frame major)
    assert "message" in frames[0] and "message" in frames[1]
    # NDJSON, not SSE
    assert b"data: " not in ndjson_bytes


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def test_extract_error_text_raw_exception() -> None:
    exc = ValueError("Test error message")
    text = extract_error_text(exc, "test-spec", "some_expression")
    assert text.startswith("[url4 error] ")
    assert "test-spec" in text
    assert "some_expression" in text
    assert "ValueError" in text
    assert "Test error message" in text
    assert "Traceback:" in text


def test_extract_error_text_truncates_long_expression() -> None:
    long_expr = "x" * 500
    text = extract_error_text(RuntimeError("boom"), "spec", long_expr)
    # only the first 200 chars of the expression are surfaced
    assert "x" * 200 in text
    assert "x" * 201 not in text


def test_extract_error_text_empty_expression() -> None:
    text = extract_error_text(RuntimeError("boom"), "spec", "")
    assert "(empty)" in text


def test_extract_error_text_httpx_status_error_surfaces_502_body() -> None:
    # The /ensemble 502 path: PlainTextResponse body must be visible, not just "502".
    request = httpx.Request("GET", "http://localhost/ensemble")
    response = httpx.Response(
        502, text="url4 evaluation failed: interpreter blew up", request=request
    )
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        response.raise_for_status()
    text = extract_error_text(excinfo.value, "test-spec", "$prompt | model:foo")
    assert text.startswith("[url4 error] ")
    assert "HTTPStatusError" in text
    assert "502" in text
    assert "url4 evaluation failed: interpreter blew up" in text  # the PlainText body
    assert "Traceback:" in text


def test_serialize_transcript() -> None:
    turns = [("user", "Hello"), ("assistant", "Hi there"), ("user", "How are you?")]
    result = serialize_transcript(turns)
    assert result == "User: Hello\nAssistant: Hi there\nUser: How are you?"


def test_serialize_transcript_empty() -> None:
    assert serialize_transcript([]) == ""


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("1234") == 1
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("a") == 1  # floor would be 0, but min is 1 for non-empty


def test_deterministic_id_is_stable() -> None:
    a = deterministic_id("msg_", "m", "p", "r")
    b = deterministic_id("msg_", "m", "p", "r")
    assert a == b
    assert a.startswith("msg_")
    assert deterministic_id("msg_", "m", "p", "r2") != a


def test_deterministic_id_matches_sha256_formula() -> None:
    expected = "msg_" + hashlib.sha256(b"mpr").hexdigest()[:24]
    assert deterministic_id("msg_", "m", "p", "r") == expected
    # 24 hex chars after the prefix
    assert len(deterministic_id("", "m", "p", "r")) == 24


def test_deterministic_id_empty_prefix() -> None:
    # gemini responseId uses an empty prefix.
    got = deterministic_id("", "gemini-2.5-flash", "User: hi", "answer")
    assert len(got) == 24
    assert all(c in "0123456789abcdef" for c in got)
