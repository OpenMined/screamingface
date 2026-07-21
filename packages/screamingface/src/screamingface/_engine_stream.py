"""Strict synchronous client for ScreamingFace evaluation event streams."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

import httpx

from screamingface._config import current_engine_url
from screamingface._engine_http import (
    EVAL_PATH,
    engine_error,
    exact_fields,
    nonblank,
    object_value,
    unique_json_object,
)
from screamingface.errors import EngineConnectionError, EngineProtocolError

_STREAM_SCHEMA = "screamingface.evaluation-event.v1"


@dataclass(frozen=True, slots=True)
class EvaluationEvent:
    """One validated non-terminal evaluation lifecycle event."""

    type: str
    elapsed_seconds: float | None = None
    stage: str | None = None
    status: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class _Terminal:
    value: str


@dataclass(slots=True)
class _SSEBlock:
    event: str | None = None
    data: list[str] | None = None

    def add(self, line: str) -> None:
        field, separator, value = line.partition(":")
        if not separator:
            raise EngineProtocolError("evaluation stream contains a malformed field")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            if self.event is not None:
                raise EngineProtocolError("evaluation stream event repeats its name")
            self.event = value
            return
        if field == "data":
            if self.data is None:
                self.data = []
            self.data.append(value)
            return
        raise EngineProtocolError(f"evaluation stream contains unsupported field {field!r}")

    def finish(self) -> tuple[str, str] | None:
        if self.event is None and not self.data:
            return None
        if self.event is None or not self.data:
            raise EngineProtocolError("evaluation stream event is incomplete")
        return self.event, "\n".join(self.data)


def evaluate_stream(
    expression: str,
    *,
    timeout: float,
    on_event: Callable[[EvaluationEvent], None] | None = None,
) -> str:
    """Evaluate URL4 over SSE and return its unchanged final plaintext value."""

    base_url = current_engine_url()
    try:
        with httpx.stream(
            "GET",
            f"{base_url}{EVAL_PATH}",
            params={"q": expression},
            headers={"accept": "text/event-stream"},
            timeout=timeout,
        ) as response:
            if not response.is_success:
                response.read()
                _raise_http_error(response)
            content_type = _media_type(response.headers.get("content-type", ""))
            if content_type != "text/event-stream":
                raise EngineProtocolError("URL4 benchmark evaluation must return text/event-stream")
            return _consume_events(response.iter_lines(), on_event)
    except httpx.TimeoutException as exc:
        raise EngineConnectionError("URL4 benchmark evaluation timed out") from exc
    except (httpx.RequestError, httpx.InvalidURL) as exc:
        raise EngineConnectionError(
            f"could not reach the configured URL4 engine at {base_url}"
        ) from exc


def _consume_events(
    lines: Iterable[str],
    on_event: Callable[[EvaluationEvent], None] | None,
) -> str:
    accepted = False
    for event_name, data in _sse_messages(lines):
        try:
            event, accepted = _decode_event(event_name, data, accepted, on_event)
            if event is not None:
                return event.value
        except EngineProtocolError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise EngineProtocolError(f"invalid evaluation event: {exc}") from exc
    raise EngineProtocolError("evaluation stream ended without a terminal event")


def _sse_messages(lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    block = _SSEBlock()
    for line in lines:
        if not line:
            finished = block.finish()
            if finished is not None:
                yield finished
            block = _SSEBlock()
            continue
        if line.startswith(":"):
            continue
        block.add(line)
    if block.finish() is not None:
        raise EngineProtocolError("evaluation stream ended inside an event")


def _decode_event(
    event_name: str,
    data: str,
    accepted: bool,
    on_event: Callable[[EvaluationEvent], None] | None,
) -> tuple[_Terminal | None, bool]:
    payload = unique_json_object(data)
    event_type = nonblank(payload.get("type"), "evaluation event type")
    if event_name != event_type:
        raise ValueError("SSE event name does not match payload type")
    if payload.get("schema") != _STREAM_SCHEMA:
        raise ValueError(f"expected schema {_STREAM_SCHEMA!r}")
    if event_type == "complete":
        _require_accepted(accepted)
        return _Terminal(_complete(payload)), accepted
    if event_type == "error":
        _require_accepted(accepted)
        _raise_stream_error(payload)
    return None, _nonterminal(event_type, payload, accepted, on_event)


def _nonterminal(
    event_type: str,
    payload: dict[str, object],
    accepted: bool,
    on_event: Callable[[EvaluationEvent], None] | None,
) -> bool:
    if event_type == "accepted":
        return _accepted(payload, accepted, on_event)
    _require_accepted(accepted)
    handler = {"running": _running, "progress": _progress}.get(event_type)
    if handler is None:
        raise ValueError(f"unknown evaluation event type {event_type!r}")
    handler(payload, on_event)
    return accepted


def _require_accepted(accepted: bool) -> None:
    if not accepted:
        raise ValueError("accepted event must be first")


def _accepted(
    payload: dict[str, object],
    already_accepted: bool,
    on_event: Callable[[EvaluationEvent], None] | None,
) -> bool:
    exact_fields(payload, {"schema", "type"}, "accepted event")
    if already_accepted:
        raise ValueError("accepted event must occur once")
    _notify(on_event, EvaluationEvent("accepted"))
    return True


def _running(
    payload: dict[str, object],
    on_event: Callable[[EvaluationEvent], None] | None,
) -> None:
    exact_fields(payload, {"schema", "type", "elapsed_seconds"}, "running event")
    _notify(on_event, EvaluationEvent("running", _elapsed(payload["elapsed_seconds"])))


def _progress(
    payload: dict[str, object],
    on_event: Callable[[EvaluationEvent], None] | None,
) -> None:
    exact_fields(payload, {"schema", "type", "stage", "status", "label"}, "progress event")
    stage = nonblank(payload["stage"], "progress event stage")
    if stage not in {"dataset", "model", "grading", "aggregating"}:
        raise ValueError(f"unknown progress event stage {stage!r}")
    status = nonblank(payload["status"], "progress event status")
    if status not in {"started", "completed"}:
        raise ValueError(f"unknown progress event status {status!r}")
    label = nonblank(payload["label"], "progress event label")
    _notify(
        on_event,
        EvaluationEvent("progress", stage=stage, status=status, label=label),
    )


def _complete(payload: dict[str, object]) -> str:
    exact_fields(
        payload,
        {"schema", "type", "content_type", "value"},
        "complete event",
    )
    if payload["content_type"] != "text/plain":
        raise ValueError("complete event content_type must be text/plain")
    value = payload["value"]
    if not isinstance(value, str):
        raise TypeError("complete event value must be a string")
    return value


def _raise_stream_error(payload: dict[str, object]) -> None:
    exact_fields(payload, {"schema", "type", "status", "error"}, "error event")
    status = payload["status"]
    if isinstance(status, bool) or not isinstance(status, int) or not 400 <= status <= 599:
        raise ValueError("error event status must be an HTTP error status")
    error = object_value(payload["error"], "evaluation event error")
    exact_fields(error, {"code", "message"}, "evaluation event error")
    code = nonblank(error["code"], "evaluation event error code")
    message = nonblank(error["message"], "evaluation event error message")
    raise EngineProtocolError(f"URL4 engine returned HTTP {status} ({code}): {message}")


def _raise_http_error(response: httpx.Response) -> None:
    error = engine_error(response)
    if error is None:
        raise EngineProtocolError(
            f"URL4 engine returned HTTP {response.status_code} for benchmark evaluation"
        )
    code, message = error
    raise EngineProtocolError(
        f"URL4 engine returned HTTP {response.status_code} ({code}): {message}"
    )


def _elapsed(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("running event elapsed_seconds must be numeric")
    elapsed = float(value)
    if elapsed < 0:
        raise ValueError("running event elapsed_seconds must not be negative")
    return elapsed


def _notify(
    callback: Callable[[EvaluationEvent], None] | None,
    event: EvaluationEvent,
) -> None:
    if callback is not None:
        callback(event)


def _media_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


__all__ = ["EvaluationEvent", "evaluate_stream"]
