import json
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from _fakes import MockExecutor, take

from url4.core.errors import ResolutionError
from url4.streaming.interfaces import (
    Completed,
    EventStream,
    ExecStep,
    Executor,
    TraceContext,
)
from url4.streaming.lifecycle import run
from url4.streaming.protocol import (
    CostUsageData,
    CostUsageEvent,
    LogData,
    OutboundFrame,
    ResultData,
    SpanData,
    TerminatedEvent,
    TokenUsage,
)
from url4.streaming.protocol.taxonomy import CostBreakdown
from url4_cloud import job_env
from url4_cloud.runner.config import AigatewaySection, CommandSpec, ModelSpec, RunnerConfig
from url4_cloud.runner.executor import Url4Executor
from url4_cloud.runner.main import RunnerConfigError, build_executor, params_from_env
from url4_cloud.testing import InMemoryEventStream

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


class RecordingEventStream(EventStream):
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


class _RaisingExecutor(Executor):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body="starting")
        raise self._exc


class _NoCompletionExecutor(Executor):
    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body="only-telemetry")


class _FakeUrl4Error(Exception):
    def __init__(self, message: str, *, code: str, permanent: bool) -> None:
        super().__init__(message)
        self.code = code
        self.permanent = permanent


@pytest.mark.asyncio
async def test_success_publishes_full_lifecycle_in_order() -> None:
    stream = RecordingEventStream()
    await run(stream, MockExecutor(), TOPIC, EXPR)

    assert [e.type for e in stream.published] == _LIFECYCLE
    assert stream.ensured == [TOPIC]


@pytest.mark.asyncio
async def test_success_sets_monotonic_sequence_and_envelope() -> None:
    stream = RecordingEventStream()
    await run(stream, MockExecutor(), TOPIC, EXPR)

    seqs = [int(e.sequence) for e in stream.published if e.sequence is not None]
    assert len(seqs) == len(stream.published)
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    for event in stream.published:
        assert event.id and len(event.id) == 32
        assert event.source == f"/trace/{TOPIC}/node/root"
        assert event.subject == TOPIC
        assert event.time is not None
        assert event.sequencetype == "Integer"


@pytest.mark.asyncio
async def test_subtree_cost_precedes_result_and_self_cost_streamed() -> None:
    stream = RecordingEventStream()
    await run(stream, MockExecutor(), TOPIC, EXPR)

    types = [e.type for e in stream.published]
    result_idx = types.index("ai.url4.result")
    before_result = stream.published[result_idx - 1]
    assert isinstance(before_result, CostUsageEvent)
    assert before_result.data.scope == "subtree"

    first_cost = stream.published[types.index("ai.url4.cost.usage")]
    assert isinstance(first_cost, CostUsageEvent)
    assert first_cost.data.scope == "self"

    term = stream.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "succeeded"
    assert term.data.error is None


@pytest.mark.asyncio
async def test_failure_terminates_with_mapped_error() -> None:
    stream = RecordingEventStream()
    exc = _FakeUrl4Error("boom", code="resolution_failed", permanent=False)
    await run(stream, _RaisingExecutor(exc), TOPIC, EXPR)

    assert [e.type for e in stream.published] == [
        "ai.url4.started",
        "ai.url4.log",
        "ai.url4.terminated",
    ]
    term = stream.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None
    assert term.data.error.code == "resolution_failed"
    assert term.data.error.permanent is False
    assert "boom" in term.data.error.message


@pytest.mark.asyncio
async def test_failure_generic_exception_defaults_to_internal_permanent() -> None:
    stream = RecordingEventStream()
    await run(stream, _RaisingExecutor(ValueError("nope")), TOPIC, EXPR)

    term = stream.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None
    assert term.data.error.code == "internal_error"
    assert term.data.error.permanent is True
    assert "nope" in term.data.error.message


@pytest.mark.asyncio
async def test_executor_without_completed_terminates_failed() -> None:
    stream = RecordingEventStream()
    await run(stream, _NoCompletionExecutor(), TOPIC, EXPR)

    term = stream.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None


@pytest.mark.asyncio
async def test_lifecycle_round_trips_through_in_memory_bus() -> None:
    stream = InMemoryEventStream()
    await run(stream, MockExecutor(), TOPIC, EXPR)

    got = await take(stream, TOPIC, len(_LIFECYCLE), from_sequence=1)
    assert [int(e.sequence) for e in got if e.sequence is not None] == [1, 2, 3, 4, 5, 6, 7]
    assert [e.type for e in got] == _LIFECYCLE
    last = got[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "succeeded"


@pytest.mark.asyncio
async def test_custom_executor_streams_are_wrapped_with_envelopes() -> None:
    class _OneSpanExecutor(Executor):
        async def execute(
            self, url4: str, *, trace: TraceContext | None = None
        ) -> AsyncIterator[ExecStep]:
            yield SpanData(name="chat", operation="chat", start=datetime.now(UTC))
            yield Completed(
                result=ResultData(body="ok"),
                subtree_cost=CostUsageData(
                    scope="self",
                    provider="anthropic",
                    model="claude-opus-4-8",
                    pricing_version="2026-07-01",
                    usage=TokenUsage(),
                    cost=CostBreakdown(total_usd=Decimal("0")),
                ),
            )

    stream = RecordingEventStream()
    await run(stream, _OneSpanExecutor(), TOPIC, EXPR)

    types = [e.type for e in stream.published]
    assert types == [
        "ai.url4.started",
        "ai.url4.span",
        "ai.url4.cost.usage",
        "ai.url4.result",
        "ai.url4.terminated",
    ]
    subtree = stream.published[types.index("ai.url4.result") - 1]
    assert isinstance(subtree, CostUsageEvent)
    assert subtree.data.scope == "subtree"


def test_params_from_env_reads_topic_expr_and_nats() -> None:
    params = params_from_env(
        {
            job_env.TOPIC: "cap",
            job_env.EXPRESSION: EXPR,
            job_env.NATS_URL: "nats://node:4222",
        }
    )
    assert params.topic == "cap"
    assert params.url4 == EXPR
    assert params.nats_url == "nats://node:4222"


def test_params_from_env_defaults_nats_url() -> None:
    params = params_from_env({job_env.TOPIC: "cap", job_env.EXPRESSION: EXPR})
    assert params.nats_url == "nats://localhost:4222"


def test_params_from_env_missing_required_raises() -> None:
    with pytest.raises(RunnerConfigError):
        params_from_env({job_env.EXPRESSION: EXPR})


_MODEL = "claude-haiku-4-5"


def _declared(*models: str, web_tools: bool = False) -> RunnerConfig:
    """A config declaring `models`, defaulting to the first — the Runner never discovers.

    `web_tools` is the per-route opt-in every declared route here shares; it defaults off,
    matching the shipped default, so a test that wants the tool loop must ask for it.
    """
    declared = models or (_MODEL,)
    return RunnerConfig(
        aigateway=AigatewaySection(
            base_url="http://aigateway.test",
            default_model=declared[0],
            models=tuple(ModelSpec(id=model, web_tools=web_tools) for model in declared),
        )
    )


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
async def test_build_executor_returns_an_executor_over_the_aigateway_world() -> None:
    async with _stub_aigateway_client() as client:
        executor = build_executor({}, _declared(), client=client)

        assert isinstance(executor, Url4Executor)
        frames = [f async for f in executor.execute(f"/{_MODEL}(ctx)!go")]

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.result.body == "hello from aigateway"


@pytest.mark.asyncio
async def test_a_config_with_no_aigateway_table_is_deny_by_default() -> None:
    executor = build_executor({}, RunnerConfig())

    assert isinstance(executor, Url4Executor)
    with pytest.raises(ResolutionError):
        async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
            pass


@pytest.mark.asyncio
async def test_build_executor_runs_a_declared_command_only_world() -> None:
    config = RunnerConfig(
        commands=(
            CommandSpec(
                "/benchmark",
                (
                    sys.executable,
                    "-c",
                    "import sys;print('benchmark:' + sys.stdin.read())",
                ),
            ),
        )
    )
    executor = build_executor({}, config)

    frames = [frame async for frame in executor.execute("/benchmark('case-1')!'load'")]

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.result.body.strip() == "benchmark:case-1"


# INVARIANT: a declared gateway world runs with NO credential of any kind. aigateway is in
# `cloudflare_headers` mode when deployed (it reads the identity header) and `disabled` locally
# (every caller is anonymous) — neither reads `Authorization`, and a deployed caller has no way to
# obtain a token. Demanding one here previously failed every deployed run before its first request.
@pytest.mark.asyncio
async def test_a_declared_gateway_runs_without_any_credential() -> None:
    client, posts = _recording_aigateway_client()
    executor = build_executor({}, _declared(), client=client)

    async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
        pass

    assert posts, "the run must reach aigateway rather than failing on a missing token"


def _recording_aigateway_client() -> tuple[httpx.AsyncClient, list[dict]]:
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
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
        base_url="https://api.tavily.com",
    )


@pytest.mark.asyncio
async def test_build_executor_with_tavily_key_declares_web_tools() -> None:
    client, posts = _recording_aigateway_client()
    async with client, _unused_tavily_client() as tclient:
        executor = build_executor(
            {job_env.TAVILY_API_KEY: "tvly-x"},
            _declared(web_tools=True),
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
async def test_build_executor_declares_no_tools_for_a_route_that_did_not_opt_in() -> None:
    # A Tavily key is configured, but url4.toml declared this route without `web_tools` — the
    # deployment secret must not decide what the model is asked.
    client, posts = _recording_aigateway_client()
    async with client, _unused_tavily_client() as tclient:
        executor = build_executor(
            {job_env.TAVILY_API_KEY: "tvly-x"},
            _declared(web_tools=False),
            client=client,
            tavily_client=tclient,
        )
        async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
            pass

    assert posts, "the aigateway completion endpoint was never called"
    assert "tools" not in posts[0]
    assert "tool_choice" not in posts[0]


@pytest.mark.asyncio
async def test_build_executor_without_tavily_key_declares_no_tools() -> None:
    client, posts = _recording_aigateway_client()
    async with client:
        executor = build_executor({}, _declared(), client=client)
        async for _ in executor.execute(f"/{_MODEL}(ctx)!go"):
            pass

    assert "tools" not in posts[0]
    assert "tool_choice" not in posts[0]
