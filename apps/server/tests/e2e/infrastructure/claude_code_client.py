"""Claude Code client emulator for e2e proxy testing.

Builds realistic Claude Code request payloads (multi-turn conversations,
system-reminder injection, tool_use/tool_result cycles) and sends them
to the claude-frontend proxy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ProxyResponse:
    """Response from the proxy, with helpers for httpbin echo mode."""

    status_code: int
    body: dict[str, Any]
    headers: dict[str, str]

    @property
    def echoed_body(self) -> dict[str, Any]:
        """The forwarded request body echoed back by httpbin ``/anything``."""
        return self.body.get("json", {})

    @property
    def forwarded_system(self) -> str | list[dict[str, Any]] | None:
        """System prompt from the echoed request body."""
        return self.echoed_body.get("system")

    @property
    def forwarded_messages(self) -> list[dict[str, Any]]:
        """Messages array from the echoed request body."""
        return self.echoed_body.get("messages", [])

    @property
    def last_user_content(self) -> str | list[dict[str, Any]]:
        """Content of the last user message in the echoed body."""
        for msg in reversed(self.forwarded_messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    @property
    def last_user_text(self) -> str:
        """Plain text of the last user message (handles both str and blocks)."""
        content = self.last_user_content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict)
                and b.get("type") == "text"
                and not b.get("text", "").lstrip().startswith("<system-reminder>")
            ]
            return texts[-1] if texts else ""
        return str(content)


@dataclass
class ClaudeCodeClient:
    """Emulates Claude Code CLI requests to the proxy."""

    proxy_url: str
    api_key: str = "test-key"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024

    _messages: list[dict[str, Any]] = field(default_factory=list, init=False)
    _system_reminders: list[str] = field(default_factory=list, init=False)

    def send_message(
        self,
        content: str | list[dict[str, Any]],
        *,
        system: str | list[dict[str, Any]] | None = None,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float = 30,
        extra_body: dict[str, Any] | None = None,
        track_history: bool = True,
    ) -> ProxyResponse:
        """Send a user message to the proxy.

        If *track_history* is True (default), the message is appended to the
        internal conversation history for multi-turn testing.
        """
        # Build user message content blocks
        if isinstance(content, str):
            user_content: str | list[dict[str, Any]] = content
            if self._system_reminders:
                blocks: list[dict[str, Any]] = [
                    {"type": "text", "text": f"<system-reminder>\n{r}\n</system-reminder>"}
                    for r in self._system_reminders
                ]
                blocks.append({"type": "text", "text": content})
                user_content = blocks
        else:
            user_content = content
            if self._system_reminders:
                reminder_blocks = [
                    {"type": "text", "text": f"<system-reminder>\n{r}\n</system-reminder>"}
                    for r in self._system_reminders
                ]
                user_content = reminder_blocks + list(content)

        user_msg = {"role": "user", "content": user_content}

        messages = list(self._messages) + [user_msg]
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            body["system"] = system
        if stream:
            body["stream"] = True
        if tools:
            body["tools"] = tools
        if extra_body:
            body.update(extra_body)

        headers = {"x-api-key": self.api_key}
        if extra_headers:
            headers.update(extra_headers)

        resp = httpx.post(
            f"{self.proxy_url}/v1/messages",
            json=body,
            headers=headers,
            timeout=timeout,
        )

        if track_history:
            self._messages.append(user_msg)

        return ProxyResponse(
            status_code=resp.status_code,
            body=resp.json(),
            headers=dict(resp.headers),
        )

    def send_tool_result(
        self,
        tool_use_id: str,
        content: str | list[dict[str, Any]],
        *,
        is_error: bool = False,
        system: str | list[dict[str, Any]] | None = None,
        track_history: bool = True,
    ) -> ProxyResponse:
        """Send a tool_result message (continues a multi-turn conversation)."""
        if isinstance(content, str):
            tool_content: list[dict[str, Any]] = [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
            ]
        else:
            tool_content = [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}]
        if is_error:
            tool_content[0]["is_error"] = True

        return self.send_message(
            tool_content,
            system=system,
            track_history=track_history,
        )

    def inject_assistant_response(self, content: list[dict[str, Any]]) -> None:
        """Add an assistant response to history (for setting up multi-turn context)."""
        self._messages.append({"role": "assistant", "content": content})

    def add_system_reminder(self, text: str) -> None:
        """Add a system-reminder block injected into subsequent user messages."""
        self._system_reminders.append(text)

    def clear_system_reminders(self) -> None:
        self._system_reminders.clear()

    def reset(self) -> None:
        """Clear conversation history and system reminders."""
        self._messages.clear()
        self._system_reminders.clear()
