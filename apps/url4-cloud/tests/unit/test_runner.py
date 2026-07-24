"""OME-520 — the Runner Job entrypoint: lifecycle publication + failure terminal + env parsing."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from _fakes import MockExecutor
from url4.core.errors import ResolutionError

from url4_cloud_nats import InMemoryBus
from url4_cloud_runner import Completed, ExecStep, TraceContext, run
from url4_cloud_runner.__main__ import RunnerConfigError, build_executor, params_from_env
from url4_cloud_runner.url4_executor import Url4Executor
from url4_streaming_protocol import (
    CostUsageData,
    CostUsageEvent,
    LogData,
    OutboundFrame,
    ResultData,
    SpanData,
    TerminatedEvent,
    TokenUsage,
)
from url4_streaming_protocol.taxonomy import CostBreakdown

TOPIC = "cap-topic"
EXPR = "(@)!'hi'"

_LIFECYCLE = [
    "ai.url4.started",
    "ai.url4.log",
    "ai.url4.span",
    "ai.url4.cost.usage",
    "ai.url4.cost.usage",
    "ai.url4.result",
    "ai.url4.terminated",
]


class RecordingBus:
    """A ``Bus`` double that captures published events *before* the wire codec re-sequences them."""

    def __init__(self) -> None:
        self.published: list[OutboundFrame] = []
        self.ensured: list[str] = []

    async def ensure_stream(self, topic: str) -> None:
        self.ensured.append(topic)

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        self.published.append(event)

    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        for event in self.published:
            yield event

    async def purge(self, topic: str) -> None:
        self.published.clear()


class _RaisingExecutor:
    """Yields one log, then raises — drives the failure terminal path."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body="starting")
        raise self._exc


class _NoCompletionExecutor:
    """Streams telemetry but never yields a terminal ``Completed`` — a malformed executor."""

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body="only-telemetry")


class _FakeUrl4Error(Exception):
    """Duck-types url4 ``Url4Error`` — carries ``code`` + ``permanent`` without importing url4."""

    def __init__(self, message: str, *, code: str, permanent: bool) -> None:
        super().__init__(message)
        self.code = code
        self.permanent = permanent


async def _take(bus: InMemoryBus, topic: str, n: int) -> list[OutboundFrame]:
    out: list[OutboundFrame] = []

    async def _run() -> None:
        async for event in bus.subscribe(topic, from_sequence=1):
            out.append(event)
            if len(out) >= n:
                break

    await asyncio.wait_for(_run(), timeout=2.0)
    return out


@pytest.mark.asyncio
async def test_success_publishes_full_lifecycle_in_order() -> None:
    bus = RecordingBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    assert [e.type for e in bus.published] == _LIFECYCLE
    assert bus.ensured == [TOPIC]


@pytest.mark.asyncio
async def test_success_sets_monotonic_sequence_and_envelope() -> None:
    bus = RecordingBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    seqs = [int(e.sequence) for e in bus.published if e.sequence is not None]
    assert len(seqs) == len(bus.published)
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    for event in bus.published:
        assert event.id and len(event.id) == 32  # uuid4().hex
        assert event.source == f"/trace/{TOPIC}/node/root"
        assert event.subject == TOPIC
        assert event.time is not None
        assert event.sequencetype == "Integer"


@pytest.mark.asyncio
async def test_subtree_cost_precedes_result_and_self_cost_streamed() -> None:
    bus = RecordingBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    types = [e.type for e in bus.published]
    result_idx = types.index("ai.url4.result")
    before_result = bus.published[result_idx - 1]
    assert isinstance(before_result, CostUsageEvent)
    assert before_result.data.scope == "subtree"

    first_cost = bus.published[types.index("ai.url4.cost.usage")]
    assert isinstance(first_cost, CostUsageEvent)
    assert first_cost.data.scope == "self"

    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "succeeded"
    assert term.data.error is None


@pytest.mark.asyncio
async def test_failure_terminates_with_mapped_error() -> None:
    bus = RecordingBus()
    exc = _FakeUrl4Error("boom", code="resolution_failed", permanent=False)
    await run(bus, _RaisingExecutor(exc), TOPIC, EXPR)

    assert [e.type for e in bus.published] == [
        "ai.url4.started",
        "ai.url4.log",
        "ai.url4.terminated",
    ]
    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None
    assert term.data.error.code == "resolution_failed"
    assert term.data.error.permanent is False
    assert "boom" in term.data.error.message


@pytest.mark.asyncio
async def test_failure_generic_exception_defaults_to_internal_permanent() -> None:
    bus = RecordingBus()
    await run(bus, _RaisingExecutor(ValueError("nope")), TOPIC, EXPR)

    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None
    assert term.data.error.code == "internal_error"
    assert term.data.error.permanent is True
    assert "nope" in term.data.error.message


@pytest.mark.asyncio
async def test_executor_without_completed_terminates_failed() -> None:
    bus = RecordingBus()
    await run(bus, _NoCompletionExecutor(), TOPIC, EXPR)

    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None


@pytest.mark.asyncio
async def test_lifecycle_round_trips_through_in_memory_bus() -> None:
    bus = InMemoryBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    got = await _take(bus, TOPIC, len(_LIFECYCLE))
    assert [int(e.sequence) for e in got if e.sequence is not None] == [1, 2, 3, 4, 5, 6, 7]
    assert [e.type for e in got] == _LIFECYCLE
    last = got[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "succeeded"


@pytest.mark.asyncio
async def test_custom_executor_streams_are_wrapped_with_envelopes() -> None:
    # WHY: a hand-built executor (not the mock) proves the port is the real seam.
    class _OneSpanExecutor:
        async def execute(
            self, url4: str, *, trace: TraceContext | None = None
        ) -> AsyncIterator[ExecStep]:
            yield SpanData(name="chat", operation="chat", start=datetime.now(UTC))
            yield Completed(
                result=ResultData(body="ok"),
                subtree_cost=CostUsageData(
                    scope="self",  # deliberately wrong — run() must force "subtree"
                    provider="anthropic",
                    model="claude-opus-4-8",
                    pricing_version="2026-07-01",
                    usage=TokenUsage(),
                    cost=CostBreakdown(total_usd=Decimal("0")),
                ),
            )

    bus = RecordingBus()
    await run(bus, _OneSpanExecutor(), TOPIC, EXPR)

    types = [e.type for e in bus.published]
    assert types == [
        "ai.url4.started",
        "ai.url4.span",
        "ai.url4.cost.usage",
        "ai.url4.result",
        "ai.url4.terminated",
    ]
    subtree = bus.published[types.index("ai.url4.result") - 1]
    assert isinstance(subtree, CostUsageEvent)
    # INVARIANT: the pre-result roll-up is always scope="subtree", regardless of executor input.
    assert subtree.data.scope == "subtree"


def test_params_from_env_reads_topic_expr_and_nats() -> None:
    params = params_from_env(
        {
            "URL4_CLOUD_TOPIC": "cap",
            "URL4_CLOUD_EXPRESSION": EXPR,
            "URL4_CLOUD_NATS_URL": "nats://node:4222",
        }
    )
    assert params.topic == "cap"
    assert params.url4 == EXPR
    assert params.nats_url == "nats://node:4222"


def test_params_from_env_defaults_nats_url() -> None:
    params = params_from_env({"URL4_CLOUD_TOPIC": "cap", "URL4_CLOUD_EXPRESSION": EXPR})
    assert params.nats_url == "nats://localhost:4222"


def test_params_from_env_missing_required_raises() -> None:
    with pytest.raises(RunnerConfigError):
        params_from_env({"URL4_CLOUD_EXPRESSION": EXPR})


# --- build_executor: prod (k8s/docker) aigateway world selection (plan §5.3, dec:A) --------------
#
# ``build_executor`` builds ``AigatewayConfig`` from env alone (no ``models=`` override), so
# fetching the catalog would otherwise mean a real ``GET /v1/models`` call. To keep this test
# headless, ``build_executor`` accepts an optional, test-only ``client=`` — forwarded verbatim to
# ``build_aigateway_world`` (which already supports client injection) — so a test can hand it an
# ``httpx.MockTransport``-backed client instead of adding an env-only ``models=`` escape hatch that
# production ``build_executor`` would never plumb through anyway.

_MODEL = "claude-haiku-4-5"  # AigatewayConfig's own default_model


def _stub_aigateway_client() -> httpx.AsyncClient:
    def _handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": _MODEL}]})
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello from aigateway"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    return httpx.AsyncClient(
        transport=httpx.MockTransport(_handle), base_url="http://aigateway.test"
    )


@pytest.mark.asyncio
async def test_build_executor_with_token_returns_executor_over_the_aigateway_world() -> None:
    async with _stub_aigateway_client() as client:
        executor = await build_executor({"AIGATEWAY_TOKEN": "tok"}, client=client)

        assert isinstance(executor, Url4Executor)
        frames = [f async for f in executor.execute(f"/{_MODEL}(ctx)!go")]

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.result.body == "hello from aigateway"


@pytest.mark.asyncio
async def test_build_executor_without_token_is_deny_by_default() -> None:
    executor = await build_executor({})

    assert isinstance(executor, Url4Executor)
    with pytest.raises(ResolutionError):
        async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
            pass


# --- build_executor: Tavily / web-tools env wiring (spec 2026-07-23, dec:W4/W5) -----------------
#
# `TAVILY_API_KEY` in the Runner env flows through build_executor -> build_aigateway_world
# (tavily_api_key=) so the connector declares web_search/web_fetch to the model. Without it,
# web tools stay off (deny-by-default) even when the aigateway token is present. Proven by
# inspecting the aigateway request BODY (tools declared ⇔ web_tools_enabled), not a private
# attribute — the executor exposes no world handle.


def _recording_aigateway_client() -> tuple[httpx.AsyncClient, list[dict]]:
    """A stub aigateway that records every /v1/chat/completions request body and returns a
    plain-content completion (no tool_calls), so the loop completes in one round-trip and
    Tavily is never consulted."""
    posts: list[dict] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": _MODEL}]})
        assert request.url.path == "/v1/chat/completions"
        posts.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1}}
        )

    return (
        httpx.AsyncClient(transport=httpx.MockTransport(_handle), base_url="http://aigateway.test"),
        posts,
    )


def _unused_tavily_client() -> httpx.AsyncClient:
    # Never called (the stub aigateway returns content on round 1) — but injected so
    # build_executor does NOT create + leak an owned real Tavily client in the test process.
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
        base_url="https://api.tavily.com",
    )


@pytest.mark.asyncio
async def test_build_executor_with_tavily_key_declares_web_tools() -> None:
    client, posts = _recording_aigateway_client()
    async with client, _unused_tavily_client() as tclient:
        executor = await build_executor(
            {"AIGATEWAY_TOKEN": "tok", "TAVILY_API_KEY": "tvly-x"},
            client=client,
            tavily_client=tclient,
        )
        async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
            pass

    assert posts, "the aigateway completion endpoint was never called"
    body = posts[0]
    assert {t["function"]["name"] for t in body["tools"]} == {"web_search", "web_fetch"}
    assert body["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_build_executor_without_tavily_key_declares_no_tools() -> None:
    client, posts = _recording_aigateway_client()
    async with client:
        executor = await build_executor({"AIGATEWAY_TOKEN": "tok"}, client=client)
        async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
            pass

    assert "tools" not in posts[0]
    assert "tool_choice" not in posts[0]
