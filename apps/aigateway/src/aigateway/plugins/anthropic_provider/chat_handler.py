from __future__ import annotations

import hashlib
from typing import Any

import litellm

# Claude Code 2.1.142 computes this attribution block from the first user
# message and sends it as the first system block. LiteLLM filters this block
# when it appears as a chat `role=system` message, but preserves it when passed
# via Anthropic's provider-specific top-level `system` parameter.
_CLAUDE_CODE_VERSION = "2.1.142"
_FINGERPRINT_SALT = "59cf53e54c78"
_FINGERPRINT_INDICES = (4, 7, 20)
_BILLING_HEADER_PREFIX = "x-anthropic-billing-header:"


def uses_claude_code_attribution(api_key: Any) -> bool:
    """Claude-Code attribution (the billing-header system block) belongs only
    on OAuth subscription traffic. Raw API keys are billed directly and must
    not carry the spoofed block (SF-244 audit F02)."""
    return isinstance(api_key, str) and api_key.startswith("sk-ant-oat")


def _prepared_body(body: dict[str, Any]) -> dict[str, Any]:
    if uses_claude_code_attribution(body.get("api_key")):
        return prepare_claude_code_body(body)
    return body


async def chat_completion(body: dict[str, Any]) -> Any:
    return await litellm.acompletion(**_prepared_body(body))


async def chat_completion_stream(body: dict[str, Any]) -> Any:
    return await litellm.acompletion(**_prepared_body(body))


def prepare_claude_code_body(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    messages = out.get("messages") or []
    if not isinstance(messages, list):
        return out

    existing_system_blocks = _content_to_text_blocks(out.get("system"))
    if _starts_with_billing_header(existing_system_blocks):
        system_blocks = list(existing_system_blocks)
        should_append_existing_system = False
    else:
        system_blocks = [
            {"type": "text", "text": _build_billing_header(_first_user_text(messages))}
        ]
        should_append_existing_system = True

    non_system_messages: list[Any] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "system":
            non_system_messages.append(message)
            continue
        system_blocks.extend(_content_to_text_blocks(message.get("content")))

    if should_append_existing_system:
        system_blocks.extend(existing_system_blocks)

    out["messages"] = non_system_messages
    out["system"] = system_blocks
    return out


def _first_user_text(messages: list[Any]) -> str:
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        return text
    return ""


def _compute_fingerprint(first_user_text: str) -> str:
    chars = "".join(
        first_user_text[index] if index < len(first_user_text) else "0"
        for index in _FINGERPRINT_INDICES
    )
    raw = f"{_FINGERPRINT_SALT}{chars}{_CLAUDE_CODE_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:3]


def _build_billing_header(first_user_text: str) -> str:
    fingerprint = _compute_fingerprint(first_user_text)
    return (
        "x-anthropic-billing-header: "
        f"cc_version={_CLAUDE_CODE_VERSION}.{fingerprint}; "
        "cc_entrypoint=cli; cch=00000;"
    )


def _starts_with_billing_header(blocks: list[dict[str, str]]) -> bool:
    if not blocks:
        return False
    return blocks[0].get("text", "").startswith(_BILLING_HEADER_PREFIX)


def _content_to_text_blocks(content: Any) -> list[dict[str, str]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return []

    blocks: list[dict[str, str]] = []
    for item in content:
        if isinstance(item, str):
            if item:
                blocks.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            blocks.append({"type": "text", "text": text})
    return blocks
