"""``NatsBus.subscribe`` must create the per-topic stream, like ``InMemoryBus`` does.

INVARIANT: the two ``Bus`` implementations are interchangeable. ``InMemoryBus.subscribe`` calls
``ensure_stream`` (memory.py); ``NatsBus.subscribe`` did not, and that divergence was invisible to
the whole headless suite because every other test injects the in-memory bus.

STORY: as a client I open the WebSocket BEFORE starting a run — the REST `428` interest gate
requires it. The JetStream stream, though, is only created when the *Runner* first publishes. So
the required order guarantees the subscriber arrives while no stream exists: `js.subscribe(...,
stream=...)` raises `NotFoundError`, the bridge's subscription task dies, and the client receives
heartbeats forever and never a single run frame. Observed on a live kind cluster — the Runner Job
completed and NATS held 6 frames that never reached the socket.
"""

from typing import Any, cast

import pytest
from nats.js import JetStreamContext

from url4_cloud_nats import NatsBus


class _FakeSub:
    """A JetStream subscription that yields nothing — the call ORDER is what's under test."""

    @property
    def messages(self) -> Any:
        async def _empty() -> Any:
            return
            yield  # pragma: no cover - never reached; makes this an async generator

        return _empty()


class _FakeJetStream:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def add_stream(self, name: str, subjects: list[str]) -> object:
        self.calls.append("add_stream")
        return object()

    async def subscribe(self, subject: str, **kwargs: Any) -> _FakeSub:
        self.calls.append("subscribe")
        return _FakeSub()


@pytest.mark.anyio
async def test_subscribe_ensures_the_stream_before_binding_to_it() -> None:
    bus = NatsBus("nats://unused:4222")
    js = _FakeJetStream()
    # Inject the JetStream context — no live NATS in the headless suite (INFRA rule). `cast`
    # because the fake implements only the two calls this behaviour depends on.
    bus._js = cast(JetStreamContext, js)

    async for _ in bus.subscribe("topic-a"):  # pragma: no branch - drains an empty stream
        pass

    # INVARIANT: ensure BEFORE bind — reversing these is exactly the production failure.
    assert js.calls == ["add_stream", "subscribe"]
