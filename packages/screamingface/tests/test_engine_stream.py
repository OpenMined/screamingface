"""Strict client contract for streamed ScreamingFace-engine evaluation."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

import screamingface as sf
import screamingface._benchmark_execution as execution
import screamingface._engine_stream as stream
from screamingface._progress import Progress


def _event(name: str, **fields: object) -> str:
    payload = {
        "schema": "screamingface.evaluation-event.v1",
        "type": name,
        **fields,
    }
    return f"event: {name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _event_payload(name: str, **fields: object) -> str:
    return json.dumps(
        {"schema": "screamingface.evaluation-event.v1", "type": name, **fields},
        separators=(",", ":"),
    )


def _event_lines(name: str, **fields: object) -> list[str]:
    return [f"event: {name}", f"data: {_event_payload(name, **fields)}", ""]


def _transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(stream.httpx, "stream", client.stream)
    monkeypatch.setattr(stream, "current_engine_url", lambda: "http://engine.test")
    return client


def test_stream_returns_final_plaintext_and_reports_real_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = (
        _event("accepted")
        + _event("running", elapsed_seconds=5.0)
        + _event(
            "progress",
            stage="model",
            status="started",
            label="Running gemini/2.5-flash",
        )
        + _event(
            "progress",
            stage="grading",
            status="completed",
            label="Graded case q1",
        )
        + _event("complete", content_type="text/plain", value='{"answer":"A"}')
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "text/event-stream"
        assert request.url.path == "/v1"
        assert request.url.params["q"] == "expression"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = _transport(monkeypatch, handler)
    observed: list[stream.EvaluationEvent] = []
    try:
        value = stream.evaluate_stream(
            "expression",
            timeout=10,
            on_event=observed.append,
        )
    finally:
        client.close()

    assert value == '{"answer":"A"}'
    assert observed == [
        stream.EvaluationEvent("accepted"),
        stream.EvaluationEvent("running", 5.0),
        stream.EvaluationEvent(
            "progress",
            stage="model",
            status="started",
            label="Running gemini/2.5-flash",
        ),
        stream.EvaluationEvent(
            "progress",
            stage="grading",
            status="completed",
            label="Graded case q1",
        ),
    ]


def test_stream_maps_typed_terminal_and_pre_stream_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _event("accepted") + _event(
        "error",
        status=502,
        error={"code": "provider_unavailable", "message": "provider setup incomplete"},
    )
    responses = iter(
        [
            httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}),
            httpx.Response(
                503,
                json={"error": {"code": "overloaded", "message": "retry shortly"}},
            ),
        ]
    )
    client = _transport(monkeypatch, lambda _request: next(responses))
    try:
        with pytest.raises(sf.EngineProtocolError, match="provider_unavailable"):
            stream.evaluate_stream("expression", timeout=10)
        with pytest.raises(sf.EngineProtocolError, match="overloaded"):
            stream.evaluate_stream("expression", timeout=10)
    finally:
        client.close()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (_event("complete", content_type="text/plain", value="ok"), "must be first"),
        (_event("accepted"), "without a terminal event"),
        (
            _event("accepted") + _event("complete", content_type="application/json", value="{}"),
            "content_type must be text/plain",
        ),
    ],
)
def test_stream_rejects_protocol_drift(
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    message: str,
) -> None:
    client = _transport(
        monkeypatch,
        lambda _request: httpx.Response(
            200,
            text=body,
            headers={"content-type": "text/event-stream"},
        ),
    )
    try:
        with pytest.raises(sf.EngineProtocolError, match=message):
            stream.evaluate_stream("expression", timeout=10)
    finally:
        client.close()


def test_stream_maps_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = _transport(monkeypatch, unavailable)
    try:
        with pytest.raises(sf.EngineConnectionError, match="could not reach"):
            stream.evaluate_stream("expression", timeout=10)
    finally:
        client.close()


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        (["broken", ""], "malformed field"),
        (["event: accepted", "event: accepted", "data: {}", ""], "repeats its name"),
        (["retry: 1", ""], "unsupported field"),
        (["event: accepted", ""], "event is incomplete"),
        (["event: accepted", f"data: {_event_payload('accepted')}"], "inside an event"),
        (
            ["event: running", f"data: {_event_payload('accepted')}", ""],
            "does not match payload type",
        ),
        (
            [
                "event: accepted",
                'data: {"schema":"wrong","type":"accepted"}',
                "",
            ],
            "expected schema",
        ),
        (
            _event_lines("accepted") + _event_lines("mystery"),
            "unknown evaluation event type",
        ),
        (
            _event_lines("accepted") + _event_lines("accepted"),
            "must occur once",
        ),
        (
            _event_lines("accepted")
            + _event_lines("progress", stage="unknown", status="started", label="Working"),
            "unknown progress event stage",
        ),
        (
            _event_lines("accepted")
            + _event_lines("progress", stage="model", status="waiting", label="Working"),
            "unknown progress event status",
        ),
        (
            _event_lines("accepted") + _event_lines("complete", content_type="text/plain", value=1),
            "value must be a string",
        ),
        (
            _event_lines("accepted")
            + _event_lines(
                "error",
                status=200,
                error={"code": "wrong", "message": "wrong"},
            ),
            "HTTP error status",
        ),
        (
            _event_lines("accepted") + _event_lines("running", elapsed_seconds="soon"),
            "must be numeric",
        ),
        (
            _event_lines("accepted") + _event_lines("running", elapsed_seconds=-1),
            "must not be negative",
        ),
    ],
)
def test_stream_rejects_malformed_event_fields(lines: list[str], message: str) -> None:
    with pytest.raises(sf.EngineProtocolError, match=message):
        stream._consume_events(lines, None)


def test_benchmark_progress_uses_route_events_and_real_completed_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def evaluate(
        _expression: str,
        *,
        timeout: float,
        on_event: Callable[[stream.EvaluationEvent], None] | None,
    ) -> str:
        assert timeout > 0
        assert on_event is not None
        on_event(stream.EvaluationEvent("accepted"))
        on_event(
            stream.EvaluationEvent(
                "progress",
                stage="dataset",
                status="started",
                label="Loading GPQA Diamond cases",
            )
        )
        on_event(
            stream.EvaluationEvent(
                "progress",
                stage="model",
                status="started",
                label="Running gemini/2.5-flash",
            )
        )
        on_event(
            stream.EvaluationEvent(
                "progress",
                stage="grading",
                status="completed",
                label="Graded case q1",
            )
        )
        on_event(stream.EvaluationEvent("running", 10.0))
        on_event(
            stream.EvaluationEvent(
                "progress",
                stage="grading",
                status="completed",
                label="Graded case q2",
            )
        )
        on_event(
            stream.EvaluationEvent(
                "progress",
                stage="aggregating",
                status="started",
                label="Aggregating 2 benchmark cases",
            )
        )
        return "report"

    monkeypatch.setattr(execution, "evaluate_stream", evaluate)
    tracker = Progress("duo", "gpqa@1", False)

    assert execution._request("expression", tracker=tracker, total=2) == "report"
    assert tracker._state.stage == "aggregating"
    assert tracker._state.label == "Aggregating 2 benchmark cases"
    assert tracker._state.completed == 2
    assert tracker._state.total == 2
