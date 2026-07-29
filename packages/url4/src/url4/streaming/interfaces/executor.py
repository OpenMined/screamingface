from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from url4.streaming.protocol import (
    CostUsageData,
    LogData,
    ResultData,
    SpanData,
)

Telemetry = LogData | SpanData | CostUsageData


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    root_span_id: str


@dataclass(frozen=True)
class SpanRef:
    span_id: str
    parent_span_id: str | None


@dataclass(frozen=True)
class Traced:
    payload: Telemetry
    span: SpanRef | None


@dataclass(frozen=True)
class Completed:
    result: ResultData
    subtree_cost: CostUsageData


ExecStep = Telemetry | Traced | Completed


class Executor(ABC):
    @abstractmethod
    def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]: ...
