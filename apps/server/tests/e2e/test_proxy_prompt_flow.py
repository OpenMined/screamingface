"""E2E tests for the $prompt substitution flow.

Migrated from scripts/test_prompt_e2e.py — tests that the proxy correctly
substitutes $prompt in url4 expressions, stores blobs, and injects resolved
context into the user message.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(30)]


class TestPromptSubstitution:
    """Tests for $prompt url4 specs — context injected into user message."""

    def test_prompt_text_mode(self, claude_client: ClaudeCodeClient):
        """$prompt blob carries the user prompt; resolved text becomes the response.

        The user text goes into the serialized transcript ($prompt blob), the
        spec resolves in-process, and the terminal text *is* the response. So the
        original prompt and the resolved robots.txt source are both in
        ``response_text``.
        """
        resp = claude_client.send_message("Summarize this for me")

        assert resp.status_code == 200

        text = resp.response_text
        assert "Summarize this" in text, f"original prompt missing: {text[:200]}"
        assert "User-agent" in text, f"resolved robots.txt missing: {text[:200]}"

    def test_prompt_skips_tool_result(self, claude_client: ClaudeCodeClient):
        """A pure-tool_result final turn contributes no text to the $prompt blob.

        ``_extract_turns`` collects only ``type="text"`` blocks. The final user
        turn is purely a ``tool_result`` block, so it yields empty text and is
        dropped from the transcript. The earlier "Hello" user turn is what drives
        the resolved response; the tool_result content/id never appear.
        """
        # Set up multi-turn: user → assistant (tool_use) → user (tool_result)
        claude_client.send_message("Hello", track_history=True)
        claude_client.inject_assistant_response(
            [
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"cmd": "ls"}},
            ]
        )

        resp = claude_client.send_tool_result("t1", "file.txt")

        assert resp.status_code == 200

        text = resp.response_text
        # The prior plain-text user turn survives in the transcript:
        assert "User: Hello" in text, f"prior user turn missing: {text[:200]}"
        # The pure tool_result turn contributed no text — its id and payload
        # are absent from the resolved response:
        assert "t1" not in text
        assert "file.txt" not in text
        # Terminal resolution still ran (robots.txt source appended):
        assert "User-agent" in text, f"resolved url4 source missing: {text[:200]}"

    def test_blob_dedup(self):
        """Same prompt text → same blob key (SHA-256 content hash)."""
        from screamingface.plugins.data_store.storage import BlobStore

        store = BlobStore()
        key1 = store.store(b"What breed for apartments?", "text/plain")
        key2 = store.store(b"What breed for apartments?", "text/plain")
        key3 = store.store(b"Different prompt", "text/plain")

        assert key1 == key2, f"dedup failed: {key1} != {key2}"
        assert key1 != key3, f"different content same key: {key1} == {key3}"

    def test_no_prompt_system_clean(self, claude_client: ClaudeCodeClient):
        """With $prompt spec, url4 context goes into user msg, NOT system prompt."""
        resp = claude_client.send_message("Hello test", system="Be helpful")

        assert resp.status_code == 200

        # System prompt should NOT have url4 content (it goes into user msg with $prompt)
        system = str(resp.forwarded_system or "")
        assert "User-agent" not in system, f"url4 context leaked into system prompt: {system[:200]}"
