"""Url4 interpreter for aigw_*_backend plugins.

Mirrors ClaudeBackendApiInterpreter.process semantics: combines intent +
sources, builds a single user CoreMessage, sends to AigwBackend, returns
the assistant text. The shared concatenation rule (intent first,
sources second, separated by \\n\\n) is preserved so existing url4
specs work unchanged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from screamingface.plugins.llm_base.messages import CoreMessage, TextPart, extract_text
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.scope import Env

from .backend import AigwBackend

if TYPE_CHECKING:
    from .settings import AigwBackendApiSettingsBase

logger = logging.getLogger(__name__)

_FALLBACK_MODEL = "anthropic/claude-sonnet-4-5"


class AigwInterpreter(Url4Interpreter):
    def __init__(
        self,
        app: Any = None,
        settings: AigwBackendApiSettingsBase | None = None,
        *,
        backend: AigwBackend | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        if backend is not None:
            self._backend = backend
        elif settings is not None:
            self._backend = AigwBackend(
                gateway_url=settings.gateway_url,
                profile_name=settings.auth_profile,
            )
        else:
            self._backend = AigwBackend()

    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
        combined = f"{intent}\n\n{sources}" if intent and sources else (intent or sources or "")
        if not combined:
            return ""

        messages = [CoreMessage(role="user", content=[TextPart(text=combined)])]

        model = (self.settings.default_model if self.settings else None) or _FALLBACK_MODEL
        system = self.settings.interpreter_system_prompt if self.settings else None
        timeout = self.settings.timeout_seconds if self.settings else 300.0

        result = await self._backend.run(
            messages,
            model=model,
            system=system,
            timeout_seconds=timeout,
        )
        return extract_text(result)
