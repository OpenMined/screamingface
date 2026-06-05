"""E2E tests for multi-turn conversation handling through the proxy."""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(30)]


class TestMultiTurn:
    """Multi-turn conversation behavior under the terminal cutover.

    The active spec is the ``$prompt`` spec ``(robots.txt)!$prompt``. The proxy
    serializes the FULL conversation transcript (``serialize_transcript`` over
    ``_extract_turns``) into the ``$prompt`` blob, resolves the expression
    in-process, and the resolved text *becomes* the response. So the conversation
    history is observable in ``response_text``, not in a forwarded ``messages``
    array (there is no upstream).
    """

    def test_multi_turn_history_preserved(self, claude_client: ClaudeCodeClient):
        """Prior turns are preserved in the transcript that drives the response."""
        # First turn: the resolved transcript echoes the lone user turn.
        resp1 = claude_client.send_message("First message")
        assert resp1.status_code == 200
        assert "First message" in resp1.response_text

        # Inject assistant response for multi-turn
        claude_client.inject_assistant_response(
            [
                {"type": "text", "text": "I received your first message."},
            ]
        )

        # Second turn: the full transcript (all three turns) drives the response,
        # rendered by serialize_transcript as "User:/Assistant:" lines.
        resp2 = claude_client.send_message("Second message")
        assert resp2.status_code == 200

        text = resp2.response_text
        assert "User: First message" in text, f"first user turn missing: {text[:300]}"
        assert "Assistant: I received your first message." in text, (
            f"assistant turn missing: {text[:300]}"
        )
        assert "User: Second message" in text, f"second user turn missing: {text[:300]}"

    def test_system_reminders_not_stripped_by_extract_turns(self, claude_client: ClaudeCodeClient):
        """<system-reminder> text is NOT filtered by ``_extract_turns``.

        ``_extract_turns`` concatenates every ``type="text"`` block of a turn
        verbatim; it has no system-reminder awareness. So both the reminder
        content and the user's question land in the transcript and therefore in
        ``response_text``. (This documents the real terminal behavior — the old
        "reminders filtered" forwarding semantics no longer apply.)
        """
        claude_client.add_system_reminder("You have access to tools: Bash, Read, Write")

        resp = claude_client.send_message("What can you do?")
        assert resp.status_code == 200

        text = resp.response_text
        # Reminder text is carried through (NOT stripped):
        assert "You have access to tools" in text, f"reminder text missing: {text[:300]}"
        # The user's actual question is also present:
        assert "What can you do?" in text, f"user question missing: {text[:300]}"

    def test_tool_use_tool_result_cycle(self, claude_client: ClaudeCodeClient):
        """tool_use / tool_result blocks contribute no transcript text.

        ``_extract_turns`` only collects ``type="text"`` content blocks. A turn
        whose content is purely ``tool_use`` (assistant) or ``tool_result``
        (user) yields empty text and is dropped from the transcript. So after a
        user-text -> assistant-tool_use -> user-tool_result cycle, only the
        leading user text turn survives in ``response_text``.
        """
        # User asks something (plain text turn)
        resp1 = claude_client.send_message("List files in current directory")
        assert resp1.status_code == 200

        # Simulate assistant using a tool (pure tool_use → no text)
        claude_client.inject_assistant_response(
            [
                {
                    "type": "tool_use",
                    "id": "toolu_01ABC",
                    "name": "bash",
                    "input": {"command": "ls"},
                },
            ]
        )

        # User sends tool result (pure tool_result → no text)
        resp2 = claude_client.send_tool_result(
            "toolu_01ABC",
            "file1.txt\nfile2.py\nREADME.md",
        )
        assert resp2.status_code == 200

        text = resp2.response_text
        # The leading user text turn is preserved in the transcript:
        assert "User: List files in current directory" in text, (
            f"leading user turn missing: {text[:300]}"
        )
        # The tool_use/tool_result blocks carry no text, so the tool id and
        # tool output never reach the transcript:
        assert "toolu_01ABC" not in text
        assert "file1.txt" not in text
        # The resolved url4 source is still appended (terminal resolution ran):
        assert "User-agent" in text, f"resolved url4 source missing: {text[:300]}"
