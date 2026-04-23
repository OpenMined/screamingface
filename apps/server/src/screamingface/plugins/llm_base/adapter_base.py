"""Adapter ABC — converts CoreMessage lists to/from a specific provider's wire format.

An :class:`Adapter` is the shape-conversion layer between our neutral
:class:`CoreMessage` list and a specific provider's expected request /
response bodies. This is the classic Gang-of-Four Adapter pattern: "one
interface, many wire shapes behind it."

Each provider plugin implements one concrete :class:`Adapter` subclass
that knows how to serialize a :class:`CoreMessage` list into that
provider's request body and how to parse the provider's response back
into a :class:`CoreMessage`.

Adapters should be **stateless** — just a shape transformation, no
cache, no state. :class:`Backend` instances hold the auth strategy and
httpx client; adapters hold nothing.

See the plan's Phase 2 section for the hand-rolled-vs-dependency
decision. Phase 1 uses exactly one concrete adapter
(``AnthropicAdapter`` in ``claude_backend_api``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from screamingface.plugins.llm_base.messages import CoreMessage, TextPart, ToolDefinition


def extract_system_text(system: str | list | None) -> str | None:
    """Normalize a ``system`` argument to a plain string or ``None``.

    Adapters all accept ``system`` as either a bare string (the simple
    case most callers use) or a list of content blocks (Anthropic's
    structured shape, when a billing header or similar needs to be
    appended as its own block). This helper turns either form into the
    flat concatenation every adapter ultimately wants when building
    provider-specific request bodies.

    Returns ``None`` for ``None`` / empty inputs.
    """
    if system is None:
        return None
    if isinstance(system, str):
        return system or None
    # list form: concatenate every .text on TextPart-like dicts
    chunks: list[str] = []
    for block in system:
        if isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                chunks.append(text)
        elif isinstance(block, TextPart):
            chunks.append(block.text)
        elif isinstance(block, str):
            chunks.append(block)
    joined = "\n\n".join(chunks).strip()
    return joined or None


def collect_provider_metadata(source: dict, keys: tuple[str, ...], *, prefix: str) -> dict:
    """Pull the listed ``keys`` from ``source`` into a provider-prefixed dict.

    Used by adapters to propagate vendor-specific response fields
    (usage counts, stop reasons, response IDs, …) onto the returned
    :class:`CoreMessage`'s ``provider_metadata``. Keys not present in
    ``source`` are skipped. The returned dict has ``f"{prefix}.{key}"``
    entries so consumers can disambiguate across providers.
    """
    out: dict = {}
    for key in keys:
        if key in source:
            out[f"{prefix}.{key}"] = source[key]
    return out


class Adapter(ABC):
    """Abstract contract for provider wire-format adapters."""

    @abstractmethod
    def to_provider_format(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 16000,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Build the provider-specific request body.

        The returned dict is passed directly to httpx as the JSON body
        of the outbound POST. It must conform to the target provider's
        Messages/Chat API schema.

        Raises:
            AdapterError: The input contains a construct the target
                provider cannot represent (e.g. an orphaned tool_use
                with no matching tool_result that would produce a
                schema-invalid Anthropic request body).
        """

    @abstractmethod
    def from_provider_response(self, data: dict[str, Any]) -> CoreMessage:
        """Parse the provider's HTTP response body into a CoreMessage.

        The response is always assumed to be a successful 200 OK body —
        error handling happens before this is called.

        Raises:
            AdapterError: The response shape is unexpected (missing
                required fields, unknown block types, etc.).
        """
