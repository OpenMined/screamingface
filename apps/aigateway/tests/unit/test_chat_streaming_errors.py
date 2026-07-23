"""Regression tests for provider exceptions in SSE streaming."""

from __future__ import annotations

import json
import logging

import pytest

from aigateway.routes.chat_dispatch import _stream


@pytest.mark.asyncio
async def test_streaming_provider_error_after_successful_chunk_is_sanitized() -> None:
    """A provider failure after one chunk must redact raw exception details."""

    class FakeAuthError(Exception):
        pass

    class _FakePlugin:
        async def chat_completion_stream(self, body: dict[str, str]):
            del body
            yield {"choices": [{"delta": {"content": "ok"}}]}
            raise FakeAuthError("STREAM_SENTINEL_SECRET=bad-token")

    frames = [frame async for frame in _stream(_FakePlugin(), {})]

    expected_chunk = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
    expected_error_frame = (
        'data: {"error": {'
        '"code": "provider_error", "message": "The upstream provider returned an error."}}\n\n'
    )

    assert frames[0] == f"data: {expected_chunk}\n\n"
    assert frames[1] == expected_error_frame
    output = "".join(frames)
    assert "STREAM_SENTINEL_SECRET" not in output
    assert "FakeAuthError" not in output


@pytest.mark.asyncio
async def test_streaming_provider_error_before_first_chunk_is_sanitized() -> None:
    """A provider failure before first chunk yields only the gateway error frame."""

    class FakeProviderError(Exception):
        pass

    class _FakePlugin:
        async def chat_completion_stream(self, body: dict[str, str]):
            del body
            if False:
                yield {"choices": [{"delta": {"content": "never"}}]}
            raise FakeProviderError(
                "provider body text with STACK_TRACE_STREAM_SENTINEL_SECRET=bad-token"
            )

    frames = [frame async for frame in _stream(_FakePlugin(), {})]

    expected_error_frame = (
        'data: {"error": {'
        '"code": "provider_error", "message": "The upstream provider returned an error."}}\n\n'
    )

    assert frames == [expected_error_frame]
    output = "".join(frames)
    assert "[DONE]" not in output
    assert "provider body text" not in output
    assert "STREAM_SENTINEL_SECRET" not in output
    assert "FakeProviderError" not in output


@pytest.mark.asyncio
async def test_streaming_provider_error_after_chunk_omits_raw_provider_and_secrets(
    caplog,
) -> None:
    provider_body = "provider body text with STREAM_LOG_SECRET_OME577"

    class FakeProviderError(RuntimeError):
        pass

    class _FakePlugin:
        async def chat_completion_stream(self, body: dict[str, str]):
            del body
            yield {"choices": [{"delta": {"content": "ok"}}]}
            raise FakeProviderError(provider_body)

    with caplog.at_level(logging.ERROR, logger="aigateway.routes.chat_dispatch"):
        frames = [frame async for frame in _stream(_FakePlugin(), {})]

    expected_chunk = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
    expected_error_frame = (
        'data: {"error": {'
        '"code": "provider_error", "message": "The upstream provider returned an error."}}\n\n'
    )

    assert frames == [f"data: {expected_chunk}\n\n", expected_error_frame]
    output = "".join(frames)
    assert "[DONE]" not in output
    assert provider_body not in output
    assert "STREAM_LOG_SECRET_OME577" not in output
    assert "FakeProviderError" not in output

    messages = [record.getMessage() for record in caplog.records]
    assert all("STREAM_LOG_SECRET_OME577" not in message for message in messages)
    assert all(provider_body not in message for message in messages)
    assert all("Traceback" not in message for message in messages)
    assert "STREAM_LOG_SECRET_OME577" not in caplog.text
    assert provider_body not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert any("stream failed" in message for message in messages)
    assert any("type=FakeProviderError" in message for message in messages)
    assert any("plugin=_FakePlugin" in message for message in messages)


@pytest.mark.asyncio
async def test_streaming_success_still_emits_done_after_chunks() -> None:
    """The normal streaming contract remains unchanged on success."""

    class _FakePlugin:
        async def chat_completion_stream(self, body: dict[str, str]):
            del body
            yield {"choices": [{"delta": {"content": "ok"}}]}

    frames = [frame async for frame in _stream(_FakePlugin(), {})]

    expected_chunk = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
    assert frames == [f"data: {expected_chunk}\n\n", "data: [DONE]\n\n"]
