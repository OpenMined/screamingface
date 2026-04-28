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


def serialize_tool_output(output: object) -> str:
    """Stringify a :class:`ToolResultPart.output` for providers that expect a string.

    String outputs are passed through unchanged; everything else is
    JSON-encoded. Used by claude (Anthropic ``tool_result.content``)
    and codex (OpenAI Responses ``function_call_output.output``).
    """
    import json as _json

    if isinstance(output, str):
        return output
    return _json.dumps(output)


def parts_to_text(parts: object, *, separator: str = "") -> str:
    """Concatenate every ``TextPart.text`` in *parts*, dropping non-text parts.

    Used by adapters when converting a ``CoreMessage.content`` list to
    a flat string for providers that don't accept content-block arrays
    (e.g. Codex's user content shorthand).
    """
    if not parts:
        return ""
    chunks: list[str] = []
    for part in parts:  # type: ignore[union-attr]
        if isinstance(part, TextPart):
            chunks.append(part.text)
    return separator.join(chunks)


def collect_provider_metadata(
    source: dict,
    keys: tuple[str, ...],
    *,
    prefix: str,
    skip_none: bool = False,
) -> dict:
    """Pull the listed ``keys`` from ``source`` into a provider-prefixed dict.

    Used by adapters to propagate vendor-specific response fields
    (usage counts, stop reasons, response IDs, …) onto the returned
    :class:`CoreMessage`'s ``provider_metadata``. Keys not present in
    ``source`` are skipped. The returned dict has ``f"{prefix}.{key}"``
    entries so consumers can disambiguate across providers.

    Pass ``skip_none=True`` to also drop keys whose value is ``None``
    (Ollama's response carries explicit ``None`` for fields that
    weren't filled in for that response shape).
    """
    out: dict = {}
    for key in keys:
        if key not in source:
            continue
        value = source[key]
        if skip_none and value is None:
            continue
        out[f"{prefix}.{key}"] = value
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
