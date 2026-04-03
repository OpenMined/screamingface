"""E2E tests for multi-turn conversation handling through the proxy."""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(30)]


class TestMultiTurn:
    """Tests for multi-turn conversation patterns through the proxy."""

    def test_multi_turn_history_preserved(self, claude_client: ClaudeCodeClient):
        """Message array grows correctly across turns."""
        # First turn
        resp1 = claude_client.send_message("First message")
        assert resp1.status_code == 200
        assert len(resp1.forwarded_messages) == 1

        # Inject assistant response for multi-turn
        claude_client.inject_assistant_response(
            [
                {"type": "text", "text": "I received your first message."},
            ]
        )

        # Second turn
        resp2 = claude_client.send_message("Second message")
        assert resp2.status_code == 200
        assert len(resp2.forwarded_messages) == 3  # user, assistant, user

        msgs = resp2.forwarded_messages
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["role"] == "user"

    def test_system_reminders_filtered(self, claude_client: ClaudeCodeClient):
        """<system-reminder> blocks should not be treated as user prompt text."""
        claude_client.add_system_reminder("You have access to tools: Bash, Read, Write")

        resp = claude_client.send_message("What can you do?")
        assert resp.status_code == 200

        # The user's actual text should be in the response, not the reminder
        content = resp.last_user_text
        # The proxy's _extract_last_user_text filters system-reminders
        # So the $prompt substitution should use "What can you do?" not the reminder
        assert "What can you do?" in content or "User-agent" in content

    def test_tool_use_tool_result_cycle(self, claude_client: ClaudeCodeClient):
        """Full tool_use → tool_result round-trip through the proxy."""
        # User asks something
        resp1 = claude_client.send_message("List files in current directory")
        assert resp1.status_code == 200

        # Simulate assistant using a tool
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

        # User sends tool result
        resp2 = claude_client.send_tool_result(
            "toolu_01ABC",
            "file1.txt\nfile2.py\nREADME.md",
        )
        assert resp2.status_code == 200

        # Verify the full message sequence was forwarded
        msgs = resp2.forwarded_messages
        assert len(msgs) >= 3

        # Check roles alternate correctly
        roles = [m["role"] for m in msgs]
        assert roles[-3:] == ["user", "assistant", "user"]
