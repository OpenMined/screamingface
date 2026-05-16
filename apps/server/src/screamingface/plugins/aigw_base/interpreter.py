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

from screamingface.plugins.llm_base.errors import BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart, extract_text
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.scope import Env

from .backend import AigwBackend

if TYPE_CHECKING:
    from .settings import AigwBackendApiSettingsBase

logger = logging.getLogger(__name__)

_FALLBACK_MODEL = "gateway/default"


class AigwInterpreter(Url4Interpreter):
    def __init__(
        self,
        app: Any = None,
        settings: AigwBackendApiSettingsBase | None = None,
        *,
        backend: AigwBackend | None = None,
        gateway_provider: str | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        if backend is not None:
            self._backend = backend
        elif settings is not None:
            if not gateway_provider:
                msg = "gateway_provider is required when constructing AigwInterpreter from settings"
                raise ValueError(msg)
            self._backend = AigwBackend(
                gateway_url=settings.gateway_url,
                profile_name=settings.auth_profile,
                gateway_provider=gateway_provider,
            )
        else:
            msg = "AigwInterpreter requires either backend or settings with gateway_provider"
            raise ValueError(msg)

    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
        combined = f"{intent}\n\n{sources}" if intent and sources else (intent or sources or "")
        if not combined:
            return ""

        messages = [CoreMessage(role="user", content=[TextPart(text=combined)])]

        model = (self.settings.default_model if self.settings else None) or _FALLBACK_MODEL
        system = self.settings.interpreter_system_prompt if self.settings else None
        timeout = self.settings.timeout_seconds if self.settings else 300.0

        try:
            result = await self._backend.run(
                messages,
                model=model,
                system=system,
                timeout_seconds=timeout,
            )
        except BackendError as exc:
            fallback_model = getattr(self.settings, "fallback_model", None)
            if not (
                exc.status == 429
                and isinstance(fallback_model, str)
                and fallback_model
                and fallback_model != model
            ):
                raise
            logger.warning(
                "aigw interpreter primary model %s rate limited; retrying fallback model %s",
                model,
                fallback_model,
            )
            result = await self._backend.run(
                messages,
                model=fallback_model,
                system=system,
                timeout_seconds=timeout,
            )
        return extract_text(result)
