from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

import screamingface as sf

NOW = datetime(2026, 7, 25, 16, 0, tzinfo=UTC)


def event_envelope(**overrides: object) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": "event",
        "run_id": "run",
        "sequence": 1,
        "timestamp": NOW,
        "source": "/trace/run/node/op",
    }
    values.update(overrides)
    return values


def test_log_and_span_values_preserve_typed_payloads() -> None:
    log = sf.events.Log(
        **event_envelope(),
        severity_number=9,
        severity_text="INFO",
        body="working",
        attributes={"attempt": 1},
    )
    span = sf.events.Span(
        **event_envelope(sequence=2),
        name="model call",
        operation="chat",
        start=NOW,
        end=NOW + timedelta(seconds=1),
        status="ok",
        span_kind="client",
        input_tokens=10,
        output_tokens=2,
    )

    assert log.attributes == {"attempt": 1}
    assert span.kind == "span"


def test_log_body_preserves_the_protocols_valid_empty_string() -> None:
    log = sf.events.Log(
        **event_envelope(),
        severity_number=9,
        severity_text="INFO",
        body="",
    )

    assert log.body == ""


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.events.Started(**event_envelope(id=" "), url4="x"), "Event id"),
        (
            lambda: sf.events.Started(
                **event_envelope(timestamp=datetime(2026, 1, 1)),
                url4="x",
            ),
            "timezone-aware",
        ),
        (
            lambda: sf.events.Log(
                **event_envelope(),
                severity_number=True,
                severity_text="INFO",
                body="x",
            ),
            "severity_number",
        ),
        (
            lambda: sf.events.Log(
                **event_envelope(),
                severity_number=9,
                severity_text=cast(Any, "TRACE"),
                body="x",
            ),
            "severity_text",
        ),
        (
            lambda: sf.events.Log(
                **event_envelope(),
                severity_number=9,
                severity_text="INFO",
                body="x",
                attributes=cast(Any, {"nested": []}),
            ),
            "scalar",
        ),
        (
            lambda: sf.events.Span(
                **event_envelope(),
                name="span",
                operation="op",
                start=NOW,
                end=NOW - timedelta(seconds=1),
            ),
            "cannot precede",
        ),
        (
            lambda: sf.events.Span(
                **event_envelope(),
                name="span",
                operation="op",
                start=NOW,
                status=cast(Any, "bad"),
            ),
            "status",
        ),
        (
            lambda: sf.events.Span(
                **event_envelope(),
                name="span",
                operation="op",
                start=NOW,
                provider=" ",
            ),
            "provider",
        ),
        (
            lambda: sf.events.Usage(
                **event_envelope(),
                scope=cast(Any, "bad"),
                provider="p",
                model="m",
                pricing_version="v",
            ),
            "scope",
        ),
        (
            lambda: sf.events.TerminationError(
                code="code",
                message="message",
                permanent=cast(Any, "no"),
            ),
            "boolean",
        ),
        (
            lambda: sf.events.Terminated(
                **event_envelope(),
                status=cast(Any, "unknown"),
            ),
            "status",
        ),
    ],
)
def test_event_values_reject_invalid_state(factory: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()
