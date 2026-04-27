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
        """$prompt in intent position: user msg replaced with 'prompt + resolved context'."""
        resp = claude_client.send_message("Summarize this for me")

        assert resp.status_code == 200

        content = resp.last_user_text
        assert "Summarize this" in content, f"original prompt missing: {content[:200]}"
        assert "User-agent" in content, f"resolved robots.txt missing: {content[:200]}"

    def test_prompt_skips_tool_result(self, claude_client: ClaudeCodeClient):
        """Last user msg is pure tool_result → $prompt substitution skipped."""
        # Set up multi-turn: user → assistant (tool_use) → user (tool_result)
        claude_client.send_message("Hello", track_history=True)
        claude_client.inject_assistant_response(
            [
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"cmd": "ls"}},
            ]
        )

        resp = claude_client.send_tool_result("t1", "file.txt")

        assert resp.status_code == 200

        # The tool_result should be preserved as-is, not substituted
        msgs = resp.forwarded_messages
        last_user = msgs[-1] if msgs else None
        assert last_user is not None

        content = last_user.get("content", "")
        if isinstance(content, list):
            has_tool_result = any(
                b.get("type") == "tool_result" for b in content if isinstance(b, dict)
            )
            assert has_tool_result, f"tool_result not preserved: {content}"

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
