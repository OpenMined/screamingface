"""Strict CloudEvents lifecycle decoder for one SF Engine Run."""

from __future__ import annotations

import json
import logging
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

_LOG = logging.getLogger(__name__)
_MAX_CONSECUTIVE_REPLAY_REQUESTS = 3
_MAX_STREAM_REATTACH_REQUESTS = 3
# Frames the control plane emits outside the broker's sequencer, so they never carry one.
_UNSEQUENCED_TYPES = frozenset({"ai.url4.heartbeat", "ai.url4.error"})
# Frames that MAY arrive either way: the broker stamps a sequence on the ones it relays, but
# url4-cloud also injects notices out of band (a re-attach cache-policy warning, a
# cache-control override) which bypass it entirely.
# INVARIANT: only frames that mutate no _RunState may appear in either set. Gap detection,
# event-id de-duplication, and the replay-order guarantee all live on the sequenced path, so
# an unsequenced terminated would build an outcome from a stream never checked for gaps, and
# an unsequenced cost.usage would corrupt the billing total the user reads in their Report.
# AIDEV-NOTE: keying on the ABSENCE of a field is a tolerant-reader shim — "out of band by
# design" and "the broker dropped the sequence" are indistinguishable on the wire. The
# durable fix is a distinct server-side CloudEvent type for advisory notices.
_ADVISORY_TYPES = frozenset({"ai.url4.log"})
_UNSEQUENCED_LABELS = {"ai.url4.heartbeat": "heartbeat"}
_BENCHMARK_PROGRESS_KIND = "screamingface.benchmark.progress"


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
        self._consecutive_replay_requests = 0
        self._stream_reattach_requests = 0
        self._benchmark_progress: events.BenchmarkProgress | None = None

    def accept(self, raw: str | bytes) -> _Accepted:
        payload = _payload(raw)
        event_type = _text(payload, "type")
        # INVARIANT: the discriminator is the presence of "sequence" ALONE. "sequencetype"
        # annotates "sequence"; with no sequence it annotates nothing. Keying on both fields
        # would reclassify a sequenced frame whose sequencetype is missing as advisory and
        # silently skip its handler, instead of rejecting a malformed envelope.
        if event_type in _UNSEQUENCED_TYPES or (
            event_type in _ADVISORY_TYPES and payload.get("sequence") is None
        ):
            return self._accept_unsequenced(payload, event_type)
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
        }
        try:
            handler = handlers[event_type]
        except KeyError:
            raise ExecutionError(f"unsupported SF Engine CloudEvent type {event_type!r}") from None
        return handler(envelope, data)

    def _accept_unsequenced(
        self,
        payload: Mapping[str, object],
        event_type: str,
    ) -> _Accepted:
        label = _UNSEQUENCED_LABELS.get(event_type, event_type)
        data = _object(payload.get("data"), f"{label} data")
        self._observe_run(_common_envelope(payload)["run_id"])
        if event_type == "ai.url4.error":
            code, message = _advisory_error(data)
            if code == "stream_failed":
                self._stream_reattach_requests += 1
                if self._stream_reattach_requests > _MAX_STREAM_REATTACH_REQUESTS:
                    raise ExecutionError(
                        message,
                        code="event_stream_failed",
                        permanent=False,
                        details=data,
                    )
                return _Accepted(replay_from=self._last_sequence + 1)
        elif event_type == "ai.url4.log":
            _advisory_log(data)
        return _Accepted()

    def _accept_sequence(self, payload: Mapping[str, object]) -> _Accepted | None:
        sequence = _sequence(payload)
        event_id = _text(payload, "id")
        if sequence <= self._last_sequence:
            return _Accepted()
        if event_id in self._event_ids:
            raise ExecutionError("SF Engine reused a CloudEvent event id at a new sequence")
        if sequence > self._last_sequence + 1:
            self._consecutive_replay_requests += 1
            if self._consecutive_replay_requests > _MAX_CONSECUTIVE_REPLAY_REQUESTS:
                raise ExecutionError(
                    "SF Engine repeatedly failed to replay a missing Run event",
                    code="event_stream_replay_exhausted",
                    permanent=False,
                )
            return _Accepted(replay_from=self._last_sequence + 1)
        self._consecutive_replay_requests = 0
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
        if not _is_benchmark_progress(data):
            return _Accepted(event=_log(envelope, data))
        try:
            event = _log(envelope, data)
            if not isinstance(event, events.BenchmarkProgress):  # pragma: no cover - kind pins it
                raise ExecutionError("SF Engine Benchmark progress kind was not preserved")
            self._validate_benchmark_progress(event)
        except ExecutionError:
            _LOG.warning("Ignored invalid SF Engine Benchmark progress Event", exc_info=True)
            return _Accepted()
        return _Accepted(event=event)

    def _validate_benchmark_progress(self, event: events.BenchmarkProgress) -> None:
        prior = self._benchmark_progress
        if prior is not None:
            if (
                event.benchmark_id != prior.benchmark_id
                or event.benchmark_revision != prior.benchmark_revision
                or event.total_cases != prior.total_cases
            ):
                raise ExecutionError("SF Engine changed Benchmark progress identity")
            if event.queued_cases > prior.queued_cases:
                raise ExecutionError("SF Engine Benchmark progress queued count regressed")
            if event.complete_cases < prior.complete_cases:
                raise ExecutionError("SF Engine Benchmark progress complete count regressed")
            if event.scored_cases < prior.scored_cases:
                raise ExecutionError("SF Engine Benchmark progress scored count regressed")
        self._benchmark_progress = event

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


def _advisory_error(data: Mapping[str, object]) -> tuple[str, str]:
    code = _text(data, "code")
    message = _text(data, "message")
    _optional_text(data.get("ref_id"), "error ref_id")
    return code, message


def _advisory_log(data: Mapping[str, object]) -> None:
    """Validate an out-of-band notice and surface it without inventing a sequence.

    WHY: the notice cannot become a public Event — ``events.Event.sequence`` is a mandatory
    positive integer, and inventing one would pollute the replay order the sequence defines.
    Dropping it silently is worse than the crash it replaces, though: the server sends these
    precisely so a caller learns its declaration was overridden. Logging keeps that promise.
    """

    _severity(_text(data, "severity_text"))
    _integer(data.get("severity_number"), "log severity_number")
    _log_attributes(data.get("attributes", {}))
    _LOG.warning("SF Engine notice: %s", _raw_text(data, "body"))


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


def _log(envelope: dict[str, Any], data: Mapping[str, object]) -> events.Event:
    severity = _severity(_text(data, "severity_text"))
    number = _integer(data.get("severity_number"), "log severity_number")
    attributes = _log_attributes(data.get("attributes", {}))
    if attributes.get("screamingface.event.kind") == _BENCHMARK_PROGRESS_KIND:
        return _benchmark_progress(envelope, attributes)
    return events.Log(
        **envelope,
        severity_number=number,
        severity_text=severity,
        body=_raw_text(data, "body"),
        attributes=attributes,
    )


def _is_benchmark_progress(data: Mapping[str, object]) -> bool:
    attributes = data.get("attributes")
    return isinstance(attributes, Mapping) and (
        attributes.get("screamingface.event.kind") == _BENCHMARK_PROGRESS_KIND
    )


def _benchmark_progress(
    envelope: dict[str, Any],
    attributes: Mapping[str, str | int | float | bool | None],
) -> events.BenchmarkProgress:
    expected = {
        "screamingface.event.kind",
        "benchmark.id",
        "benchmark.revision",
        "cases.total",
        "cases.queued",
        "cases.running_candidate",
        "cases.grading",
        "cases.complete",
        "cases.scored",
        "score.coverage",
        "score.provisional",
    }
    if set(attributes) != expected:
        raise ExecutionError("SF Engine Benchmark progress attributes are invalid")
    try:
        return events.BenchmarkProgress(
            **envelope,
            benchmark_id=_required_text(attributes.get("benchmark.id"), "benchmark id"),
            benchmark_revision=_required_text(
                attributes.get("benchmark.revision"), "benchmark revision"
            ),
            total_cases=_integer(attributes.get("cases.total"), "total Cases"),
            queued_cases=_integer(attributes.get("cases.queued"), "queued Cases"),
            running_candidate_cases=_integer(
                attributes.get("cases.running_candidate"), "running Candidate Cases"
            ),
            grading_cases=_integer(attributes.get("cases.grading"), "grading Cases"),
            complete_cases=_integer(attributes.get("cases.complete"), "complete Cases"),
            scored_cases=_integer(attributes.get("cases.scored"), "scored Cases"),
            coverage=_number(attributes.get("score.coverage"), "score coverage"),
            provisional_score=_optional_number(
                attributes.get("score.provisional"), "provisional score"
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionError(f"SF Engine Benchmark progress is invalid: {exc}") from exc


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
        finish_reasons=_optional_text_tuple(
            data.get("gen_ai.response.finish_reasons"),
            "span finish reasons",
        ),
        refusal=_optional_text(data.get("refusal"), "span refusal"),
    )


def _usage(envelope: dict[str, Any], data: Mapping[str, object]) -> events.Usage:
    usage = _object(data.get("usage"), "cost usage tokens")
    cost = _object(data.get("cost"), "cost usage cost")
    pricing_version = _text(data, "pricing_version")
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
    # WHY guarded on `parts` (OME-861): a provider may author ONE amount with no per-class split —
    # OpenRouter reports exactly that — so the Engine legitimately publishes a total with every
    # component at zero (`url4.streaming`'s CostBreakdown accepts Σ components <= total_usd since
    # OME-850). A bare `total != parts` therefore fired on EVERY priced run, which is noise a reader
    # cannot act on, in a library people run in notebooks.
    # INVARIANT: an ABSENT breakdown is silence, not disagreement. A breakdown that WAS supplied and
    # still disagrees is incoherent and keeps its warning — the guard narrows the condition, it does
    # not remove it. Either way `total_usd` wins, because it is the authoritative field.
    # AIDEV-NOTE: residual — a genuinely PARTIAL breakdown (some classes known, summing below the
    # total) still warns. No producer sends one today; revisit if that changes.
    if parts and total != parts:
        _LOG.warning(
            "SF Engine cost total_usd does not equal its parts; using total_usd "
            "(total=%s, parts=%s)",
            total,
            parts,
        )
    unpriced = pricing_version == "unpriced"
    accounting = AccountingUsage(
        input_tokens=_integer(usage.get("gen_ai.usage.input_tokens", 0), "input tokens"),
        output_tokens=_integer(usage.get("gen_ai.usage.output_tokens", 0), "output tokens"),
        cache_read_tokens=(
            None
            if unpriced
            else _integer(
                usage.get("gen_ai.usage.cache_read_tokens", 0),
                "cache read tokens",
            )
        ),
        cache_creation_tokens=(
            None
            if unpriced
            else _integer(
                usage.get("gen_ai.usage.cache_creation_tokens", 0),
                "cache creation tokens",
            )
        ),
        reasoning_tokens=(
            None
            if unpriced
            else _integer(
                usage.get("gen_ai.usage.reasoning_tokens", 0),
                "reasoning tokens",
            )
        ),
        cost_usd=None if unpriced else total,
    )
    return events.Usage(
        **envelope,
        scope=_usage_scope(_text(data, "scope")),
        provider=_text(data, "gen_ai.provider.name"),
        model=_text(data, "gen_ai.response.model"),
        pricing_version=pricing_version,
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


def _optional_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ExecutionError(f"SF Engine {label} must be an array of non-empty strings")
    return tuple(_required_text(item, label) for item in value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionError(f"SF Engine {label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExecutionError(f"SF Engine {label} must be a finite number")
    selected = float(value)
    if not math.isfinite(selected):
        raise ExecutionError(f"SF Engine {label} must be a finite number")
    return selected


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)


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
