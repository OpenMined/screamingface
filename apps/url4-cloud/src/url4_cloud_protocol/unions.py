"""Discriminated unions over the frame ``type`` (spec §7)."""

from typing import Annotated

from pydantic import Field, TypeAdapter

from url4_cloud_protocol.signals import (
    Attach,
    CostUsage,
    Execute,
    Heartbeat,
    Log,
    Result,
    Span,
    Started,
    Stop,
    Terminated,
)

OutboundFrame = Annotated[
    Started | Log | Span | CostUsage | Heartbeat | Result | Terminated,
    Field(discriminator="type"),
]
InboundFrame = Annotated[Execute | Stop | Attach, Field(discriminator="type")]
Frame = Annotated[
    Started | Log | Span | CostUsage | Heartbeat | Result | Terminated | Execute | Stop | Attach,
    Field(discriminator="type"),
]

OutboundFrameAdapter = TypeAdapter(OutboundFrame)
InboundFrameAdapter = TypeAdapter(InboundFrame)
FrameAdapter = TypeAdapter(Frame)
