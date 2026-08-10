from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import screamingface as sf


def envelope() -> dict[str, Any]:
    return {
        "id": "event_1",
        "run_id": "run_1",
        "sequence": 1,
        "timestamp": datetime(2026, 7, 25, 16, 0, tzinfo=UTC),
        "source": "/trace/run_1/node/op_1",
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }


def test_started_is_a_typed_public_event() -> None:
    event = sf.events.Started(**envelope(), url4="(@)!'hello'")

    assert isinstance(event, sf.Event)
    assert event.kind == "started"
    assert event.run_id == "run_1"
    assert event.sequence == 1
    assert event.url4 == "(@)!'hello'"


def test_usage_event_keeps_taxonomy_and_accounting_separate() -> None:
    event = sf.events.Usage(
        **envelope(),
        scope="subtree",
        provider="openrouter",
        model="anthropic/claude-opus-4.8",
        pricing_version="2026-07-25",
        usage=sf.Usage(input_tokens=10, output_tokens=2, cost_usd="0.04"),
    )

    assert event.kind == "usage"
    assert event.scope == "subtree"
    assert event.usage.cost_usd is not None
    assert str(event.usage.cost_usd) == "0.04"


def test_event_sequence_must_be_positive() -> None:
    values = envelope()
    values["sequence"] = 0

    with pytest.raises(ValueError, match="positive integer"):
        sf.events.Started(**values, url4="(@)!'hello'")


def test_terminated_preserves_structured_engine_failure() -> None:
    error = sf.events.TerminationError(
        code="gateway_timeout",
        message="The model timed out.",
        permanent=False,
    )
    event = sf.events.Terminated(**envelope(), status="failed", error=error)

    assert event.kind == "terminated"
    assert event.error is error


def test_succeeded_termination_cannot_carry_an_error() -> None:
    with pytest.raises(ValueError, match="cannot contain an error"):
        sf.events.Terminated(
            **envelope(),
            status="succeeded",
            error=sf.events.TerminationError(code="bad", message="bad", permanent=True),
        )
