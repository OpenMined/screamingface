"""Unit tests for ``claude_frontend.context_filter``.

Pure-module tests — no FastAPI fixtures, no httpx, no I/O. Run with::

    cd apps/server
    uv run pytest src/screamingface/plugins/claude_frontend/tests/test_context_filter.py -v
"""

from __future__ import annotations

import copy
import json

import pytest

from screamingface.plugins.claude_frontend.context_filter import (
    ASSISTANT_ALIASES,
    ASSISTANT_BLOCK_TYPES,
    USER_ALIASES,
    USER_BLOCK_TYPES,
    apply_context_filter,
    parse_filter_entries,
)


# ----------------------------------------------------------------------------
# Fixture
# ----------------------------------------------------------------------------


def _fixture_full_body() -> dict:
    """Return a request body exercising every interesting block type and shape.

    Layout (deliberately rich, used by every TestApplyContextFilter case):

    Top-level:
      - system   (list of two text blocks)
      - tools    (two tool definitions)
      - model    (always present, never filtered in/out — purely informative)

    Messages:
      [0] user      — single text block
      [1] assistant — text + tool_use blocks
      [2] user      — single tool_result with file content
      [3] assistant — text + thinking + server_tool_use blocks
      [4] user      — text + image blocks
      [5] user      — string-shorthand content (the "content is a str" case)
      [6] user      — system-reminder text block (must be kept by user:text;
                       sanitization is the LLM consumer's problem)
      [7] tool      — defensive: a non-{user,assistant} role that must always
                       be dropped, even with system:*/user:*/assistant:*/tools:*
      [8] user      — content block with an unknown future-block type
    """
    return {
        "model": "claude-opus-4-6",
        "max_tokens": 16000,
        "system": [
            {"type": "text", "text": "You are helpful."},
            {"type": "text", "text": "Be concise."},
        ],
        "tools": [
            {"name": "Read", "description": "Reads a file", "input_schema": {"type": "object"}},
            {"name": "Bash", "description": "Runs a shell command", "input_schema": {"type": "object"}},
        ],
        "messages": [
            # 0
            {"role": "user", "content": [{"type": "text", "text": "List the python files."}]},
            # 1
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll list them."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Bash",
                        "input": {"command": "ls *.py"},
                    },
                ],
            },
            # 2
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01",
                        "content": "foo.py\nbar.py\nbaz.py\n",
                    }
                ],
            },
            # 3
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Found three files."},
                    {
                        "type": "thinking",
                        "thinking": "Let me also search the web for stats.",
                        "signature": "sig-abc",
                    },
                    {
                        "type": "server_tool_use",
                        "id": "stu_01",
                        "name": "web_search",
                        "input": {"query": "python file size avg"},
                    },
                ],
            },
            # 4
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Here's a screenshot."},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": "iVBOR..."},
                    },
                ],
            },
            # 5 — string shorthand
            {"role": "user", "content": "hi"},
            # 6 — system-reminder
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<system-reminder>\nbe nice\n</system-reminder>"}
                ],
            },
            # 7 — defensive: tool role (must always be dropped)
            {"role": "tool", "content": "ignored"},
            # 8 — unknown future block type
            {
                "role": "user",
                "content": [
                    {"type": "future_block", "data": "from the year 2099"},
                ],
            },
        ],
    }


# ----------------------------------------------------------------------------
# TestParseFilterEntries
# ----------------------------------------------------------------------------


class TestParseFilterEntries:
    def test_empty_list_returns_empty_filter(self):
        p = parse_filter_entries([])
        assert p.include_system is False
        assert p.include_tools is False
        assert p.user_types == set()
        assert p.assistant_types == set()

    def test_user_text(self):
        p = parse_filter_entries(["user:text"])
        assert p.user_types == {"text"}
        assert p.assistant_types == set()
        assert p.include_system is False
        assert p.include_tools is False

    def test_user_star_expands_all_user_blocks(self):
        p = parse_filter_entries(["user:*"])
        assert p.user_types == set(USER_BLOCK_TYPES)

    def test_assistant_star_expands_all_assistant_blocks(self):
        p = parse_filter_entries(["assistant:*"])
        assert p.assistant_types == set(ASSISTANT_BLOCK_TYPES)

    def test_system_star(self):
        p = parse_filter_entries(["system:*"])
        assert p.include_system is True
        assert p.include_tools is False
        assert p.user_types == set()

    def test_tools_star(self):
        p = parse_filter_entries(["tools:*"])
        assert p.include_tools is True
        assert p.include_system is False

    def test_system_with_explicit_type_warns_and_falls_back(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["system:text"])
        assert p.include_system is False
        assert any("system" in r.message and "*" in r.message for r in caplog.records)

    def test_tools_with_explicit_type_warns_and_falls_back(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["tools:tool_use"])
        assert p.include_tools is False
        assert any("tools" in r.message for r in caplog.records)

    def test_alias_tool_call_expands_in_assistant(self):
        p = parse_filter_entries(["assistant:tool_call"])
        assert p.assistant_types == {"tool_use", "server_tool_use", "mcp_tool_use"}

    def test_alias_tool_call_unknown_in_user(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["user:tool_call"])
        assert p.user_types == set()
        assert any("tool_call" in r.message for r in caplog.records)

    def test_alias_tool_result_in_assistant_expands_to_server_variants(self):
        p = parse_filter_entries(["assistant:tool_result"])
        expected = {
            "web_search_tool_result",
            "web_fetch_tool_result",
            "code_execution_tool_result",
            "bash_code_execution_tool_result",
            "text_editor_code_execution_tool_result",
            "tool_search_tool_result",
            "mcp_tool_result",
        }
        assert p.assistant_types == expected

    def test_literal_tool_result_in_user_kept(self):
        p = parse_filter_entries(["user:tool_result"])
        assert p.user_types == {"tool_result"}

    def test_alias_thinking_in_assistant(self):
        p = parse_filter_entries(["assistant:thinking"])
        assert p.assistant_types == {"thinking", "redacted_thinking"}

    def test_unknown_scope_warns_and_skips(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["wat:text"])
        assert p == parse_filter_entries([])
        assert any("wat" in r.message for r in caplog.records)

    def test_unknown_block_type_warns_keeps_known(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["user:text,bogus"])
        assert p.user_types == {"text"}
        assert any("bogus" in r.message for r in caplog.records)

    def test_multiple_entries_union(self):
        p = parse_filter_entries(["user:text", "user:image"])
        assert p.user_types == {"text", "image"}

    def test_duplicate_entry_idempotent(self):
        p = parse_filter_entries(["user:text", "user:text"])
        assert p.user_types == {"text"}

    def test_whitespace_tolerated(self):
        p = parse_filter_entries([" user : text , image "])
        assert p.user_types == {"text", "image"}

    def test_malformed_entry_no_colon_warns_skips(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["usertext"])
        assert p == parse_filter_entries([])
        assert any("usertext" in r.message for r in caplog.records)

    def test_malformed_entry_empty_types_warns_skips(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries(["user:"])
        assert p == parse_filter_entries([])
        assert any("user:" in r.message for r in caplog.records)

    def test_alias_in_combo_with_literals_in_assistant(self):
        p = parse_filter_entries(["assistant:text,tool_call"])
        assert p.assistant_types == {"text", "tool_use", "server_tool_use", "mcp_tool_use"}

    def test_non_string_entry_skipped(self, caplog):
        with caplog.at_level("WARNING"):
            p = parse_filter_entries([123])  # type: ignore[list-item]
        assert p == parse_filter_entries([])


# ----------------------------------------------------------------------------
# TestApplyContextFilter
# ----------------------------------------------------------------------------


def _user_text_blocks(out: dict) -> list[dict]:
    """Helper: collect text blocks from all user messages in the filtered output."""
    result: list[dict] = []
    for msg in out.get("messages", []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            result.append({"type": "text", "text": content})
        elif isinstance(content, list):
            result.extend(b for b in content if b.get("type") == "text")
    return result


def _assistant_blocks(out: dict) -> list[dict]:
    """Helper: collect all assistant content blocks from the filtered output."""
    result: list[dict] = []
    for msg in out.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            result.extend(content)
    return result


def _user_blocks(out: dict) -> list[dict]:
    """Helper: collect all user content blocks from the filtered output."""
    result: list[dict] = []
    for msg in out.get("messages", []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            result.append({"type": "text", "text": content})
        elif isinstance(content, list):
            result.extend(content)
    return result


class TestApplyContextFilter:
    def test_default_filter_user_text(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["user:text"])

        assert "system" not in out
        assert "tools" not in out
        # Only user text blocks survive (turns 0, 4, 5-shorthand, 6-reminder)
        text_blocks = _user_text_blocks(out)
        texts = [b["text"] for b in text_blocks]
        assert "List the python files." in texts
        assert "Here's a screenshot." in texts
        assert "hi" in texts
        assert any("system-reminder" in t for t in texts)
        # No assistant content
        assert _assistant_blocks(out) == []

    def test_user_star_keeps_all_user_block_types(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["user:*"])
        types = {b["type"] for b in _user_blocks(out)}
        assert "text" in types
        assert "tool_result" in types
        assert "image" in types
        # future_block is unknown — dropped (user:* expands to known types only)
        assert "future_block" not in types

    def test_assistant_text_only(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["assistant:text"])
        types = {b["type"] for b in _assistant_blocks(out)}
        assert types == {"text"}

    def test_assistant_tool_call_alias(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["assistant:tool_call"])
        types = {b["type"] for b in _assistant_blocks(out)}
        assert types == {"tool_use", "server_tool_use"}  # mcp_tool_use absent in fixture

    def test_user_tool_result_only(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["user:tool_result"])
        blocks = _user_blocks(out)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "tool_result"
        assert "foo.py" in blocks[0]["content"]

    def test_combined_reflection_filter(self):
        body = _fixture_full_body()
        out = apply_context_filter(
            body, ["user:text,tool_result", "assistant:text,tool_call"]
        )
        user_types = {b["type"] for b in _user_blocks(out)}
        assert user_types == {"text", "tool_result"}
        asst_types = {b["type"] for b in _assistant_blocks(out)}
        assert asst_types == {"text", "tool_use", "server_tool_use"}
        # Negative: thinking and image and system-tools are absent
        assert "thinking" not in asst_types
        assert "image" not in user_types
        assert "system" not in out
        assert "tools" not in out

    def test_system_only(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["system:*"])
        assert "system" in out
        assert "messages" not in out
        assert "tools" not in out

    def test_tools_only(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["tools:*"])
        assert "tools" in out
        assert "system" not in out
        assert "messages" not in out

    def test_full_dump(self):
        body = _fixture_full_body()
        out = apply_context_filter(
            body, ["system:*", "tools:*", "user:*", "assistant:*"]
        )
        assert "system" in out
        assert "tools" in out
        assert "messages" in out
        # Defensive: tool role still dropped, even on full dump
        roles = [m["role"] for m in out["messages"]]
        assert "tool" not in roles
        assert "user" in roles
        assert "assistant" in roles
        # String-shorthand turn 5 preserved as string
        shorthand = [
            m for m in out["messages"]
            if m["role"] == "user" and isinstance(m.get("content"), str)
        ]
        assert len(shorthand) == 1
        assert shorthand[0]["content"] == "hi"

    def test_empty_filter_returns_empty_dict(self):
        body = _fixture_full_body()
        assert apply_context_filter(body, []) == {}

    def test_messages_with_no_matching_blocks_dropped(self):
        # Body without any tool calls
        body = {
            "model": "claude-opus-4-6",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hi"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
            ],
        }
        out = apply_context_filter(body, ["assistant:tool_call"])
        assert "messages" not in out

    def test_string_content_shorthand_kept_for_text_filter(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["user:text"])
        shorthand = [
            m for m in out["messages"]
            if m["role"] == "user" and isinstance(m.get("content"), str)
        ]
        assert len(shorthand) == 1
        assert shorthand[0]["content"] == "hi"

    def test_string_content_shorthand_dropped_for_non_text_filter(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["user:image"])
        # The string-shorthand turn must NOT appear (it's text-only)
        shorthand = [
            m for m in out.get("messages", [])
            if isinstance(m.get("content"), str)
        ]
        assert shorthand == []

    def test_message_role_other_than_user_assistant_dropped(self):
        body = _fixture_full_body()
        out = apply_context_filter(
            body, ["system:*", "tools:*", "user:*", "assistant:*"]
        )
        assert all(m["role"] in ("user", "assistant") for m in out["messages"])

    def test_unknown_block_type_in_body_dropped_silently(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["user:*"])
        # turn 8 only has future_block — should produce no kept content
        # so the message itself is dropped (no kept blocks → not appended)
        # Verify no future_block leaked anywhere
        for block in _user_blocks(out):
            assert block.get("type") != "future_block"

    def test_does_not_mutate_input_body(self):
        body = _fixture_full_body()
        snapshot = copy.deepcopy(body)
        apply_context_filter(body, ["user:*", "assistant:*", "system:*", "tools:*"])
        assert body == snapshot

    def test_preserves_block_field_ordering_inside_kept_blocks(self):
        body = _fixture_full_body()
        out = apply_context_filter(body, ["assistant:tool_call"])
        tool_uses = [b for b in _assistant_blocks(out) if b.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        tu = tool_uses[0]
        assert tu["id"] == "toolu_01"
        assert tu["name"] == "Bash"
        assert tu["input"] == {"command": "ls *.py"}

    @pytest.mark.parametrize(
        "filter_entries",
        [
            ["user:text"],
            ["user:*"],
            ["assistant:text"],
            ["assistant:tool_call"],
            ["assistant:thinking"],
            ["user:tool_result"],
            ["user:text,tool_result", "assistant:text,tool_call"],
            ["system:*", "tools:*"],
            ["system:*", "tools:*", "user:*", "assistant:*"],
            [],
        ],
    )
    def test_round_trip_json_serializable(self, filter_entries):
        body = _fixture_full_body()
        out = apply_context_filter(body, filter_entries)
        # Must be json.dumps-serializable without raising
        json.dumps(out, ensure_ascii=False)


# ----------------------------------------------------------------------------
# TestAliasResolution
# ----------------------------------------------------------------------------


class TestAliasResolution:
    def test_assistant_tool_call_includes_mcp_tool_use(self):
        assert "mcp_tool_use" in ASSISTANT_ALIASES["tool_call"]

    def test_assistant_tool_result_includes_all_server_variants(self):
        expected = {
            "web_search_tool_result",
            "web_fetch_tool_result",
            "code_execution_tool_result",
            "bash_code_execution_tool_result",
            "text_editor_code_execution_tool_result",
            "tool_search_tool_result",
            "mcp_tool_result",
        }
        assert ASSISTANT_ALIASES["tool_result"] == expected

    def test_user_aliases_does_not_define_tool_call(self):
        assert "tool_call" not in USER_ALIASES
