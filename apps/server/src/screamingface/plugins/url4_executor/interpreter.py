"""Base url4 interpreter — parse, resolve sources, resolve intent, process.

Subclass and override ``process()`` in each backend plugin to control
what happens with the resolved sources and intent. The default
implementation concatenates them (used by the ``/ensemble`` endpoint).
"""

from __future__ import annotations

import logging
from typing import Any

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.url4 import (
    _fetch_relative,
    _fetch_url,
    resolve_str,
)

logger = logging.getLogger(__name__)


async def resolve_intent(intent: str, app: Any = None) -> str:
    """Resolve an intent string to text.

    - ``/path`` → relative URL, fetched via in-process ASGI
    - ``http://`` or ``https://`` → absolute URL, fetched via httpx
    - anything else → text literal (surrounding quotes stripped)
    """
    intent = intent.strip()
    if intent.startswith("/"):
        if not app:
            raise ValueError("Relative URL intent requires app for in-process fetch")
        return await _fetch_relative(app, intent)
    if intent.startswith(("http://", "https://")):
        return await _fetch_url(intent)
    return intent.strip("'\"")


class Url4Interpreter:
    """Base url4 interpreter.

    Pipeline: split intent → resolve sources (parallel) → resolve intent → process.

    Override ``process()`` to change what happens with the resolved pieces.
    The default concatenates ``intent + "\\n\\n" + sources``.
    """

    def __init__(self, app: Any = None):
        self.app = app

    async def evaluate(self, expr: str) -> str:
        """Full evaluation pipeline."""
        source_expr, raw_intent = split_intent(expr.strip())

        # Resolve sources (parallel fetch of URLs, concatenate text)
        sources = await resolve_str(source_expr, self.app) if source_expr else ""

        # Resolve intent (text / relative URL / absolute URL)
        intent = await resolve_intent(raw_intent, self.app) if raw_intent else None

        return await self.process(sources, intent)

    async def process(self, sources: str, intent: str | None) -> str:
        """Process resolved sources and intent. Override in subclasses.

        Default: concatenate intent + sources.
        """
        if intent and sources:
            return f"{intent}\n\n{sources}"
        return intent or sources or ""
