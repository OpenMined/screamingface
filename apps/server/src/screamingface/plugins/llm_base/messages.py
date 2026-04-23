"""Provider-agnostic message shape — the CoreMessage type.

The design is ported from the Vercel AI SDK ``CoreMessage`` schema
(https://ai-sdk.dev/docs/foundations/prompts). It is the single
neutral shape every :class:`~screamingface.plugins.llm_base.Adapter`
converts to/from.

Why this shape and not Anthropic Messages or OpenAI Chat directly:

- **Anthropic Messages** is the highest-fidelity native shape but it's
  vendor-coupled. Choosing it as canonical implies "Anthropic is the
  home shape, everyone else is an exception."
- **OpenAI Chat** is the lowest common denominator and loses
  Anthropic-side detail (cache_control, citations, structured
  tool_result content lists, parallel tool calls with IDs).
- **Vercel-AI-SDK-style parts** are the only field-proven neutral shape
  that round-trips Anthropic content blocks faithfully *and* is easy to
  translate to OpenAI Chat / Gemini ``Content[]``.

The ``provider_metadata`` escape hatch on each message and each part is
the standard pattern for "carry vendor-specific extras through the
canonical type without breaking other consumers." Adapters are free
to inspect and honor provider_metadata but must never depend on its
presence.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------------
# Content parts — each part is a discriminated-union member via its ``type``
# ----------------------------------------------------------------------------


class _PartBase(BaseModel):
    """Common base for every content part."""

    model_config = ConfigDict(extra="forbid")

    provider_metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Vendor-specific extras that should survive translation but "
            "don't map to any neutral field. Examples: cache_control, "
            "citations, image media_type hints."
        ),
    )


class TextPart(_PartBase):
    """Plain text content."""

    type: Literal["text"] = "text"
    text: str


class ImagePart(_PartBase):
    """Image content — URL-based or base64-encoded.

    Exactly one of ``image_url`` or ``image_b64`` must be set.
    """

    type: Literal["image"] = "image"
    image_url: str | None = None
    image_b64: str | None = None
    media_type: str | None = None


class ToolCallPart(_PartBase):
    """Model's request to invoke a tool.

    Lives in an ``assistant`` message. The ``tool_call_id`` links this
    call to a later :class:`ToolResultPart` in a user/tool message.
    """

    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultPart(_PartBase):
    """Result of a prior tool call, fed back to the model.

    Lives in a ``user`` or ``tool`` message. ``tool_call_id`` must match
    a prior :class:`ToolCallPart`.
    """

    type: Literal["tool-result"] = "tool-result"
    tool_call_id: str
    tool_name: str
    output: dict[str, Any] | str
    is_error: bool = False


class ReasoningPart(_PartBase):
    """Model reasoning / extended thinking.

    Some providers (Anthropic) produce signed thinking blocks that must
    be preserved across turns. The ``signature`` field carries that
    provider-specific signature; translators that don't need it ignore
    it.
    """

    type: Literal["reasoning"] = "reasoning"
    text: str
    signature: str | None = None


# The union of every part type. Discriminated on the ``type`` field.
ContentPart = TextPart | ImagePart | ToolCallPart | ToolResultPart | ReasoningPart


# ----------------------------------------------------------------------------
# Message
# ----------------------------------------------------------------------------


class CoreMessage(BaseModel):
    """A single turn in a conversation.

    Content is either a bare string (shorthand for a single TextPart) or
    a list of typed parts. Adapters should handle both forms.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart]
    provider_metadata: dict[str, Any] | None = None


# ----------------------------------------------------------------------------
# Tool definition — what a backend advertises it can call
# ----------------------------------------------------------------------------


def extract_text(msg: CoreMessage) -> str:
    """Return the concatenation of every :class:`TextPart` in ``msg.content``.

    Short-circuits on the bare-string content shorthand. Parts that are
    not TextPart (image, tool-call, tool-result, reasoning) are skipped —
    callers who need those should walk ``msg.content`` directly.
    """
    if isinstance(msg.content, str):
        return msg.content
    return "".join(p.text for p in msg.content if isinstance(p, TextPart))


class ToolDefinition(BaseModel):
    """Schema describing a tool the model may call.

    Maps directly to both Anthropic's ``tools`` field and OpenAI's
    ``tools`` field (modulo a parameters/input_schema rename that
    translators handle).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description=(
            "JSON Schema describing the tool's input. Anthropic calls "
            "this ``input_schema``; OpenAI calls it ``parameters``."
        ),
    )
