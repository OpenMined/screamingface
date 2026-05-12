"""Url4 interpreter for Gemini backend."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from screamingface.plugins.gemini_backend_api.backend import GeminiBackend
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.scope import Env

if TYPE_CHECKING:
    from screamingface.plugins.gemini_backend_api.plugin import GeminiBackendApiSettings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiBackendApiInterpreter(Url4Interpreter):
    def __init__(
        self,
        app: Any = None,
        settings: GeminiBackendApiSettings | None = None,
        *,
        backend: GeminiBackend | None = None,
    ) -> None:
        super().__init__(app=app)
        self.settings = settings
        self._backend = backend or GeminiBackend()

    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
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
        result = await self._backend.run(messages, model=model, system=system, max_tokens=16000)
        return _extract_text(result)


def _extract_text(msg: CoreMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return "".join(p.text for p in msg.content if isinstance(p, TextPart))
