from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from typing import Any

import pytest

import screamingface as sf
from screamingface._progress import _message, _progress_observer
from screamingface.client import _async_event_observer, _sync_event_observer


def envelope() -> dict[str, Any]:
    return {
        "id": "event_1",
        "run_id": "run_1",
        "sequence": 1,
        "timestamp": datetime(2026, 7, 25, 16, 0, tzinfo=UTC),
        "source": "/trace/run_1/node/root",
    }


def test_progress_can_be_disabled_or_forced() -> None:
    stream = StringIO()

    assert _progress_observer(False, stream=stream) is None
    observer = _progress_observer(True, stream=stream)
    assert observer is not None

    observer(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert stream.getvalue() == "ScreamingFace · Run started\n"


def test_progress_messages_cover_meaningful_lifecycle_events() -> None:
    log = sf.events.Log(
        **envelope(),
        severity_number=9,
        severity_text="INFO",
        body="Grading case 1",
    )
    terminated = sf.events.Terminated(**envelope(), status="timed_out")
    usage = sf.events.Usage(
        **envelope(),
        scope="subtree",
        provider="openrouter",
        model="model",
        pricing_version="v1",
    )

    assert _message(log) == "Grading case 1"
    assert _message(terminated) == "Run timed out"
    assert _message(usage) is None


def test_sync_evaluate_combines_builtin_and_caller_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "screamingface._progress._progress_observer",
        lambda requested: lambda event: observed.append(("progress", event.kind)),
    )
    callback = _sync_event_observer(
        lambda event: observed.append(("caller", event.kind)),
        True,
    )
    assert callback is not None

    callback(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert observed == [("progress", "started"), ("caller", "started")]


@pytest.mark.asyncio
async def test_async_evaluate_combines_builtin_and_async_caller_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "screamingface._progress._progress_observer",
        lambda requested: lambda event: observed.append(("progress", event.kind)),
    )

    async def caller(event: sf.Event) -> None:
        observed.append(("caller", event.kind))

    callback = _async_event_observer(caller, True)
    assert callback is not None

    await callback(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert observed == [("progress", "started"), ("caller", "started")]
