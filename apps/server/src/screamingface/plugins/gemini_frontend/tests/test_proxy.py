"""Tests for gemini-frontend proxy helpers."""

from __future__ import annotations

from screamingface.plugins.gemini_frontend.proxy import (
    _embed_context,
    _extract_last_user_text,
    _inject_system_context,
    _replace_user_text,
)


class TestExtractLastUserText:
    def test_simple_user_message(self):
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": "Hello"}]},
            ]
        }
        assert _extract_last_user_text(body) == "Hello"

    def test_multi_turn(self):
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": "First"}]},
                {"role": "model", "parts": [{"text": "Reply"}]},
                {"role": "user", "parts": [{"text": "Second"}]},
            ]
        }
        assert _extract_last_user_text(body) == "Second"

    def test_empty(self):
        assert _extract_last_user_text({}) is None
        assert _extract_last_user_text({"contents": []}) is None


class TestReplaceUserText:
    def test_replaces_last_user_text(self):
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": "old"}]},
            ]
        }
        _replace_user_text(body, "new")
        assert body["contents"][0]["parts"][0]["text"] == "new"


class TestInjectSystemContext:
    def test_no_existing(self):
        body = {}
        _inject_system_context(body, "Context")
        assert body["systemInstruction"]["parts"][0]["text"] == "Context"

    def test_existing(self):
        body = {"systemInstruction": {"parts": [{"text": "Existing"}]}}
        _inject_system_context(body, "More")
        assert len(body["systemInstruction"]["parts"]) == 2


class TestEmbedContext:
    def test_user_concat(self):
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.embed_target = "user"
        settings.embed_mode = "concat"
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": "Question"}]},
            ]
        }
        _embed_context(body, "Context", settings)
        text = body["contents"][0]["parts"][0]["text"]
        assert "Question" in text
        assert "Context" in text
