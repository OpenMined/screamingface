"""Unit tests for chatgpt_session helpers (header/body builders)."""

from __future__ import annotations

from screamingface.plugins.codex_backend_api.chatgpt_session import (
    CHATGPT_CLIENT_VERSION,
    build_chatgpt_headers,
    build_health_probe_body,
    build_responses_body,
)
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart


def test_build_chatgpt_headers_layers_session_metadata() -> None:
    headers = build_chatgpt_headers({"authorization": "Bearer t"}, "acct-123")
    assert headers["authorization"] == "Bearer t"
    assert headers["chatgpt-account-id"] == "acct-123"
    assert headers["originator"] == "codex_exec"
    assert headers["version"] == CHATGPT_CLIENT_VERSION
    assert headers["accept"] == "text/event-stream"
    assert headers["content-type"] == "application/json"
    # session ids are reused across the three id-bearing headers
    assert headers["session_id"] == headers["x-client-request-id"]
    assert headers["x-codex-window-id"].startswith(headers["session_id"])


def test_build_chatgpt_headers_does_not_mutate_input() -> None:
    src = {"authorization": "Bearer t"}
    build_chatgpt_headers(src, "acct")
    assert src == {"authorization": "Bearer t"}


def test_build_responses_body_with_string_content() -> None:
    body = build_responses_body([CoreMessage(role="user", content="hi there")], model="gpt-5.4")
    assert body["model"] == "gpt-5.4"
    assert body["instructions"]
    assert body["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "hi there"}]}
    ]
    assert body["stream"] is True
    assert body["store"] is False


def test_build_responses_body_with_text_parts() -> None:
    body = build_responses_body(
        [
            CoreMessage(
                role="user",
                content=[TextPart(text="part one"), TextPart(text="part two")],
            )
        ],
        model="gpt-5.4",
    )
    texts = [item["content"][0]["text"] for item in body["input"]]
    assert texts == ["part one", "part two"]


def test_build_responses_body_uses_custom_system() -> None:
    body = build_responses_body(
        [CoreMessage(role="user", content="hi")],
        model="gpt-5.4",
        system="be terse",
    )
    assert body["instructions"] == "be terse"


def test_build_health_probe_body_is_minimal() -> None:
    body = build_health_probe_body()
    assert body["model"] == "gpt-5.4"
    assert body["instructions"] == "Say OK."
    assert body["input"][0]["role"] == "user"
