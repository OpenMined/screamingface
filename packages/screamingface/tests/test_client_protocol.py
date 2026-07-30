"""Confirmed SF Engine transport contract against a controlled protocol server."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import closing
from typing import Any, cast

import pytest
from protocol_server import protocol_server

import screamingface as sf
from screamingface._evaluation import Candidate, _candidate_from_engine, _operation_from_engine
from screamingface._ports import _RunOutcome
from screamingface._transport import AsyncUrl4CloudTransport, Url4CloudTransport


def _candidate() -> Candidate:
    return _candidate_from_engine(
        name="opus",
        kind="model",
        models=("provider/opus",),
        url4="(@)!'hello'",
        operations=(
            _operation_from_engine(
                id="op_opus",
                kind="model",
                label="opus answer",
                depends_on=(),
            ),
        ),
    )


def _run(
    engine_url: str,
    on_event: Callable[[sf.Event], None] | None = None,
) -> _RunOutcome:
    with closing(Url4CloudTransport(engine_url)) as transport:
        return transport.run(_candidate(), on_event)


async def _arun(
    engine_url: str,
    on_event: Callable[[sf.Event], None | Awaitable[None]] | None = None,
) -> _RunOutcome:
    transport = AsyncUrl4CloudTransport(engine_url)
    try:
        return await transport.run(_candidate(), on_event)
    finally:
        await transport.close()


def test_transport_attaches_before_start_and_returns_the_root_outcome() -> None:
    with protocol_server() as engine:
        outcome = _run(engine.url)

    assert outcome.result_body == "[test] done"
    assert engine.state.inbound_events[0]["type"] == "ai.url4.attach"
    assert engine.state.inbound_events[0]["data"] == {"from_sequence": None}


@pytest.mark.asyncio
async def test_async_transport_has_the_same_attach_and_result_boundary() -> None:
    with protocol_server() as engine:
        outcome = await _arun(engine.url)

    assert outcome.result_body == "[test] done"
    assert engine.state.inbound_events[0]["type"] == "ai.url4.attach"
    assert engine.state.inbound_events[0]["data"] == {"from_sequence": None}


def test_callback_failure_stops_the_attached_run_and_reraises() -> None:
    original = RuntimeError("progress renderer failed")

    def fail(event: sf.Event) -> None:
        raise original

    with protocol_server(mode="stop") as engine:
        with pytest.raises(RuntimeError) as caught:
            _run(engine.url, fail)

    assert caught.value is original
    assert [event["type"] for event in engine.state.inbound_events] == [
        "ai.url4.attach",
        "ai.url4.stop",
    ]


def test_keyboard_interrupt_stops_the_attached_run_and_reraises() -> None:
    def interrupt(event: sf.Event) -> None:
        raise KeyboardInterrupt

    with protocol_server(mode="stop") as engine:
        with pytest.raises(KeyboardInterrupt):
            _run(engine.url, interrupt)

    assert [event["type"] for event in engine.state.inbound_events] == [
        "ai.url4.attach",
        "ai.url4.stop",
    ]


@pytest.mark.asyncio
async def test_async_callback_failure_has_the_same_stop_behavior() -> None:
    original = RuntimeError("async progress renderer failed")

    async def fail(event: sf.Event) -> None:
        raise original

    with protocol_server(mode="stop") as engine:
        with pytest.raises(RuntimeError) as caught:
            await _arun(engine.url, fail)

    assert caught.value is original
    assert [event["type"] for event in engine.state.inbound_events] == [
        "ai.url4.attach",
        "ai.url4.stop",
    ]


@pytest.mark.asyncio
async def test_async_cancellation_stops_the_attached_run_and_reraises() -> None:
    async def cancel(event: sf.Event) -> None:
        raise asyncio.CancelledError

    with protocol_server(mode="stop") as engine:
        with pytest.raises(asyncio.CancelledError):
            await _arun(engine.url, cancel)

    assert [event["type"] for event in engine.state.inbound_events] == [
        "ai.url4.attach",
        "ai.url4.stop",
    ]


def test_sequence_gap_reattaches_from_the_first_missing_event() -> None:
    with protocol_server(mode="gap") as engine:
        _run(engine.url)

    assert [event["data"] for event in engine.state.inbound_events] == [
        {"from_sequence": None},
        {"from_sequence": 2},
    ]


@pytest.mark.asyncio
async def test_async_sequence_gap_reattaches_from_the_first_missing_event() -> None:
    with protocol_server(mode="gap") as engine:
        await _arun(engine.url)

    assert [event["data"] for event in engine.state.inbound_events] == [
        {"from_sequence": None},
        {"from_sequence": 2},
    ]


def test_disconnect_before_terminal_state_is_an_execution_error() -> None:
    with protocol_server(mode="disconnect") as engine:
        with pytest.raises(sf.ExecutionError, match="disconnected") as caught:
            _run(engine.url)

    assert caught.value.code == "websocket_disconnected"
    assert caught.value.permanent is False


@pytest.mark.asyncio
async def test_async_disconnect_before_terminal_state_is_an_execution_error() -> None:
    with protocol_server(mode="disconnect") as engine:
        with pytest.raises(sf.ExecutionError, match="disconnected") as caught:
            await _arun(engine.url)

    assert caught.value.code == "websocket_disconnected"
    assert caught.value.permanent is False


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("token_invalid_json", "must be JSON"),
        ("token_malformed", "is malformed"),
    ],
)
def test_transport_rejects_malformed_capability_responses(
    mode: str,
    message: str,
) -> None:
    with protocol_server(mode=cast(Any, mode)) as engine:
        with pytest.raises(sf.ExecutionError, match=message):
            _run(engine.url)


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("missing_preference", "acknowledge asynchronous"),
        ("missing_location", "missing Location"),
    ],
)
def test_transport_rejects_incomplete_async_start_responses(
    mode: str,
    message: str,
) -> None:
    with protocol_server(mode=cast(Any, mode)) as engine:
        with pytest.raises(sf.ExecutionError, match=message):
            _run(engine.url)


def test_start_problem_is_preserved_as_an_execution_error() -> None:
    with protocol_server(mode="start_error") as engine:
        with pytest.raises(sf.ExecutionError, match="test runner is unavailable") as caught:
            _run(engine.url)

    assert caught.value.code == "runner_unavailable"
    assert caught.value.status == 502
    assert caught.value.permanent is False
    assert caught.value.details == {
        "type": "runner_unavailable",
        "title": "Runner unavailable",
        "status": 502,
        "detail": "The test runner is unavailable.",
    }


def test_authentication_problem_preserves_structured_diagnostics() -> None:
    with protocol_server(mode="start_auth_error") as engine:
        with pytest.raises(sf.AuthenticationError) as caught:
            _run(engine.url)

    assert str(caught.value) == ("Could not start the Run: The execution capability expired.")
    assert caught.value.code == "capability_expired"
    assert caught.value.status == 401
    assert caught.value.permanent is True
    assert caught.value.details == {
        "type": "capability_expired",
        "title": "Capability expired",
        "status": 401,
        "detail": "The execution capability expired.",
    }


def test_transport_observer_receives_public_events_in_order() -> None:
    seen: list[sf.Event] = []
    with protocol_server() as engine:
        _run(engine.url, seen.append)

    assert [event.kind for event in seen] == ["started", "usage", "terminated"]


@pytest.mark.asyncio
async def test_async_callback_is_awaited_in_event_order() -> None:
    seen: list[str] = []

    async def observe(event: sf.Event) -> None:
        seen.append(event.kind)

    with protocol_server() as engine:
        await _arun(engine.url, observe)

    assert seen == ["started", "usage", "terminated"]


def test_heartbeat_is_consumed_as_internal_liveness() -> None:
    seen: list[str] = []
    with protocol_server(mode="heartbeat") as engine:
        _run(engine.url, lambda event: seen.append(event.kind))

    assert seen == ["started", "usage", "terminated"]


@pytest.mark.parametrize("error", [OSError("observer failed"), TimeoutError("observer timed out")])
def test_transport_preserves_disconnect_shaped_callback_exceptions(
    error: BaseException,
) -> None:
    def fail(event: sf.Event) -> None:
        raise error

    with protocol_server(mode="stop") as engine:
        with pytest.raises(type(error)) as caught:
            _run(engine.url, fail)

    assert caught.value is error


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [OSError("observer failed"), TimeoutError("observer timed out")])
async def test_async_transport_preserves_disconnect_shaped_callback_exceptions(
    error: BaseException,
) -> None:
    async def fail(event: sf.Event) -> None:
        raise error

    with protocol_server(mode="stop") as engine:
        with pytest.raises(type(error)) as caught:
            await _arun(engine.url, fail)

    assert caught.value is error
