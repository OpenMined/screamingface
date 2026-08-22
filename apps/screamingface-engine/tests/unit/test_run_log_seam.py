"""Generic run-scoped structured Log seam (OME-934)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from types import TracebackType
from typing import cast

import pytest

import screamingface_engine.runner.executor as executor_module
from screamingface_engine.runner.executor import BridgeEvent, Url4Executor, _Bridge
from screamingface_engine.runner.run_logs import (
    LogScalar,
    RunLogScopeFactory,
    StructuredLog,
    StructuredLogEmitter,
)
from url4.io.static import StaticIOLayer
from url4.observe import NodeStarted
from url4.streaming.interfaces import Completed, ExecStep, Traced
from url4.streaming.protocol import LogData


async def _drain(
    executor: Url4Executor,
    expression: str = "https://example.test!go",
) -> list[ExecStep]:
    return [frame async for frame in executor.execute(expression)]


def _io() -> StaticIOLayer:
    return StaticIOLayer(fetch_map={"https://example.test": "source"})


def _logs(frames: list[ExecStep]) -> list[LogData]:
    return [
        frame.payload
        for frame in frames
        if isinstance(frame, Traced) and isinstance(frame.payload, LogData)
    ]


class _Scope(AbstractContextManager[None]):
    def __init__(
        self,
        *,
        events: list[str],
        emit: StructuredLogEmitter,
        exit_error: Exception | None = None,
    ) -> None:
        self._events = events
        self._emit = emit
        self._exit_error = exit_error
        self.exit_exception: type[BaseException] | None = None

    def __enter__(self) -> None:
        self._events.append("enter")
        self._emit("scope entered", {"scope.phase": "enter", "scope.count": 1})

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.exit_exception = exc_type
        self._events.append("exit")
        self._emit("scope exited", {"scope.phase": "exit"})
        if self._exit_error is not None:
            raise self._exit_error
        # INVARIANT: an observational scope cannot suppress an execution failure.
        return True


class _Factory(RunLogScopeFactory):
    def __init__(
        self,
        events: list[str],
        *,
        decline: bool = False,
        exit_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.decline = decline
        self.exit_error = exit_error
        self.urls: list[str] = []
        self.emitter: StructuredLogEmitter | None = None
        self.scope: _Scope | None = None

    def open_run_scope(
        self,
        rendered_url4: str,
        emit_structured_log: StructuredLogEmitter,
    ) -> AbstractContextManager[None] | None:
        self.events.append("open")
        self.urls.append(rendered_url4)
        self.emitter = emit_structured_log
        if self.decline:
            return None
        self.scope = _Scope(
            events=self.events,
            emit=emit_structured_log,
            exit_error=self.exit_error,
        )
        return self.scope


@pytest.mark.asyncio
async def test_scope_gets_exact_url4_and_surrounds_only_run_before_bridge_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    expression = "https://example.test/a%20b(context)!intent"

    async def world() -> tuple[StaticIOLayer, None]:
        events.append("world")
        return StaticIOLayer(), None

    async def run(
        rendered_url4: str,
        _io: object,
        **_kwargs: object,
    ) -> str:
        events.append("run")
        assert rendered_url4 is expression
        return "result"

    monkeypatch.setattr(executor_module, "url4_run", run)
    factory = _Factory(events)
    executor = Url4Executor(world_factory=world, run_log_scope_factory=factory)

    frames = await _drain(executor, expression)

    assert events == ["world", "open", "enter", "run", "exit"]
    assert factory.urls == [expression]
    assert [log.body for log in _logs(frames)] == ["scope entered", "scope exited"]
    assert _logs(frames)[0].attributes == {"scope.phase": "enter", "scope.count": 1}
    assert all(log.severity_text == "INFO" for log in _logs(frames))
    assert isinstance(frames[-1], Completed)
    assert frames[-1].result.body == "result"


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [None, _Factory([], decline=True)])
async def test_missing_or_declining_factory_keeps_execution_silent_and_unchanged(
    factory: RunLogScopeFactory | None,
) -> None:
    executor = Url4Executor(_io(), run_log_scope_factory=factory)

    frames = await _drain(executor)

    assert _logs(frames) == []
    assert isinstance(frames[-1], Completed)
    assert frames[-1].result.body == "go\n\nsource"


class _SetupFailureFactory(RunLogScopeFactory):
    def open_run_scope(
        self,
        rendered_url4: str,
        emit_structured_log: StructuredLogEmitter,
    ) -> AbstractContextManager[None] | None:
        del rendered_url4, emit_structured_log
        raise RuntimeError("private prompt must not be logged")


@pytest.mark.asyncio
async def test_factory_setup_failure_is_private_and_cannot_change_the_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    executor = Url4Executor(_io(), run_log_scope_factory=_SetupFailureFactory())

    frames = await _drain(executor)

    assert isinstance(frames[-1], Completed)
    assert frames[-1].result.body == "go\n\nsource"
    assert "run Log scope setup failed (RuntimeError)" in caplog.text
    assert "private prompt" not in caplog.text


class _EntryFailureFactory(RunLogScopeFactory):
    def open_run_scope(
        self,
        rendered_url4: str,
        emit_structured_log: StructuredLogEmitter,
    ) -> AbstractContextManager[None] | None:
        del rendered_url4, emit_structured_log

        class _EntryFailureScope(AbstractContextManager[None]):
            exited = False

            def __enter__(self) -> None:
                raise RuntimeError("private entry payload")

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                self.exited = True

        self.scope = _EntryFailureScope()
        return self.scope


@pytest.mark.asyncio
async def test_scope_entry_failure_does_not_enter_teardown_or_change_execution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    factory = _EntryFailureFactory()
    executor = Url4Executor(_io(), run_log_scope_factory=factory)

    frames = await _drain(executor)

    assert isinstance(frames[-1], Completed)
    assert frames[-1].result.body == "go\n\nsource"
    assert not factory.scope.exited
    assert "run Log scope entry failed (RuntimeError)" in caplog.text
    assert "private entry payload" not in caplog.text


class _ExecutionFailure(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_scope_exit_cannot_suppress_or_replace_the_original_execution_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = _ExecutionFailure("original execution failure")

    async def fail(*_args: object, **_kwargs: object) -> str:
        raise original

    monkeypatch.setattr(executor_module, "url4_run", fail)
    caplog.set_level(logging.WARNING)
    factory = _Factory([], exit_error=RuntimeError("private teardown payload"))
    executor = Url4Executor(_io(), run_log_scope_factory=factory)

    with pytest.raises(_ExecutionFailure) as exc_info:
        await _drain(executor)

    assert exc_info.value is original
    assert factory.scope is not None
    assert factory.scope.exit_exception is _ExecutionFailure
    assert "run Log scope teardown failed (RuntimeError)" in caplog.text
    assert "private teardown payload" not in caplog.text


class _MalformedFactory(RunLogScopeFactory):
    def __init__(self, value: object) -> None:
        self._value = value

    def open_run_scope(
        self,
        rendered_url4: str,
        emit_structured_log: StructuredLogEmitter,
    ) -> AbstractContextManager[None] | None:
        del rendered_url4

        class _MalformedScope(AbstractContextManager[None]):
            def __enter__(self) -> None:
                emit_structured_log("valid", {"valid": True})
                malformed = cast("Mapping[str, LogScalar]", {"invalid": self_value})
                emit_structured_log("must be dropped whole", malformed)

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                return None

        self_value = self._value
        return _MalformedScope()


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [[], {}, {"nested": []}])
async def test_malformed_record_is_dropped_whole_without_coercion_or_execution_failure(
    caplog: pytest.LogCaptureFixture,
    malformed: object,
) -> None:
    caplog.set_level(logging.WARNING)
    executor = Url4Executor(
        _io(),
        run_log_scope_factory=_MalformedFactory(malformed),
    )

    frames = await _drain(executor)

    assert [log.body for log in _logs(frames)] == ["valid"]
    assert "run Log submission rejected" in caplog.text
    assert "array" not in caplog.text
    assert isinstance(frames[-1], Completed)


@pytest.mark.asyncio
async def test_retained_emitter_becomes_inert_and_warns_at_most_once_after_scope_close(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    factory = _Factory([])
    executor = Url4Executor(_io(), run_log_scope_factory=factory)

    await _drain(executor)
    assert factory.emitter is not None
    factory.emitter("late one", {"late": 1})
    factory.emitter("late two", {"late": 2})

    expired = [record for record in caplog.records if "expired emitter" in record.message]
    assert len(expired) == 1
    assert "late one" not in caplog.text
    assert "late two" not in caplog.text


@pytest.mark.asyncio
async def test_bridge_submission_failure_is_fail_open_and_payload_private(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = _Bridge.on_event

    def fail_injected(self: _Bridge, event: BridgeEvent) -> None:
        if isinstance(event, StructuredLog):
            raise RuntimeError("private submitted body")
        original(self, event)

    monkeypatch.setattr(_Bridge, "on_event", fail_injected)
    caplog.set_level(logging.WARNING)
    executor = Url4Executor(_io(), run_log_scope_factory=_Factory([]))

    frames = await _drain(executor)

    assert isinstance(frames[-1], Completed)
    assert _logs(frames) == []
    assert "run Log submission failed (RuntimeError)" in caplog.text
    assert "private submitted body" not in caplog.text


def test_injected_log_has_the_existing_evictable_log_policy() -> None:
    bridge = _Bridge(maxsize=1)
    bridge.on_event(StructuredLog("progress", {"cases.completed": 1}))

    bridge.on_event(NodeStarted("span", None, "TextNode", ""))

    assert bridge.dropped == 1
    assert bridge.high_water == 1


def test_run_scope_factory_interface_has_one_method() -> None:
    # The deletion test for a deep seam: adapters learn one lifecycle operation, while validation,
    # failure containment, ordering, and transport remain hidden behind it.
    public = {
        name
        for name, value in vars(RunLogScopeFactory).items()
        if isinstance(value, Callable) and not name.startswith("_")
    }

    assert public == {"open_run_scope"}
