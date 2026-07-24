"""traceparent / W3C span tree end-to-end (trace PRD §7): real-engine-driven
:mod:`~url4_cloud_runner.publish` runs, through
:class:`~url4_cloud_runner.url4_executor.Url4Executor`, must produce the same wire shape
:mod:`~url4_cloud.testing.mock_runner` already fakes.

Every test drives the real url4 engine (:class:`~url4.io.static.StaticIOLayer`, no network) — no
mocking of ``publish.run`` or ``Url4Executor`` themselves.
"""

import asyncio
import re
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from url4.io.static import StaticIOLayer

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobStatus, job_name
from url4_cloud.testing.mock_runner import build_run
from url4_cloud_nats import InMemoryBus
from url4_cloud_runner.publish import run as publish_run
from url4_cloud_runner.url4_executor import Url4Executor
from url4_streaming_protocol import (
    OutboundFrame,
    ResultEvent,
    SpanEvent,
    StartedEvent,
    TerminatedEvent,
)

_TP_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-01$")

SECRET = "traceparent-unit-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


async def _collect(bus: InMemoryBus, topic: str) -> list[OutboundFrame]:
    """Every frame published on ``topic``, from the start through the terminal frame."""
    frames: list[OutboundFrame] = []

    async def _run() -> None:
        async for frame in bus.subscribe(topic, from_sequence=1):
            frames.append(frame)
            if isinstance(frame, TerminatedEvent):
                return

    await asyncio.wait_for(_run(), timeout=2.0)
    return frames


def _edge_shape(spans: list[SpanEvent]) -> list[str | None]:
    """A literal-id-independent fingerprint of a span tree's edges: ``None`` for the (unique)
    tracestate-less root, ``"root"`` for a span whose ``tracestate`` names the root, sorted so two
    structurally-identical trees compare equal regardless of their actual span ids."""
    root = next(f for f in spans if f.tracestate is None)
    root_span_id = _TP_RE.match(root.traceparent).group(2)  # type: ignore[union-attr]
    shape: list[str | None] = []
    for f in spans:
        if f.tracestate is None:
            shape.append(None)
        else:
            parent_id = f.tracestate.removeprefix("url4.parent=")
            shape.append("root" if parent_id == root_span_id else parent_id)
    return sorted(shape, key=lambda x: (x is not None, x))


# --- 1. every published frame's traceparent is well-formed, and the run shares ONE trace_id ----


@pytest.mark.asyncio
async def test_every_frame_traceparent_matches_w3c_and_shares_one_trace_id() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    bus = InMemoryBus()
    topic = "trace-topic-1"

    await publish_run(bus, Url4Executor(io), topic, "https://a!go")
    frames = await _collect(bus, topic)

    trace_ids = set()
    for frame in frames:
        match = _TP_RE.match(frame.traceparent)  # type: ignore[arg-type]
        assert match is not None, frame
        trace_ids.add(match.group(1))
    assert len(trace_ids) == 1


# --- 2. non-top span tracestate names its parent; top span + all non-span frames are None -------


@pytest.mark.asyncio
async def test_span_tracestate_and_non_span_tracestate_none() -> None:
    io = StaticIOLayer(fetch_map={"https://x": "X", "https://y": "Y"})
    bus = InMemoryBus()
    topic = "trace-topic-2"

    await publish_run(bus, Url4Executor(io), topic, "(https://x, https://y)!go")
    frames = await _collect(bus, topic)

    span_frames = [f for f in frames if isinstance(f, SpanEvent)]
    non_span_frames = [f for f in frames if not isinstance(f, SpanEvent)]
    assert non_span_frames
    for frame in non_span_frames:
        assert frame.tracestate is None

    roots = [f for f in span_frames if f.tracestate is None]
    assert len(roots) == 1
    root_span_id = _TP_RE.match(roots[0].traceparent).group(2)  # type: ignore[union-attr]

    children = [f for f in span_frames if f is not roots[0]]
    assert len(children) == 2
    for child in children:
        assert child.tracestate == f"url4.parent={root_span_id}"


# --- 3. a fan-out's span EDGE structure matches mock_runner's root ← {leaf-0, leaf-1} ------------


@pytest.mark.asyncio
async def test_fanout_span_edge_set_matches_mock_runner_shape() -> None:
    io = StaticIOLayer(fetch_map={"https://x": "X", "https://y": "Y"})
    bus = InMemoryBus()
    topic = "trace-topic-3"

    await publish_run(bus, Url4Executor(io), topic, "(https://x, https://y)!go")
    frames = await _collect(bus, topic)
    real_spans = [f for f in frames if isinstance(f, SpanEvent)]
    assert len(real_spans) == 3

    mock_frames = build_run("mock-topic", "(gpt,claude)!'demo'")
    mock_spans = [f for f in mock_frames if isinstance(f, SpanEvent)]

    assert _edge_shape(real_spans) == _edge_shape(mock_spans) == [None, "root", "root"]


# --- 4. a malformed inbound traceparent mints a fresh trace (never propagates garbage) -----------


@pytest.mark.asyncio
async def test_malformed_inbound_traceparent_mints_a_fresh_trace() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    bus = InMemoryBus()
    topic = "trace-topic-4"

    await publish_run(bus, Url4Executor(io), topic, "https://a!go", traceparent="garbage")
    frames = await _collect(bus, topic)

    trace_ids = set()
    for frame in frames:
        match = _TP_RE.match(frame.traceparent)  # type: ignore[arg-type]
        assert match is not None
        trace_ids.add(match.group(1))
    assert len(trace_ids) == 1
    assert next(iter(trace_ids)) != "garbage"


# --- 4b. an all-zero (W3C-invalid) inbound traceparent is rejected, not propagated ---------------


@pytest.mark.asyncio
async def test_all_zero_inbound_traceparent_mints_a_fresh_trace() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    bus = InMemoryBus()
    topic = "trace-topic-4b"
    all_zero = f"00-{'0' * 32}-{'b' * 16}-01"  # W3C-invalid all-zero trace-id

    await publish_run(bus, Url4Executor(io), topic, "https://a!go", traceparent=all_zero)
    frames = await _collect(bus, topic)

    trace_ids = set()
    for frame in frames:
        match = _TP_RE.match(frame.traceparent)  # type: ignore[arg-type]
        assert match is not None
        trace_ids.add(match.group(1))
    assert len(trace_ids) == 1
    # the null-sentinel trace-id must NOT have been adopted
    assert next(iter(trace_ids)) != "0" * 32


# --- 5. routes.py: a valid inbound header forwards; absent/malformed schedules with None ---------


class _FakeJobRunner:
    """A headless ``JobRunner`` that only records the ``traceparent`` kwarg it was scheduled
    with."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str, int, str | None]] = []

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
        self.scheduled.append((topic, url4, deadline_s, traceparent))
        return job_name(topic)

    def stop(self, topic: str) -> None:
        raise NotImplementedError

    def exists(self, topic: str) -> bool:
        return False

    def status(self, topic: str) -> JobStatus:
        return "running"


class _FakeGate:
    async def has_subscriber(self, topic: str) -> bool:
        return True


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _app(job_runner: _FakeJobRunner) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S)
    return create_app(
        settings, bus=InMemoryBus(), job_runner=job_runner, clock=lambda: T0, interest=_FakeGate()
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_routes_valid_inbound_traceparent_forwards_into_schedule() -> None:
    topic = "trace-topic-5-valid"
    runner = _FakeJobRunner()
    app = _app(runner)
    valid_tp = f"00-{'a' * 32}-{'b' * 16}-01"

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "traceparent": valid_tp,
            },
        )
    assert resp.status_code == 202
    assert runner.scheduled == [(topic, "gpt(hi)", app.state.settings.job_deadline_s, valid_tp)]


@pytest.mark.asyncio
async def test_routes_absent_traceparent_schedules_with_none() -> None:
    topic = "trace-topic-5-absent"
    runner = _FakeJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={"URL4-Capability": _token(topic), "Prefer": "respond-async"},
        )
    assert resp.status_code == 202
    assert runner.scheduled[0][3] is None


@pytest.mark.asyncio
async def test_routes_malformed_traceparent_schedules_with_none() -> None:
    topic = "trace-topic-5-malformed"
    runner = _FakeJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "traceparent": "garbage",
            },
        )
    assert resp.status_code == 202
    assert runner.scheduled[0][3] is None


# --- 6. non-span lifecycle frames carry the root traceparent, tracestate None --------------------


@pytest.mark.asyncio
async def test_non_span_lifecycle_frames_carry_root_traceparent() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    bus = InMemoryBus()
    topic = "trace-topic-6"

    await publish_run(bus, Url4Executor(io), topic, "https://a!go")
    frames = await _collect(bus, topic)

    started = next(f for f in frames if isinstance(f, StartedEvent))
    result = next(f for f in frames if isinstance(f, ResultEvent))
    terminated = next(f for f in frames if isinstance(f, TerminatedEvent))

    assert started.traceparent == result.traceparent == terminated.traceparent
    assert _TP_RE.match(started.traceparent)  # type: ignore[arg-type]
    assert started.tracestate is None
    assert result.tracestate is None
    assert terminated.tracestate is None
