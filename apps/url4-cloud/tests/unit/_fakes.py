"""Test-only executor doubles (not shipped, not a production adapter).

``MockExecutor`` is a §8-valid fake :class:`~url4_cloud_runner.executor.Executor` — one log, one
GenAI span, ``CostUsage{self}``, then ``Completed`` — used by the Runner / ``InProcessJobRunner``
tests to drive :func:`url4_cloud_runner.publish.run` without importing ``url4`` or standing up a
real engine. Every REAL execution path builds ``Url4Executor`` instead (k8s/docker pods via
``url4_cloud_runner.__main__.build_executor``, local mode via ``url4_cloud.app.make_local_app``).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

from url4_cloud_runner import Completed, ExecStep, TraceContext
from url4_streaming_protocol import (
    CostUsageData,
    LogData,
    ResultData,
    SpanData,
    TokenUsage,
)
from url4_streaming_protocol.taxonomy import CostBreakdown


class MockExecutor:
    """§8-valid fake — a single-node subtree, so ``subtree == self`` (spec §8: root
    ``subtree.total == Σ all self``). Yields BARE ``Telemetry`` (never ``Traced``) since it carries
    no real engine span identity; ``publish.run`` tolerates both."""

    def _cost(self, scope: str) -> CostUsageData:
        # WHY: input_usd + output_usd == total_usd — the CostBreakdown validator enforces it.
        return CostUsageData(
            scope="subtree" if scope == "subtree" else "self",
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
        # `trace` is accepted for Protocol conformance and ignored — this fake never carries real
        # engine span identity, so it always yields BARE Telemetry (no Traced wrapping); publish.run
        # tolerates both.
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
