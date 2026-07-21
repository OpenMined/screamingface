"""CloudEvent message types (discriminated on ``type``) + unions (docs/protocol.md §4)."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from url4_cloud_protocol.envelope import CloudEvent
from url4_cloud_protocol.signals import (
    AttachData,
    CostUsageData,
    ExecuteData,
    HeartbeatData,
    LogData,
    ResultData,
    SpanData,
    StartedData,
    StopData,
    TerminatedData,
)


# ---- outbound events (engine/tool -> app -> client) ----
class StartedEvent(CloudEvent):
    type: Literal["ai.url4.started"] = "ai.url4.started"
    data: StartedData


class LogEvent(CloudEvent):
    type: Literal["ai.url4.log"] = "ai.url4.log"
    data: LogData


class SpanEvent(CloudEvent):
    type: Literal["ai.url4.span"] = "ai.url4.span"
    data: SpanData


class CostUsageEvent(CloudEvent):
    type: Literal["ai.url4.cost.usage"] = "ai.url4.cost.usage"
    data: CostUsageData


class HeartbeatEvent(CloudEvent):
    type: Literal["ai.url4.heartbeat"] = "ai.url4.heartbeat"
    data: HeartbeatData = Field(default_factory=HeartbeatData)


class ResultEvent(CloudEvent):
    type: Literal["ai.url4.result"] = "ai.url4.result"
    data: ResultData


class TerminatedEvent(CloudEvent):
    type: Literal["ai.url4.terminated"] = "ai.url4.terminated"
    data: TerminatedData


# ---- inbound commands (client -> app -> engine/tool) ----
class ExecuteEvent(CloudEvent):
    type: Literal["ai.url4.execute"] = "ai.url4.execute"
    data: ExecuteData


class StopEvent(CloudEvent):
    type: Literal["ai.url4.stop"] = "ai.url4.stop"
    data: StopData


class AttachEvent(CloudEvent):
    type: Literal["ai.url4.attach"] = "ai.url4.attach"
    data: AttachData


OutboundFrame = Annotated[
    StartedEvent
    | LogEvent
    | SpanEvent
    | CostUsageEvent
    | HeartbeatEvent
    | ResultEvent
    | TerminatedEvent,
    Field(discriminator="type"),
]
InboundFrame = Annotated[ExecuteEvent | StopEvent | AttachEvent, Field(discriminator="type")]
Frame = Annotated[
    StartedEvent
    | LogEvent
    | SpanEvent
    | CostUsageEvent
    | HeartbeatEvent
    | ResultEvent
    | TerminatedEvent
    | ExecuteEvent
    | StopEvent
    | AttachEvent,
    Field(discriminator="type"),
]

OutboundFrameAdapter = TypeAdapter(OutboundFrame)
InboundFrameAdapter = TypeAdapter(InboundFrame)
FrameAdapter = TypeAdapter(Frame)
