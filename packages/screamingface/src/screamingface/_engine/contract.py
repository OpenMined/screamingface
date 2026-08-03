"""Strict CloudEvents lifecycle decoder for one SF Engine Run."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from screamingface import events
from screamingface._core.ports import _RunOutcome
from screamingface.errors import ExecutionError
from screamingface.report import Usage as AccountingUsage


@dataclass(frozen=True, slots=True)
class _Accepted:
    event: events.Event | None = None
    outcome: _RunOutcome | None = None
    replay_from: int | None = None


class _RunState:
    """Validate one ordered CloudEvents stream and identify its root outcome."""

    def __init__(self, expected_url4: str) -> None:
        # INVARIANT: sequence and Event IDs define replay order within exactly one Run.
        self._expected_url4 = expected_url4
        self._run_id: str | None = None
        self._root_source: str | None = None
        self._started_at: datetime | None = None
        self._result: tuple[str, str | None] | None = None
        self._root_usage: AccountingUsage | None = None
        self._last_sequence = 0
        self._event_ids: set[str] = set()

    def accept(self, raw: str | bytes) -> _Accepted:
        payload = _payload(raw)
        event_type = _text(payload, "type")
        if event_type == "ai.url4.heartbeat":
            _object(payload.get("data"), "heartbeat data")
            self._observe_run(_common_envelope(payload)["run_id"])
            return _Accepted()
        sequence_result = self._accept_sequence(payload)
        if sequence_result is not None:
            return sequence_result
        sequence = _sequence(payload)
        envelope = _envelope(payload, sequence)
        self._observe_run(envelope["run_id"])
        data = _object(payload.get("data"), f"{event_type} data")
        handlers = {
            "ai.url4.started": self._started,
            "ai.url4.log": self._log,
            "ai.url4.span": self._span,
            "ai.url4.cost.usage": self._usage,
            "ai.url4.result": self._result_event,
            "ai.url4.terminated": self._terminated,
            "ai.url4.error": self._error,
        }
        try:
            handler = handlers[event_type]
        except KeyError:
            raise ExecutionError(f"unsupported SF Engine CloudEvent type {event_type!r}") from None
        return handler(envelope, data)

    def _accept_sequence(self, payload: Mapping[str, object]) -> _Accepted | None:
        sequence = _sequence(payload)
        event_id = _text(payload, "id")
        if sequence <= self._last_sequence:
            return _Accepted()
        if event_id in self._event_ids:
            raise ExecutionError("SF Engine reused a CloudEvent event id at a new sequence")
        if sequence > self._last_sequence + 1:
            return _Accepted(replay_from=self._last_sequence + 1)
        self._event_ids.add(event_id)
        self._last_sequence = sequence
        return None

    def _observe_run(self, run_id: str) -> None:
        if self._run_id is None:
            self._run_id = run_id
        elif run_id != self._run_id:
            raise ExecutionError("SF Engine changed run subject within one stream")

    def _started(self, envelope: dict[str, Any], data: dict[str, object]) -> _Accepted:
        url4 = _text(data, "url4")
        event = events.Started(**envelope, url4=url4)
        if self._root_source is None and url4 == self._expected_url4:
            self._root_source = envelope["source"]
            self._started_at = envelope["timestamp"]
        elif envelope["source"] == self._root_source:
            raise ExecutionError("SF Engine emitted duplicate root started Events")
        return _Accepted(event=event)

    def _log(self, envelope: dict[str, Any], data: dict[str, object]) -> _Accepted:
        return _Accepted(event=_log(envelope, data))

    def _span(self, envelope: dict[str, Any], data: dict[str, object]) -> _Accepted:
        return _Accepted(event=_span(envelope, data))

    def _usage(self, envelope: dict[str, Any], data: dict[str, object]) -> _Accepted:
        usage_event = _usage(envelope, data)
        if envelope["source"] == self._root_source and usage_event.scope == "subtree":
            self._root_usage = usage_event.usage
        return _Accepted(event=usage_event)

    def _result_event(self, envelope: dict[str, Any], data: dict[str, object]) -> _Accepted:
        if envelope["source"] != self._root_source:
            return _Accepted()
        if self._result is not None:
            raise ExecutionError("SF Engine emitted duplicate root result Events")
        body = _raw_text(data, "body")
        media_type = _optional_text(data.get("media_type"), "media_type")
        self._result = (body, media_type)
        return _Accepted()

    def _error(self, envelope: dict[str, Any], data: dict[str, object]) -> _Accepted:
        del envelope
        raise ExecutionError(
            _text(data, "message"),
            code=_text(data, "code"),
            permanent=False,
            details=data,
        )

    def _terminated(
        self,
        envelope: dict[str, Any],
        data: dict[str, object],
    ) -> _Accepted:
        error = _termination_error(data.get("error"))
        status = _text(data, "status")
        if status not in {"succeeded", "failed", "stopped", "timed_out"}:
            raise ExecutionError("SF Engine termination status is invalid")
        selected_status = _termination_status(status)
        event = events.Terminated(**envelope, status=selected_status, error=error)
        if envelope["source"] != self._root_source:
            return _Accepted(event=event)
        if status != "succeeded":
            raise ExecutionError(
                error.message if error is not None else f"SF Engine Run {status}",
                code=error.code if error is not None else status,
                permanent=error.permanent if error is not None else None,
                details=data,
            )
        if self._result is None:
            raise ExecutionError("SF Engine succeeded without a root result")
        if self._run_id is None or self._started_at is None:
            raise ExecutionError("SF Engine terminated before the root Run started")
        return _Accepted(
            event=event,
            outcome=_RunOutcome(
                run_id=self._run_id,
                started_at=self._started_at,
                completed_at=envelope["timestamp"],
                result_body=self._result[0],
                media_type=self._result[1],
                root_usage=self._root_usage,
            ),
        )


def _payload(raw: str | bytes) -> dict[str, object]:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExecutionError("SF Engine CloudEvent must be UTF-8 JSON") from exc
    if not isinstance(raw, str):
        raise ExecutionError("SF Engine WebSocket frame must contain text JSON")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExecutionError("SF Engine CloudEvent must be valid JSON") from exc
    payload = _object(value, "CloudEvent")
    if payload.get("specversion") != "1.0":
        raise ExecutionError("SF Engine CloudEvent must use specversion '1.0'")
    if payload.get("datacontenttype", "application/json") != "application/json":
        raise ExecutionError("SF Engine CloudEvent data must use application/json")
    return payload


def _sequence(payload: Mapping[str, object]) -> int:
    if payload.get("sequencetype") != "Integer":
        raise ExecutionError("SF Engine CloudEvent sequence must declare Integer semantics")
    value = payload.get("sequence")
    if not isinstance(value, str) or not value.isdigit() or int(value) < 1:
        raise ExecutionError("SF Engine CloudEvent sequence must be a positive integer string")
    return int(value)


def _envelope(
    payload: Mapping[str, object],
    sequence: int,
) -> dict[str, Any]:
    return {
        **_common_envelope(payload),
        "sequence": sequence,
    }


def _common_envelope(payload: Mapping[str, object]) -> dict[str, Any]:
    return {
        "id": _text(payload, "id"),
        "run_id": _text(payload, "subject"),
        "timestamp": _timestamp(payload.get("time")),
        "source": _text(payload, "source"),
        "traceparent": _optional_text(payload.get("traceparent"), "traceparent"),
        "tracestate": _optional_text(payload.get("tracestate"), "tracestate"),
    }


def _log(envelope: dict[str, Any], data: Mapping[str, object]) -> events.Log:
    severity = _severity(_text(data, "severity_text"))
    number = _integer(data.get("severity_number"), "log severity_number")
    attributes = _log_attributes(data.get("attributes", {}))
    return events.Log(
        **envelope,
        severity_number=number,
        severity_text=severity,
        body=_raw_text(data, "body"),
        attributes=attributes,
    )


def _span(envelope: dict[str, Any], data: Mapping[str, object]) -> events.Span:
    return events.Span(
        **envelope,
        name=_text(data, "name"),
        operation=_text(data, "gen_ai.operation.name"),
        start=_timestamp(data.get("start")),
        end=_optional_timestamp(data.get("end")),
        status=_span_status(_text(data, "status")),
        span_kind=_span_kind(_text(data, "kind")),
        provider=_optional_text(data.get("gen_ai.provider.name"), "span provider"),
        request_model=_optional_text(
            data.get("gen_ai.request.model"),
            "span request model",
        ),
        response_model=_optional_text(
            data.get("gen_ai.response.model"),
            "span response model",
        ),
        input_tokens=_optional_integer(
            data.get("gen_ai.usage.input_tokens"),
            "span input tokens",
        ),
        output_tokens=_optional_integer(
            data.get("gen_ai.usage.output_tokens"),
            "span output tokens",
        ),
    )


def _usage(envelope: dict[str, Any], data: Mapping[str, object]) -> events.Usage:
    usage = _object(data.get("usage"), "cost usage tokens")
    cost = _object(data.get("cost"), "cost usage cost")
    total = _decimal(cost.get("total_usd"), "cost total_usd")
    parts = sum(
        (
            _decimal(cost.get(name, 0), f"cost {name}")
            for name in (
                "input_usd",
                "output_usd",
                "cache_read_usd",
                "cache_creation_usd",
                "reasoning_usd",
            )
        ),
        Decimal(),
    )
    if total != parts:
        raise ExecutionError("SF Engine cost total_usd does not equal its parts")
    accounting = AccountingUsage(
        input_tokens=_integer(usage.get("gen_ai.usage.input_tokens", 0), "input tokens"),
        output_tokens=_integer(usage.get("gen_ai.usage.output_tokens", 0), "output tokens"),
        cache_read_tokens=_integer(
            usage.get("gen_ai.usage.cache_read_tokens", 0),
            "cache read tokens",
        ),
        cache_creation_tokens=_integer(
            usage.get("gen_ai.usage.cache_creation_tokens", 0),
            "cache creation tokens",
        ),
        reasoning_tokens=_integer(
            usage.get("gen_ai.usage.reasoning_tokens", 0),
            "reasoning tokens",
        ),
        cost_usd=total,
    )
    return events.Usage(
        **envelope,
        scope=_usage_scope(_text(data, "scope")),
        provider=_text(data, "gen_ai.provider.name"),
        model=_text(data, "gen_ai.response.model"),
        pricing_version=_text(data, "pricing_version"),
        usage=accounting,
    )


def _termination_error(value: object) -> events.TerminationError | None:
    if value is None:
        return None
    data = _object(value, "termination error")
    permanent = data.get("permanent", False)
    if not isinstance(permanent, bool):
        raise ExecutionError("SF Engine termination error permanent must be boolean")
    return events.TerminationError(
        code=_text(data, "code"),
        message=_raw_text(data, "message"),
        permanent=permanent,
    )


def _severity(value: str) -> events.Severity:
    if value not in {"DEBUG", "INFO", "WARN", "ERROR"}:
        raise ExecutionError("SF Engine log severity_text is invalid")
    return cast(events.Severity, value)


def _span_status(value: str) -> events.SpanStatus:
    if value == "ok":
        return "ok"
    if value == "error":
        return "error"
    raise ExecutionError("SF Engine span status is invalid")


def _span_kind(value: str) -> events.SpanKind:
    if value == "client":
        return "client"
    if value == "internal":
        return "internal"
    if value == "server":
        return "server"
    raise ExecutionError("SF Engine span kind is invalid")


def _usage_scope(value: str) -> events.UsageScope:
    if value == "self":
        return "self"
    if value == "subtree":
        return "subtree"
    raise ExecutionError("SF Engine usage scope is invalid")


def _termination_status(value: str) -> events.TerminationStatus:
    if value not in {"succeeded", "failed", "stopped", "timed_out"}:
        raise ExecutionError("SF Engine termination status is invalid")
    return cast(events.TerminationStatus, value)


def _log_attributes(
    value: object,
) -> dict[str, str | int | float | bool | None]:
    attributes = _object(value, "log attributes")
    selected: dict[str, str | int | float | bool | None] = {}
    for name, item in attributes.items():
        if item is not None and not isinstance(item, str | int | float | bool):
            raise ExecutionError("SF Engine log attributes contain a non-scalar value")
        selected[name] = item
    return selected


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ExecutionError(f"SF Engine {label} must be a JSON object")
    return value


def _text(value: Mapping[str, object], name: str) -> str:
    return _required_text(value.get(name), name)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionError(f"SF Engine {label} must be a non-empty string")
    return value.strip()


def _raw_text(value: Mapping[str, object], name: str) -> str:
    selected = value.get(name)
    if not isinstance(selected, str):
        raise ExecutionError(f"SF Engine {name} must be a string")
    return selected


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionError(f"SF Engine {label} must be a non-negative integer")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ExecutionError("SF Engine CloudEvent time must be an RFC 3339 string")
    try:
        selected = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionError("SF Engine CloudEvent time must be an RFC 3339 string") from exc
    if selected.tzinfo is None:
        raise ExecutionError("SF Engine CloudEvent time must include a timezone")
    return selected


def _optional_timestamp(value: object) -> datetime | None:
    return None if value is None else _timestamp(value)


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise ExecutionError(f"SF Engine {label} must be a decimal")
    try:
        selected = Decimal(str(value))
    except InvalidOperation as exc:
        raise ExecutionError(f"SF Engine {label} must be a decimal") from exc
    if not selected.is_finite() or selected < 0 or math.isnan(float(selected)):
        raise ExecutionError(f"SF Engine {label} must be a finite non-negative decimal")
    return selected


__all__: list[str] = []
