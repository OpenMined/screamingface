"""The ``Executor`` port — the url4 execution seam the Runner publishes from (spec §1.1, OME-446).

The Runner (:mod:`url4_cloud_runner.publish`) owns the CloudEvents envelope (id / source / sequence
/ time) and the lifecycle framing; the ``Executor`` owns *what happened* — it streams telemetry
payloads "as available", then yields exactly one terminal :class:`Completed` carrying the result and
the subtree cost roll-up. PEP 525 forbids a value-returning async generator, so the outcome rides as
the final yielded item rather than a ``return``.

The real url4-backed adapter is the deferred OME-446 seam; :class:`MockExecutor` is an interim,
§8-valid fake so ``url4-cloud-runner`` runs end-to-end for the compose e2e (OME-524) until it lands.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from url4_cloud_protocol import (
    CostUsageData,
    LogData,
    ResultData,
    SpanData,
    TokenUsage,
)
from url4_cloud_protocol.taxonomy import CostBreakdown

# Telemetry the executor streams "as available" — each wrapped into its CloudEvent by the Runner.
Telemetry = LogData | SpanData | CostUsageData


@dataclass(frozen=True)
class Completed:
    """The terminal outcome of a url4 execution: the result body + the subtree cost roll-up.

    Carrying both together makes the spec §8 ordering invariant ("``CostUsage{subtree}`` emitted
    before ``Result``") true by construction — the Runner emits them back-to-back from this value.
    """

    result: ResultData
    subtree_cost: CostUsageData


# One step of an execution stream: a telemetry payload, or the single terminal ``Completed``.
ExecStep = Telemetry | Completed


class Executor(Protocol):
    """Runs a url4 expression, streaming :data:`Telemetry` then one terminal :class:`Completed`."""

    def execute(self, url4: str) -> AsyncIterator[ExecStep]: ...


class MockExecutor:
    """Interim §8-valid fake — one log, one GenAI span, ``CostUsage{self}``, then ``Completed``.

    A single-node subtree, so ``subtree == self`` (spec §8: root ``subtree.total == Σ all self``).
    Swapped for the real url4 engine channel once OME-446 lands.
    """

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

    async def execute(self, url4: str) -> AsyncIterator[ExecStep]:
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
