from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest

import screamingface as sf
from screamingface import _engine_contract
from screamingface._engine_contract import _RunState

URL4 = "(@)!'hello'"


def frame(
    event_type: str,
    data: dict[str, object],
    *,
    sequence: int | None,
    source: str = "/trace/run_1/node/root",
    event_id: str | None = None,
) -> str:
    value: dict[str, object] = {
        "specversion": "1.0",
        "id": event_id or f"event_{sequence or 'heartbeat'}",
        "source": source,
        "subject": "run_1",
        "time": "2026-07-25T16:00:00Z",
        "type": event_type,
        "datacontenttype": "application/json",
        "data": data,
    }
    if sequence is not None:
        value["sequence"] = str(sequence)
        value["sequencetype"] = "Integer"
    return json.dumps(value)


def test_state_decodes_public_events_and_root_lifecycle() -> None:
    state = _RunState(URL4)

    started = state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    result = state.accept(
        frame(
            "ai.url4.result",
            {"body": '{"schema":"result"}', "media_type": "application/json"},
            sequence=2,
        )
    )
    terminated = state.accept(
        frame(
            "ai.url4.terminated",
            {"status": "succeeded", "error": None},
            sequence=3,
        )
    )

    assert isinstance(started.event, sf.events.Started)
    assert result.event is None
    assert terminated.outcome is not None
    assert terminated.outcome.run_id == "run_1"
    assert terminated.outcome.result_body == '{"schema":"result"}'
    assert terminated.outcome.started_at.isoformat() == "2026-07-25T16:00:00+00:00"


def test_heartbeat_is_internal_and_does_not_participate_in_stream_sequence() -> None:
    state = _RunState(URL4)

    accepted = state.accept(frame("ai.url4.heartbeat", {}, sequence=None))

    assert accepted.event is None
    assert accepted.outcome is None
    assert accepted.replay_from is None


def test_heartbeat_still_validates_its_run_envelope() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.heartbeat", {}, sequence=None))
    changed = json.loads(frame("ai.url4.heartbeat", {}, sequence=None))
    changed["subject"] = "run_2"

    with pytest.raises(sf.ExecutionError, match="changed run subject"):
        state.accept(json.dumps(changed))

    malformed = json.loads(frame("ai.url4.heartbeat", {}, sequence=None))
    malformed.pop("source")
    with pytest.raises(sf.ExecutionError, match="source"):
        _RunState(URL4).accept(json.dumps(malformed))


def test_duplicate_frames_are_ignored_and_gaps_request_replay() -> None:
    state = _RunState(URL4)
    first = frame("ai.url4.started", {"url4": URL4}, sequence=1)

    assert state.accept(first).event is not None
    assert state.accept(first).event is None
    assert (
        state.accept(
            frame(
                "ai.url4.log",
                {
                    "severity_number": 9,
                    "severity_text": "INFO",
                    "body": "working",
                    "attributes": {},
                },
                sequence=3,
            )
        ).replay_from
        == 2
    )


def test_reused_event_id_at_a_new_sequence_is_rejected() -> None:
    state = _RunState(URL4)
    state.accept(
        frame(
            "ai.url4.started",
            {"url4": URL4},
            sequence=1,
            event_id="same-event",
        )
    )

    with pytest.raises(sf.ExecutionError, match="event id"):
        state.accept(
            frame(
                "ai.url4.log",
                {
                    "severity_number": 9,
                    "severity_text": "INFO",
                    "body": "working",
                    "attributes": {},
                },
                sequence=2,
                event_id="same-event",
            )
        )


def test_state_rejects_malformed_or_inconsistent_frames() -> None:
    state = _RunState(URL4)

    with pytest.raises(sf.ExecutionError, match="valid JSON"):
        state.accept("not json")

    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    with pytest.raises(sf.ExecutionError, match="changed run subject"):
        changed = json.loads(
            frame(
                "ai.url4.log",
                {
                    "severity_number": 9,
                    "severity_text": "INFO",
                    "body": "working",
                    "attributes": {},
                },
                sequence=2,
            )
        )
        changed["subject"] = "run_2"
        state.accept(json.dumps(changed))


def test_succeeded_root_requires_exactly_one_result() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))

    with pytest.raises(sf.ExecutionError, match="without a root result"):
        state.accept(
            frame(
                "ai.url4.terminated",
                {"status": "succeeded", "error": None},
                sequence=2,
            )
        )


def test_failed_root_becomes_a_structured_execution_error() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))

    with pytest.raises(sf.ExecutionError) as caught:
        state.accept(
            frame(
                "ai.url4.terminated",
                {
                    "status": "failed",
                    "error": {
                        "code": "gateway_timeout",
                        "message": "The model timed out.",
                        "permanent": False,
                    },
                },
                sequence=2,
            )
        )

    assert caught.value.code == "gateway_timeout"
    assert caught.value.permanent is False


def test_root_result_preserves_optional_media_type_without_interpreting_the_body() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    state.accept(
        frame(
            "ai.url4.result",
            {"body": "[mock] done", "media_type": None},
            sequence=2,
        )
    )
    terminated = state.accept(
        frame(
            "ai.url4.terminated",
            {"status": "succeeded", "error": None},
            sequence=3,
        )
    )

    assert terminated.outcome is not None
    assert terminated.outcome.result_body == "[mock] done"
    assert terminated.outcome.media_type is None


def test_state_decodes_log_span_and_non_root_lifecycle() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    log = state.accept(
        frame(
            "ai.url4.log",
            {
                "severity_number": 9,
                "severity_text": "INFO",
                "body": "working",
                "attributes": {"attempt": 1},
            },
            sequence=2,
        )
    )
    span = state.accept(
        frame(
            "ai.url4.span",
            {
                "name": "model",
                "kind": "client",
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "openrouter",
                "gen_ai.request.model": "requested",
                "gen_ai.response.model": "actual",
                "gen_ai.usage.input_tokens": 10,
                "gen_ai.usage.output_tokens": 2,
                "start": "2026-07-25T16:00:00Z",
                "end": "2026-07-25T16:00:01Z",
                "status": "ok",
            },
            sequence=3,
        )
    )
    ignored_result = state.accept(
        frame(
            "ai.url4.result",
            {"body": "child", "media_type": "application/json"},
            sequence=4,
            source="/trace/run_1/node/child",
        )
    )
    child_terminal = state.accept(
        frame(
            "ai.url4.terminated",
            {"status": "succeeded", "error": None},
            sequence=5,
            source="/trace/run_1/node/child",
        )
    )

    assert isinstance(log.event, sf.events.Log)
    assert isinstance(span.event, sf.events.Span)
    assert ignored_result.outcome is None
    assert isinstance(child_terminal.event, sf.events.Terminated)


def test_state_rejects_duplicate_root_events_and_protocol_nacks() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    with pytest.raises(sf.ExecutionError, match="duplicate root started"):
        state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=2))

    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    state.accept(
        frame(
            "ai.url4.result",
            {"body": "{}", "media_type": "application/json"},
            sequence=2,
        )
    )
    with pytest.raises(sf.ExecutionError, match="duplicate root result"):
        state.accept(
            frame(
                "ai.url4.result",
                {"body": "{}", "media_type": "application/json"},
                sequence=3,
            )
        )

    state = _RunState(URL4)
    with pytest.raises(sf.ExecutionError, match="bad attach"):
        state.accept(
            frame(
                "ai.url4.error",
                {"code": "invalid_attach", "message": "bad attach", "ref_id": None},
                sequence=1,
            )
        )


def test_equal_looking_child_started_event_does_not_replace_root_identity() -> None:
    state = _RunState(URL4)
    root = state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    child = state.accept(
        frame(
            "ai.url4.started",
            {"url4": URL4},
            sequence=2,
            source="/trace/run_1/node/child",
        )
    )

    assert isinstance(root.event, sf.events.Started)
    assert isinstance(child.event, sf.events.Started)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(specversion="0.3"), "specversion"),
        (lambda value: value.update(datacontenttype="text/plain"), "application/json"),
        (lambda value: value.pop("sequencetype"), "Integer semantics"),
        (lambda value: value.update(sequence="0"), "positive integer string"),
        (lambda value: value.update(type="ai.url4.unknown"), "unsupported"),
        (lambda value: value.update(time="not-time"), "RFC 3339"),
    ],
)
def test_state_rejects_invalid_envelopes(mutate: object, message: str) -> None:
    value = json.loads(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    cast(Callable[[dict[str, object]], None], mutate)(value)
    with pytest.raises(sf.ExecutionError, match=message):
        _RunState(URL4).accept(json.dumps(value))


def test_state_accepts_utf8_bytes_and_rejects_non_utf8_or_binary_objects() -> None:
    accepted = _RunState(URL4).accept(frame("ai.url4.started", {"url4": URL4}, sequence=1).encode())
    assert accepted.event is not None
    with pytest.raises(sf.ExecutionError, match="UTF-8"):
        _RunState(URL4).accept(b"\xff")
    with pytest.raises(sf.ExecutionError, match="text JSON"):
        _RunState(URL4).accept(cast(Any, 123))


def test_state_rejects_invalid_event_payloads() -> None:
    state = _RunState(URL4)
    state.accept(frame("ai.url4.started", {"url4": URL4}, sequence=1))
    with pytest.raises(sf.ExecutionError, match="media_type"):
        state.accept(
            frame(
                "ai.url4.result",
                {"body": "x", "media_type": 123},
                sequence=2,
            )
        )

    with pytest.raises(sf.ExecutionError, match="severity_text"):
        _RunState(URL4).accept(
            frame(
                "ai.url4.log",
                {
                    "severity_number": 9,
                    "severity_text": "TRACE",
                    "body": "x",
                    "attributes": {},
                },
                sequence=1,
            )
        )
    with pytest.raises(sf.ExecutionError, match="non-scalar"):
        _RunState(URL4).accept(
            frame(
                "ai.url4.log",
                {
                    "severity_number": 9,
                    "severity_text": "INFO",
                    "body": "x",
                    "attributes": {"nested": {}},
                },
                sequence=1,
            )
        )
    with pytest.raises(sf.ExecutionError, match="termination status"):
        _RunState(URL4).accept(
            frame(
                "ai.url4.terminated",
                {"status": "unknown", "error": None},
                sequence=1,
            )
        )
    with pytest.raises(sf.ExecutionError, match="permanent"):
        _RunState(URL4).accept(
            frame(
                "ai.url4.terminated",
                {
                    "status": "failed",
                    "error": {"code": "x", "message": "x", "permanent": "no"},
                },
                sequence=1,
            )
        )


def test_decoder_scalar_helpers_reject_invalid_wire_values() -> None:
    assert _engine_contract._optional_text(None, "x") is None
    assert _engine_contract._optional_integer(None, "x") is None
    assert _engine_contract._optional_timestamp(None) is None
    assert _engine_contract._decimal(Decimal("1"), "x") == Decimal("1")

    invalid_calls = (
        lambda: _engine_contract._object([], "x"),
        lambda: _engine_contract._required_text("", "x"),
        lambda: _engine_contract._raw_text({}, "x"),
        lambda: _engine_contract._integer(-1, "x"),
        lambda: _engine_contract._timestamp(1),
        lambda: _engine_contract._timestamp("2026-01-01"),
        lambda: _engine_contract._decimal(True, "x"),
        lambda: _engine_contract._decimal("not-decimal", "x"),
        lambda: _engine_contract._decimal("-1", "x"),
    )
    for call in invalid_calls:
        with pytest.raises(sf.ExecutionError):
            call()
