"""Url4 interpreter that routes to the OpenAI Chat Completions API.

Mirrors ClaudeBackendApiInterpreter -- same process() signature, same
intent+sources concatenation, different backend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from screamingface.plugins.codex_backend_api.backend import OpenAIBackend
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.scope import Env

if TYPE_CHECKING:
    from screamingface.plugins.codex_backend_api.plugin import CodexBackendApiSettings

logger = logging.getLogger(__name__)

# Final fallback model if neither the request nor the plugin settings
# specify one.
_DEFAULT_MODEL = "gpt-5.4"


class CodexBackendApiInterpreter(Url4Interpreter):
    """Url4 interpreter that routes to the direct OpenAI API.

    Combines resolved sources with the intent text, sends the result as
    a single user message to the OpenAI Chat Completions endpoint, and
    returns the assistant's text reply.
    """

    def __init__(
        self,
        app: Any = None,
        settings: CodexBackendApiSettings | None = None,
        *,
        backend: OpenAIBackend | None = None,
    ) -> None:
        super().__init__(app=app)
        self.settings = settings
        self._backend = backend or OpenAIBackend()

    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
        """Combine intent + sources and send to OpenAI.

        Concatenation rule: ``intent\\n\\nsources`` (intent first so the
        model sees the instruction before the context).
        """
        parts: list[str] = []
        if intent:
            parts.append(intent)
        if sources:
            parts.append(sources)
        user_text = "\n\n".join(parts) if parts else ""

        model = (self.settings.default_model if self.settings else None) or _DEFAULT_MODEL
        system = (
            self.settings.interpreter_system_prompt
            if self.settings
            else "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        )

        messages = [CoreMessage(role="user", content=[TextPart(text=user_text)])]

        result = await self._backend.run(
            messages,
            model=model,
            system=system,
            max_tokens=16000,
        )

        return _extract_text(result)


def _extract_text(msg: CoreMessage) -> str:
    """Pull concatenated text out of an assistant CoreMessage."""
    if isinstance(msg.content, str):
        return msg.content
    chunks: list[str] = []
    for part in msg.content:
        if isinstance(part, TextPart):
            chunks.append(part.text)
    return "".join(chunks)
