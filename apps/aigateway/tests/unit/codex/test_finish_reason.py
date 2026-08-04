"""How a Codex response's `finish_reason` is derived.

FEATURE: OME-679 — a provider refusal must be distinguishable from a bad answer, so a
safety-refusing model is not scored as if it answered badly. That only works if this value is
DERIVED from the upstream response; the plugin used to hardcode `"stop"` on every reply.

A separate module from `test_chat_handler.py` rather than an append to it: the repo's
append-only gate compares file status, so growing an existing test file reads as "a prior test
was modified" even when the diff is purely additive (the line-level fix is in flight as
OME-369). A new file keeps the guarantee unambiguous.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from litellm.llms.custom_llm import CustomLLMError

from aigateway.plugins.codex_provider.chat_handler import _model_response_from_sse


def _sse_event(payload: dict[str, Any]) -> str:
    return f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n"


def _terminal_sse(
    event_type: str,
    *,
    status: str,
    reason: str | None = None,
    text: str = "partial answer",
) -> str:
    """One terminal Responses-API event carrying a full `Response`.

    `reason=None` covers the shape where `incomplete_details` is absent entirely — it is
    optional on the Response object, so its absence is a real case, not a contrived one.
    """
    response: dict[str, Any] = {
        "id": "resp_1",
        "created_at": 123,
        "model": "gpt-5.4-mini",
        "status": status,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": 3, "output_tokens": 2},
    }
    if reason is not None:
        response["incomplete_details"] = {"reason": reason}
    payload = {"type": event_type, "response": response}
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\ndata: [DONE]\n\n"


def _incomplete_sse(reason: str | None, text: str = "partial answer") -> str:
    return _terminal_sse("response.incomplete", status="incomplete", reason=reason, text=text)


def _completed_sse(text: str = "hello") -> str:
    return _terminal_sse("response.completed", status="completed", text=text)


def test_truncated_response_reports_length_and_keeps_the_partial_content() -> None:
    # The silently-wrong case this unit exists for. `response.incomplete` was not recognized as
    # terminal, so the stream drained and the whole answer was discarded as a 502 — and had it
    # survived, it would have claimed "stop".
    # INVARIANT: a truncated answer reaches the caller, labelled as truncated.
    response = _model_response_from_sse(_incomplete_sse("max_output_tokens"), "gpt-5.4-mini")

    assert response.choices[0].finish_reason == "length"
    assert response.choices[0].message.content == "partial answer"


def test_filtered_response_reports_content_filter() -> None:
    # STORY: as a researcher running HealthBench, a refused case must be visibly separate from a
    # wrong one — OME-679 keys that on exactly this value.
    response = _model_response_from_sse(
        _incomplete_sse("content_filter", text="I can't help with that"),
        "gpt-5.4-mini",
    )

    assert response.choices[0].finish_reason == "content_filter"
    assert response.choices[0].message.content == "I can't help with that"


def test_incomplete_without_details_falls_back_to_stop() -> None:
    # Boundary: `incomplete_details` is optional, so its absence must degrade to "stop" rather
    # than raise or emit None into a field with a closed vocabulary.
    response = _model_response_from_sse(_incomplete_sse(None), "gpt-5.4-mini")

    assert response.choices[0].finish_reason == "stop"
    assert response.choices[0].message.content == "partial answer"


def test_unknown_incomplete_reason_falls_back_to_stop() -> None:
    # Boundary: the upstream reason enum can grow. An unrecognized value must not leak into the
    # chat-completions `finish_reason`, whose vocabulary the gateway owns.
    response = _model_response_from_sse(_incomplete_sse("some_future_reason"), "gpt-5.4-mini")

    assert response.choices[0].finish_reason == "stop"


def test_completed_response_still_reports_stop() -> None:
    # Regression guard: the normal path keeps the value every existing test asserts.
    response = _model_response_from_sse(_completed_sse("hello"), "gpt-5.4-mini")

    assert response.choices[0].finish_reason == "stop"
    assert response.choices[0].message.content == "hello"


def test_stream_with_no_terminal_event_still_raises() -> None:
    # Error path unchanged: recognizing a SECOND terminal event must not make the handler
    # tolerant of a stream that terminates with neither.
    body = _sse_event({"type": "response.output_text.delta", "delta": "Hello"})

    with pytest.raises(CustomLLMError) as exc_info:
        _model_response_from_sse(body, "gpt-5.4-mini")

    assert exc_info.value.status_code == 502


def test_failed_response_still_raises() -> None:
    # Error path unchanged: `response.failed` is not terminal-with-content, it is an error.
    body = _sse_event(
        {"type": "response.failed", "error": {"message": "Codex blew up"}},
    )

    with pytest.raises(CustomLLMError) as exc_info:
        _model_response_from_sse(body, "gpt-5.4-mini")

    assert exc_info.value.status_code == 502
