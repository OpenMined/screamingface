"""Tests for codex-frontend proxy helpers."""

from __future__ import annotations

from screamingface.plugins.codex_frontend.proxy import (
    _embed_context,
    _extract_last_user_text,
    _inject_system_context,
    _parse_sse_response,
    _replace_user_text,
)


class TestExtractLastUserText:
    def test_string_input(self):
        body = {"input": "Hello world"}
        assert _extract_last_user_text(body) == "Hello world"

    def test_message_array(self):
        body = {
            "input": [
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "Reply"},
                {"role": "user", "content": "Second"},
            ]
        }
        assert _extract_last_user_text(body) == "Second"

    def test_empty_input(self):
        assert _extract_last_user_text({}) is None
        assert _extract_last_user_text({"input": []}) is None

    def test_no_user_messages(self):
        body = {"input": [{"role": "assistant", "content": "hi"}]}
        assert _extract_last_user_text(body) is None


class TestReplaceUserText:
    def test_string_input(self):
        body = {"input": "old text"}
        _replace_user_text(body, "new text")
        assert body["input"] == "new text"

    def test_message_array(self):
        body = {
            "input": [
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "reply"},
            ]
        }
        _replace_user_text(body, "new")
        assert body["input"][0]["content"] == "new"


class TestInjectSystemContext:
    def test_no_existing_instructions(self):
        body = {}
        _inject_system_context(body, "Context here")
        assert body["instructions"] == "Context here"

    def test_existing_instructions(self):
        body = {"instructions": "Be helpful"}
        _inject_system_context(body, "Context here")
        assert "Be helpful" in body["instructions"]
        assert "Context here" in body["instructions"]


class TestEmbedContext:
    def test_user_concat(self):
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.embed_target = "user"
        settings.embed_mode = "concat"
        body = {"input": "My question"}
        _embed_context(body, "Some context", settings)
        assert "My question" in body["input"]
        assert "Some context" in body["input"]

    def test_system_embed(self):
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.embed_target = "system"
        settings.system_prompt = "You are helpful"
        body = {"input": "Question"}
        _embed_context(body, "Context", settings)
        assert "You are helpful" in body["instructions"]
        assert "Context" in body["instructions"]


class TestParseSSEResponse:
    def test_simple_response(self):
        import json

        def _evt(data):
            return f"data: {json.dumps(data)}\n"

        raw = (
            _evt({
                "type": "response.created",
                "response": {"id": "resp_1", "model": "o4-mini", "status": "in_progress"},
            })
            + _evt({
                "type": "response.output_item.added",
                "item": {"type": "message", "role": "assistant"},
            })
            + _evt({"type": "response.output_text.delta", "delta": "Hello"})
            + _evt({"type": "response.output_text.delta", "delta": " world"})
            + _evt({
                "type": "response.output_item.done",
                "item": {"type": "message", "role": "assistant"},
            })
            + _evt({
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                },
            })
            + "data: [DONE]\n"
        )
        result = _parse_sse_response(raw)
        assert result is not None
        assert result["id"] == "resp_1"
        assert result["status"] == "completed"
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "message"
        assert result["output"][0]["content"][0]["text"] == "Hello world"

    def test_empty_stream(self):
        assert _parse_sse_response("") is None
        assert _parse_sse_response("data: [DONE]\n") is None
