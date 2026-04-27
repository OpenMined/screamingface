"""Unit tests for the OpenAI Responses SSE parser."""

from __future__ import annotations

from screamingface.plugins.codex_backend_api.sse_parser import parse_responses_sse


def test_collects_text_deltas_in_order() -> None:
    sse = (
        'data: {"type":"response.output_text.delta","delta":"hel"}\n'
        'data: {"type":"response.output_text.delta","delta":"lo "}\n'
        'data: {"type":"response.output_text.delta","delta":"world"}\n'
    )
    msg = parse_responses_sse(sse)
    assert msg.role == "assistant"
    assert msg.content[0].text == "hello world"


def test_extracts_completed_event_metadata() -> None:
    sse = (
        'data: {"type":"response.output_text.delta","delta":"ok"}\n'
        'data: {"type":"response.completed","response":{"model":"gpt-5.4",'
        '"usage":{"input_tokens":10,"output_tokens":2}}}\n'
    )
    msg = parse_responses_sse(sse)
    assert msg.provider_metadata == {
        "openai.usage": {"input_tokens": 10, "output_tokens": 2},
        "openai.model": "gpt-5.4",
    }


def test_skips_unknown_events_and_invalid_json() -> None:
    sse = (
        ":keepalive\n"
        "event: ping\n"
        "data: not-json\n"
        'data: {"type":"unknown.event","x":1}\n'
        'data: {"type":"response.output_text.delta","delta":"x"}\n'
    )
    msg = parse_responses_sse(sse)
    assert msg.content[0].text == "x"
    assert msg.provider_metadata is None


def test_empty_stream_produces_empty_message() -> None:
    msg = parse_responses_sse("")
    assert msg.content[0].text == ""
    assert msg.provider_metadata is None
