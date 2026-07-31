"""The served model reaches the wire, end to end.

FEATURE: `gen_ai.response.model` on a span must name the model that ACTUALLY served the call.
The gateway echoes it; before this it was dropped and the field repeated the requested model,
so a provider silently resolving an alias to a different snapshot looked identical to it
serving exactly what was asked for.

Covers both halves of the seam: the connector reporting it, and the executor putting it on the
span frame.
"""

from __future__ import annotations

import json

import httpx
import pytest

from url4.dag import run as url4_run
from url4.observe import NodeFinished, NodeStarted, ObservationEvent, RunStarted, Usage
from url4_cloud.runner.config import ModelSpec
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world
from url4_cloud.runner.executor import _RunState


class _Recorder:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


def _gateway(response_body: dict) -> httpx.AsyncClient:
    def _handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"object": "list", "data": [{"id": "google/gemini-3.1-pro-preview"}]}
            )
        return httpx.Response(200, json=response_body)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(_handle), base_url="http://aigateway.test"
    )


def _body(*, model: str | None) -> dict:
    body: dict = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    if model is not None:
        body["model"] = model
    return body


async def _run_and_get_usage(response_body: dict) -> Usage:
    cfg = AigatewayConfig(
        models=(ModelSpec(id="google/gemini-3.1-pro-preview"),),
        default_model="google/gemini-3.1-pro-preview",
    )
    rec = _Recorder()
    async with _gateway(response_body) as client:
        world = await build_aigateway_world(cfg, client=client)
        await url4_run("/google/gemini-3.1-pro-preview(ctx)!go", io=world.node, observer=rec)
    usages = [e for e in rec.events if isinstance(e, Usage)]
    assert len(usages) == 1
    return usages[0]


# --- the connector half ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_gateways_resolved_model_is_reported_not_the_requested_one() -> None:
    usage = await _run_and_get_usage(_body(model="google/gemini-3.1-pro-preview-20260715"))

    assert usage.model == "google/gemini-3.1-pro-preview"
    assert usage.response_model == "google/gemini-3.1-pro-preview-20260715"


@pytest.mark.asyncio
async def test_a_gateway_that_omits_the_model_yields_none() -> None:
    usage = await _run_and_get_usage(_body(model=None))

    assert usage.model == "google/gemini-3.1-pro-preview"
    assert usage.response_model is None


@pytest.mark.asyncio
async def test_a_non_string_model_is_refused_rather_than_reaching_the_wire_schema() -> None:
    """It comes off an upstream JSON body, so its type is not ours to assume."""
    usage = await _run_and_get_usage(_body(model=None) | {"model": {"nested": "object"}})

    assert usage.response_model is None


# --- the executor half ----------------------------------------------------------


def _span_frames(events: list[ObservationEvent]) -> list:
    state = _RunState()
    frames: list = []
    for event in events:
        frames.extend(state.map(event))
    return frames


def _span_data(response_model: str | None):
    events: list[ObservationEvent] = [
        RunStarted(trace_id="t" * 32, root_span_id="s" * 16, expression_hash="h"),
        NodeStarted(span_id="s" * 16, parent_span_id=None, node_kind="ModelNode", detail="d"),
        Usage(
            span_id="s" * 16,
            provider="google",
            model="gemini-3.1-pro-preview",
            input_tokens=3,
            output_tokens=2,
            response_model=response_model,
        ),
        NodeFinished(span_id="s" * 16, status="ok", engine_seq=2),
    ]
    frames = _span_frames(events)
    spans = [f.payload for f in frames if hasattr(f.payload, "request_model")]
    assert len(spans) == 1
    return spans[0]


def test_the_span_carries_the_served_model_distinctly_from_the_requested_one() -> None:
    span = _span_data("gemini-3.1-pro-preview-20260715")

    assert span.request_model == "gemini-3.1-pro-preview"
    assert span.response_model == "gemini-3.1-pro-preview-20260715"


def test_an_unreported_served_model_leaves_the_span_field_absent() -> None:
    """INVARIANT: absent, NOT a copy of request_model — that copy was the bug."""
    span = _span_data(None)

    assert span.request_model == "gemini-3.1-pro-preview"
    assert span.response_model is None


def test_the_wire_alias_serializes_the_served_model() -> None:
    span = _span_data("gemini-3.1-pro-preview-20260715")

    dumped = json.loads(span.model_dump_json(by_alias=True, exclude_none=True))
    assert dumped["gen_ai.request.model"] == "gemini-3.1-pro-preview"
    assert dumped["gen_ai.response.model"] == "gemini-3.1-pro-preview-20260715"
