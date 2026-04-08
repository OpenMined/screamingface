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

from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition


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
