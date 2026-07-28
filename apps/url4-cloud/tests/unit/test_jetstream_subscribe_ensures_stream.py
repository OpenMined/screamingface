from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from nats.js import JetStreamContext

from url4.streaming.codec import encode
from url4.streaming.protocol import LogData, LogEvent, OutboundFrame, source_for
from url4_cloud.adapters.jetstream import JetStreamConsumer


class _FakeMsg:
    """One delivered message, shaped like the `nats-py` message the adapter decodes."""

    def __init__(self, n: int) -> None:
        self.data = encode(
            LogEvent(
                id=f"e{n}",
                source=source_for("topic-a", "root"),
                subject="topic-a",
                data=LogData.at("INFO", f"msg-{n}"),
            )
        )
        self.metadata = SimpleNamespace(sequence=SimpleNamespace(stream=n + 1))


class _FakeSub:
    def __init__(self, count: int = 0) -> None:
        self.unsubscribed = False
        self._count = count

    @property
    def messages(self) -> Any:
        async def _msgs() -> Any:
            for n in range(self._count):
                yield _FakeMsg(n)

        return _msgs()

    async def unsubscribe(self) -> None:
        self.unsubscribed = True


class _FakeJetStream:
    def __init__(self, messages_per_sub: int = 0) -> None:
        self.calls: list[str] = []
        self.subs: list[_FakeSub] = []
        self._messages_per_sub = messages_per_sub

    async def add_stream(self, name: str, subjects: list[str]) -> object:
        self.calls.append("add_stream")
        return object()

    async def subscribe(self, subject: str, **kwargs: Any) -> _FakeSub:
        self.calls.append("subscribe")
        sub = _FakeSub(self._messages_per_sub)
        self.subs.append(sub)
        return sub


@pytest.mark.anyio
async def test_subscribe_ensures_the_stream_before_binding_to_it() -> None:
    stream = JetStreamConsumer("nats://unused:4222")
    js = _FakeJetStream()
    stream._js = cast(JetStreamContext, js)

    async for _ in stream.subscribe("topic-a"):  # pragma: no branch - drains an empty stream
        pass

    assert js.calls == ["add_stream", "subscribe"]


@pytest.mark.anyio
async def test_abandoning_the_iterator_releases_the_subscription() -> None:
    """INVARIANT: a re-attach cancels the WS pump and a sync GET gives up at `sync_max_wait_s`,
    both mid-iteration. Leaving the push consumer bound would keep delivering into a queue
    nobody drains, once per attach, for the life of the NATS connection."""
    stream = JetStreamConsumer("nats://unused:4222")
    js = _FakeJetStream(messages_per_sub=3)
    stream._js = cast(JetStreamContext, js)

    # `subscribe` is typed as the AsyncIterator the port promises; the concrete object is the
    # async generator, and closing it is what abandoning an `async for` does.
    frames = cast(AsyncGenerator[OutboundFrame], stream.subscribe("topic-a"))
    await anext(frames)  # bind, then walk away mid-stream
    await frames.aclose()

    assert js.subs[0].unsubscribed is True
