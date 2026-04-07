"""Context filter for the claude-frontend $prompt blob.

Pure module — no FastAPI, no httpx, no I/O. Trivially unit-testable.

The proxy uses ``apply_context_filter`` to curate which parts of an incoming
``/v1/messages`` request body get serialized into the data-store blob that
``$prompt`` resolves to. The filter syntax is documented in
``ClaudeFrontendSettings.context_filter`` and in the desktop session UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Block type vocabulary (matches Anthropic Messages API content block types)
# ----------------------------------------------------------------------------

USER_BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "text",
        "image",
        "document",
        "tool_result",
        "container_upload",
        "search_result",
    }
)

ASSISTANT_BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "text",
        "thinking",
        "redacted_thinking",
        "tool_use",
        "server_tool_use",
        "web_search_tool_result",
        "web_fetch_tool_result",
        "code_execution_tool_result",
        "bash_code_execution_tool_result",
        "text_editor_code_execution_tool_result",
        "tool_search_tool_result",
        "mcp_tool_use",
        "mcp_tool_result",
        "compaction",
    }
)

# Aliases are scope-aware. The literal name ``tool_result`` is also a key in
# ``ASSISTANT_ALIASES`` (expands to all server-side *_tool_result variants),
# but in the user scope it stays as the literal block type.
ASSISTANT_ALIASES: dict[str, frozenset[str]] = {
    "tool_call": frozenset({"tool_use", "server_tool_use", "mcp_tool_use"}),
    "tool_result": frozenset(
        {
            "web_search_tool_result",
            "web_fetch_tool_result",
            "code_execution_tool_result",
            "bash_code_execution_tool_result",
            "text_editor_code_execution_tool_result",
            "tool_search_tool_result",
            "mcp_tool_result",
        }
    ),
    "thinking": frozenset({"thinking", "redacted_thinking"}),
}

USER_ALIASES: dict[str, frozenset[str]] = {
    # Users do not issue tool calls, so no tool_call alias here.
    # tool_result in the user scope is the literal block type, not an alias.
}

VALID_SCOPES: frozenset[str] = frozenset({"system", "tools", "user", "assistant"})


# ----------------------------------------------------------------------------
# Parsed filter
# ----------------------------------------------------------------------------


@dataclass
class ParsedFilter:
    """Resolved view of a list of filter entries."""

    include_system: bool = False
    include_tools: bool = False
    user_types: set[str] = field(default_factory=set)
    assistant_types: set[str] = field(default_factory=set)


# ----------------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------------


def _expand_types(scope: str, raw_types: list[str]) -> set[str]:
    """Resolve a list of raw type tokens (or aliases) to concrete block types.

    Unknown tokens are logged at WARNING level and skipped.
    Returns a set of concrete block type names valid in *scope*.
    """
    if scope == "user":
        valid = USER_BLOCK_TYPES
        aliases = USER_ALIASES
    elif scope == "assistant":
        valid = ASSISTANT_BLOCK_TYPES
        aliases = ASSISTANT_ALIASES
    else:
        return set()

    resolved: set[str] = set()
    for token in raw_types:
        token = token.strip()
        if not token:
            continue
        if token == "*":
            resolved |= set(valid)
            continue
        if token in aliases:
            resolved |= aliases[token]
            continue
        if token in valid:
            resolved.add(token)
            continue
        logger.warning(
            "context_filter: unknown block type %r in scope %r — skipping", token, scope
        )
    return resolved


def parse_filter_entries(entries: list[str]) -> ParsedFilter:
    """Parse a list of ``<scope>:<types>`` entries into a ``ParsedFilter``.

    Multiple entries with the same scope are unioned. Unknown scopes / block
    types are warned-and-skipped — never raised — so a typo can never break
    the proxy's hot path.
    """
    parsed = ParsedFilter()

    for entry in entries:
        if not isinstance(entry, str):
            logger.warning("context_filter: non-string entry %r — skipping", entry)
            continue

        if ":" not in entry:
            logger.warning(
                "context_filter: malformed entry %r (missing ':') — skipping", entry
            )
            continue

        scope_raw, types_raw = entry.split(":", 1)
        scope = scope_raw.strip()
        types_raw = types_raw.strip()

        if scope not in VALID_SCOPES:
            logger.warning("context_filter: unknown scope %r — skipping entry", scope)
            continue

        if not types_raw:
            logger.warning("context_filter: empty types in entry %r — skipping", entry)
            continue

        if scope == "system":
            if types_raw == "*":
                parsed.include_system = True
            else:
                logger.warning(
                    "context_filter: scope 'system' only supports '*', got %r — skipping",
                    types_raw,
                )
            continue

        if scope == "tools":
            if types_raw == "*":
                parsed.include_tools = True
            else:
                logger.warning(
                    "context_filter: scope 'tools' only supports '*', got %r — skipping",
                    types_raw,
                )
            continue

        # user / assistant
        raw_tokens = [t for t in types_raw.split(",")]
        resolved = _expand_types(scope, raw_tokens)
        if scope == "user":
            parsed.user_types |= resolved
        else:
            parsed.assistant_types |= resolved

    return parsed


# ----------------------------------------------------------------------------
# Apply
# ----------------------------------------------------------------------------


def apply_context_filter(body: dict, filter_entries: list[str]) -> dict:
    """Apply *filter_entries* to *body*, returning a curated copy.

    The output mirrors the relevant parts of an Anthropic ``/v1/messages``
    request body — only top-level fields and content blocks the filter opted
    into are present. The input body is never mutated.

    An empty filter list (or one that resolves to nothing) returns ``{}``.
    The caller treats an empty dict as the signal to skip blob creation.
    """
    parsed = parse_filter_entries(filter_entries)
    out: dict = {}

    if parsed.include_system and "system" in body:
        out["system"] = body["system"]

    if parsed.include_tools and "tools" in body:
        out["tools"] = body["tools"]

    if parsed.user_types or parsed.assistant_types:
        filtered_msgs: list[dict] = []
        for msg in body.get("messages", []):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role == "user":
                allowed = parsed.user_types
            elif role == "assistant":
                allowed = parsed.assistant_types
            else:
                continue
            if not allowed:
                continue

            content = msg.get("content")

            # String shorthand: treat as a single text block
            if isinstance(content, str):
                if "text" in allowed:
                    filtered_msgs.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                kept = [
                    block
                    for block in content
                    if isinstance(block, dict) and block.get("type") in allowed
                ]
                if kept:
                    filtered_msgs.append({"role": role, "content": kept})

        if filtered_msgs:
            out["messages"] = filtered_msgs

    return out
