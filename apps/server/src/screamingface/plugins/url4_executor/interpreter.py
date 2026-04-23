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
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced

        with traced("url4.evaluate"):
            set_span_attrs(
                {
                    "url4.expression": expr[:500],
                }
            )

            source_expr, raw_intent, _broadcast = split_intent(expr.strip())
            set_span_attrs({"url4.has_intent": raw_intent is not None})

            # Resolve sources (parallel fetch of URLs, concatenate text)
            with traced("url4.resolve_sources"):
                sources = await resolve_str(source_expr, self.app) if source_expr else ""
                src_preview = sources[:4000]
                if len(sources) > 4000:
                    src_preview += f"\n... ({len(sources) - 4000} more chars)"
                set_span_attrs(
                    {
                        "url4.sources_length": len(sources),
                        "url4.response_body": src_preview,
                    }
                )

            # Resolve intent (text / relative URL / absolute URL)
            with traced("url4.resolve_intent"):
                intent = await resolve_intent(raw_intent, self.app) if raw_intent else None
                set_span_attrs(
                    {
                        "url4.intent_length": len(intent) if intent else 0,
                        "url4.response_body": intent[:4000] if intent else "",
                    }
                )

            result = await self.process(sources, intent)
            result_preview = result[:4000]
            if len(result) > 4000:
                result_preview += f"\n... ({len(result) - 4000} more chars)"
            set_span_attrs(
                {
                    "url4.result_length": len(result),
                    "url4.response_body": result_preview,
                }
            )
            return result

    async def process(self, sources: str, intent: str | None) -> str:
        """Process resolved sources and intent. Override in subclasses.

        Default: concatenate intent + sources.
        """
        if intent and sources:
            return f"{intent}\n\n{sources}"
        return intent or sources or ""
