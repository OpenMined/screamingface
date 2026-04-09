"""llm-base SF plugin.

Registers no routes, no settings, no hooks. Exists only to be discoverable
by the SF plugin loader so other plugins can declare
``depends = ["llm-base"]`` and the dependency machinery handles activation
ordering.

The public API of the plugin is the Python import surface exposed by
``screamingface.plugins.llm_base.__init__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class LlmBasePlugin(Plugin):
    name = "llm-base"
    description = (
        "Shared ABCs and types for multi-backend LLM providers "
        "(Anthropic, OpenAI, Gemini, Qwen, Ollama, …). Provides CoreMessage, "
        "Backend, AuthStrategy, Adapter, and the cross-platform "
        "CredentialStore. No routes or settings of its own — other plugins "
        "import from it and build concrete provider backends on top."
    )
    depends: list[str] = []
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        # Nothing to register — the plugin exposes its API via Python
        # imports, not via FastAPI routes or hooks.
        pass
