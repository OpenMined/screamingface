from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, NamedTuple

import pytest
from _pytest.mark import ParameterSet

from url4.streaming.interfaces import (
    Completed,
    EventConsumer,
    ExecStep,
    Executor,
    JobAlreadyExists,
    JobRunner,
    JobStatus,
    TraceContext,
    job_name,
)
from url4.streaming.protocol import (
    CostUsageData,
    LogData,
    ResultData,
    SpanData,
    TokenUsage,
)
from url4.streaming.protocol.taxonomy import CostBreakdown
from url4.streaming.testing import TAKE_TIMEOUT_S, take
from url4_cloud.adapters.jetstream import JetStreamConsumer
from url4_cloud.testing import InMemoryEventStream

STREAM_FACTORIES: list[Callable[[], EventConsumer] | ParameterSet] = [
    pytest.param(InMemoryEventStream, id="InMemoryEventStream"),
    pytest.param(
        lambda: JetStreamConsumer("nats://localhost:4222"),
        id="JetStreamConsumer",
        marks=pytest.mark.skip(reason="owner-run: needs real NATS (INFRA rule)"),
    ),
]


class ScheduledRun(NamedTuple):
    topic: str
    url4: str
    deadline_s: int
    traceparent: str | None
    credential: str | None
    profile: str | None


class RecordingJobRunner(JobRunner):
    def __init__(self, *, exists: bool = False, conflict_on_schedule: bool = False) -> None:
        self._exists = exists
        self._conflict = conflict_on_schedule
        self.scheduled: list[ScheduledRun] = []
        self.stopped: list[str] = []

    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str:
        if self._conflict:
            raise JobAlreadyExists(topic)
        self.scheduled.append(
            ScheduledRun(topic, url4, deadline_s, traceparent, credential, profile)
        )
        return job_name(topic)

    def stop(self, topic: str) -> None:
        self.stopped.append(topic)

    def exists(self, topic: str) -> bool:
        return self._exists

    def status(self, topic: str) -> JobStatus:
        return "running"


class FixedGate:
    def __init__(self, present: bool = True) -> None:
        self._present = present

    async def has_subscriber(self, topic: str) -> bool:
        return self._present


class MockExecutor(Executor):
    def _cost(self, scope: Literal["self", "subtree"]) -> CostUsageData:
        return CostUsageData(
            scope=scope,
            provider="anthropic",
            model="claude-opus-4-8",
            pricing_version="2026-07-01",
            usage=TokenUsage(input_tokens=1200, output_tokens=340),
            cost=CostBreakdown(
                input_usd=Decimal("0.0180"),
                output_usd=Decimal("0.0255"),
                total_usd=Decimal("0.0435"),
            ),
        )

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body=f"executing {url4}")
        yield SpanData(
            name="chat",
            operation="chat",
            provider="anthropic",
            request_model="claude-opus-4-8",
            response_model="claude-opus-4-8",
            input_tokens=1200,
            output_tokens=340,
            start=datetime.now(UTC),
            end=datetime.now(UTC),
        )
        yield self._cost("self")
        yield Completed(
            result=ResultData(body="[mock] done", media_type="text/plain"),
            subtree_cost=self._cost("subtree"),
        )


__all__ = [
    "STREAM_FACTORIES",
    "TAKE_TIMEOUT_S",
    "FixedGate",
    "MockExecutor",
    "RecordingJobRunner",
    "ScheduledRun",
    "take",
]
