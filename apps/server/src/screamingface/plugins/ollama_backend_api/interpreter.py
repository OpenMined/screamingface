"""Url4 interpreter that routes to a local (or remote) Ollama server.

Mirrors ``CodexBackendApiInterpreter`` — same ``process()`` signature,
same intent+sources concatenation, different backend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from screamingface.plugins.llm_base.messages import CoreMessage, TextPart
from screamingface.plugins.ollama_backend_api.backend import OllamaBackend
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter

if TYPE_CHECKING:
    from screamingface.plugins.ollama_backend_api.plugin import OllamaBackendApiSettings

logger = logging.getLogger(__name__)

# Final fallback model if neither the request nor the plugin settings
# specify one. Chosen as a small, commonly-pulled default.
_DEFAULT_MODEL = "llama3.2"


class OllamaBackendApiInterpreter(Url4Interpreter):
    """Url4 interpreter that routes to the Ollama ``/api/chat`` endpoint.

    Combines resolved sources with the intent text, sends the result as
    a single user message to Ollama, and returns the assistant's text
    reply.
    """

    def __init__(
        self,
        app: Any = None,
        settings: OllamaBackendApiSettings | None = None,
        *,
        backend: OllamaBackend | None = None,
    ) -> None:
        super().__init__(app=app)
        self.settings = settings
        self._backend = backend or _build_backend(settings)

    async def process(self, sources: str, intent: str | None) -> str:
        """Combine intent + sources and send to Ollama.

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


def _build_backend(settings: OllamaBackendApiSettings | None) -> OllamaBackend:
    if settings is None:
        return OllamaBackend()
    from screamingface.plugins.ollama_backend_api.auth import OllamaAuth

    return OllamaBackend(
        base_url=settings.base_url,
        auth=OllamaAuth(api_key=settings.api_key),
    )


def _extract_text(msg: CoreMessage) -> str:
    """Pull concatenated text out of an assistant CoreMessage."""
    if isinstance(msg.content, str):
        return msg.content
    chunks: list[str] = []
    for part in msg.content:
        if isinstance(part, TextPart):
            chunks.append(part.text)
    return "".join(chunks)
