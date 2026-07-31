"""``Usage.response_model`` — the model that actually served a call.

FEATURE: OpenTelemetry's GenAI semconv separates ``gen_ai.request.model`` (asked for) from
``gen_ai.response.model`` (served it). A gateway may resolve an alias to a dated snapshot, so a
consumer must be able to tell the two apart.

STORY: as someone auditing a published benchmark score, I can see which model actually answered,
not merely which one was requested — otherwise provider-side drift is invisible.
"""

from __future__ import annotations

import pytest

from url4.dag import run
from url4.io.static import StaticIOLayer
from url4.observe import ObservationEvent, Usage


class _Recorder:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


class _ResolvedModelNode:
    """Reports a response model that DIFFERS from the requested one — the alias case."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        ctx.report_usage(
            provider="google",
            model="gemini-3.1-pro-preview",
            input_tokens=10,
            output_tokens=5,
            response_model="gemini-3.1-pro-preview-20260715",
        )
        return "ok"


class _SilentProviderNode:
    """Reports no response model — a provider that does not echo one."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        ctx.report_usage(provider="anthropic", model="claude-x", input_tokens=1, output_tokens=1)
        return "ok"


def _usage(events: list[ObservationEvent]) -> Usage:
    usages = [e for e in events if isinstance(e, Usage)]
    assert len(usages) == 1
    return usages[0]


@pytest.mark.asyncio
async def test_the_served_model_is_carried_separately_from_the_requested_one() -> None:
    rec = _Recorder()

    await run(_ResolvedModelNode(), StaticIOLayer(), observer=rec)

    usage = _usage(rec.events)
    assert usage.model == "gemini-3.1-pro-preview"
    assert usage.response_model == "gemini-3.1-pro-preview-20260715"


@pytest.mark.asyncio
async def test_an_unreported_response_model_stays_none_rather_than_echoing_the_request() -> None:
    """INVARIANT: the whole point of the field. Defaulting it to the requested model would make
    "the provider served what we asked for" and "the provider never said" identical."""
    rec = _Recorder()

    await run(_SilentProviderNode(), StaticIOLayer(), observer=rec)

    usage = _usage(rec.events)
    assert usage.model == "claude-x"
    assert usage.response_model is None
