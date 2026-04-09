"""ClaudeBackendApiInterpreter — url4 interpreter that calls the direct Anthropic API.

Subclass of :class:`Url4Interpreter`. Used by the ``GET /claude?q=…``
endpoint: the url4-executor splits the expression into ``sources``
(parenthesized group of URLs/text) and ``intent`` (text after ``!``),
then calls our :meth:`process` to produce the final response.

Mirrors :class:`~claude_backend.interpreter.ClaudeInterpreter` byte-for-
byte semantically — the only difference is the transport. The
concatenation rule (``intent`` first, ``sources`` second, separated by
``\\n\\n``) is preserved because existing url4 specs depend on it.

Key differences from the CLI-based interpreter:

- No temp-directory dance. The direct API has no concept of ``cwd``, so
  there's nothing to isolate.
- No subprocess, no exit code to interpret. The response comes back as
  a :class:`CoreMessage`; we return its text.
- Auth errors bubble up as :class:`AuthError` from the OAuth strategy
  instead of non-zero exit codes from the CLI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from screamingface.plugins.claude_backend_api.backend import AnthropicBackend
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter

if TYPE_CHECKING:
    from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiSettings

logger = logging.getLogger(__name__)

# Final fallback model if neither the request nor the plugin settings
# specify one. Matches the plan's locked-in default.
_DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeBackendApiInterpreter(Url4Interpreter):
    """Url4 interpreter that routes to the direct Anthropic Messages API.

    Args:
        app: The FastAPI app (used by the Url4Interpreter base for
            in-process ASGI fetches of relative URLs like /data/<key>).
        settings: The claude-backend-api plugin settings. Provides the
            default model, the interpreter system prompt, and the
            timeout.
        backend: Optional :class:`AnthropicBackend` to inject. Defaults
            to a new instance with the platform's default auth +
            adapter. Tests override this.
    """

    def __init__(
        self,
        app: Any = None,
        settings: ClaudeBackendApiSettings | None = None,
        *,
        backend: AnthropicBackend | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self._backend = backend or AnthropicBackend()

    async def process(self, sources: str, intent: str | None) -> str:
        """Combine intent + sources, send as a user message to Anthropic.

        Matches :class:`ClaudeInterpreter.process` semantics so existing
        url4 specs (e.g. the ``cat-breeds-3sources`` e2e test) work
        unchanged. The combined text becomes a single user message;
        the interpreter system prompt from settings becomes the
        Anthropic ``system`` field.
        """
        combined = f"{intent}\n\n{sources}" if intent and sources else (intent or sources or "")

        if not combined:
            # Empty input — nothing meaningful to ask. Return empty
            # string for parity with the CLI path (which would also
            # produce no output).
            return ""

        messages = [CoreMessage(role="user", content=[TextPart(text=combined)])]

        model = (self.settings.default_model if self.settings else None) or _DEFAULT_MODEL
        system = self.settings.interpreter_system_prompt if self.settings else None
        timeout = self.settings.timeout_seconds if self.settings else 300.0

        result = await self._backend.run(
            messages,
            model=model,
            system=system,
            timeout_seconds=timeout,
        )

        return _extract_text(result)


def _extract_text(msg: CoreMessage) -> str:
    """Pull concatenated text out of a response CoreMessage.

    The AnthropicAdapter packs multiple assistant text blocks (and any
    tool_use, thinking, etc.) into the content list. For the interpreter
    we only care about the text — other block types are ignored for the
    legacy drop-in semantics.
    """
    if isinstance(msg.content, str):
        return msg.content
    chunks: list[str] = []
    for part in msg.content:
        if isinstance(part, TextPart):
            chunks.append(part.text)
    return "".join(chunks)
