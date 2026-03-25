"""Pydantic models for the Anthropic Messages API (request, response, streaming)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["text"] = "text"
    text: str


class ImageSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["base64"] = "base64"
    media_type: str
    data: str


class ImageBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["image"] = "image"
    source: ImageSource


class ToolUseBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[TextBlock | ImageBlock]
    is_error: bool | None = None


ContentBlock = Annotated[
    TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class InputSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["object"] = "object"
    properties: dict[str, Any] | None = None
    required: list[str] | None = None


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: str | None = None
    input_schema: InputSchema


class ToolChoiceAuto(BaseModel):
    type: Literal["auto"] = "auto"


class ToolChoiceAny(BaseModel):
    type: Literal["any"] = "any"


class ToolChoiceTool(BaseModel):
    type: Literal["tool"] = "tool"
    name: str


ToolChoice = ToolChoiceAuto | ToolChoiceAny | ToolChoiceTool


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class MessageMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    user_id: str | None = None


class MessagesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    max_tokens: int | None = None
    messages: list[Message]
    system: str | list[TextBlock] | None = None
    stream: bool | None = None
    metadata: MessageMetadata | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: ToolChoice | None = None


# ---------------------------------------------------------------------------
# Response (non-streaming)
# ---------------------------------------------------------------------------


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")
    input_tokens: int
    output_tokens: int


class MessagesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock]
    model: str
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: Usage


# ---------------------------------------------------------------------------
# Streaming events (for future use — proxy forwards SSE bytes as-is)
# ---------------------------------------------------------------------------


class StreamMessageStart(BaseModel):
    type: Literal["message_start"] = "message_start"
    message: MessagesResponse


class ContentBlockStart(BaseModel):
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ContentBlock


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class InputJsonDelta(BaseModel):
    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str


class ContentBlockDelta(BaseModel):
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: TextDelta | InputJsonDelta


class ContentBlockStop(BaseModel):
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaBody(BaseModel):
    stop_reason: str | None = None
    stop_sequence: str | None = None


class MessageDeltaUsage(BaseModel):
    output_tokens: int


class StreamMessageDelta(BaseModel):
    type: Literal["message_delta"] = "message_delta"
    delta: MessageDeltaBody
    usage: MessageDeltaUsage


class StreamMessageStop(BaseModel):
    type: Literal["message_stop"] = "message_stop"


# ---------------------------------------------------------------------------
# System-prompt injection helper
# ---------------------------------------------------------------------------


def prepend_system_context(request: MessagesRequest, context: str) -> None:
    """Prepend url4-resolved context to the system prompt (mutates in place)."""
    if not context:
        return
    if request.system is None:
        request.system = context
    elif isinstance(request.system, str):
        request.system = context + "\n\n" + request.system
    elif isinstance(request.system, list):
        request.system.insert(0, TextBlock(text=context + "\n\n"))
