from __future__ import annotations

import sys
from datetime import UTC, datetime
from io import StringIO
from typing import Any

import pytest

import screamingface as sf
from screamingface._evaluation.progress import _message, _progress_observer
from screamingface._evaluation.runner import _async_event_observer, _sync_event_observer


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


def test_progress_defaults_on_inside_a_notebook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ipykernel", object())

    assert _progress_observer(None, stream=StringIO()) is not None


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


def test_progress_neutralizes_terminal_controls_and_multiline_log_spoofing() -> None:
    stream = StringIO()
    observer = _progress_observer(True, stream=stream)
    assert observer is not None

    observer(
        sf.events.Log(
            **envelope(),
            severity_number=9,
            severity_text="INFO",
            body="safe\x1b]0;forged-title\x07\rforged\nnext\tline",
        )
    )

    assert stream.getvalue() == ("ScreamingFace · safe ]0;forged-title forged next line\n")


def test_progress_hides_structural_spans_and_summarizes_model_completions() -> None:
    started = datetime(2026, 7, 25, 16, 0, tzinfo=UTC)
    structural = sf.events.Span(
        **envelope(),
        name="TextNode",
        operation="TextNode",
        start=started,
        end=started,
    )
    model = sf.events.Span(
        **envelope(),
        name="RelUrlNode",
        operation="RelUrlNode",
        start=started,
        end=datetime(2026, 7, 25, 16, 0, 4, 800000, tzinfo=UTC),
        provider="openrouter",
        request_model="openrouter/anthropic/claude-haiku-4.5",
        input_tokens=103,
        output_tokens=374,
        finish_reasons=("stop",),
    )

    assert _message(structural) is None
    assert _message(model) == (
        "Model completed · openrouter/anthropic/claude-haiku-4.5 · 4.8s · 103 in / 374 out · stop"
    )


def test_sync_evaluate_combines_builtin_and_caller_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "screamingface._evaluation.progress._progress_observer",
        lambda requested: lambda event: observed.append(("progress", event.kind)),
    )
    callback = _sync_event_observer(
        lambda event: observed.append(("caller", event.kind)),
        True,
    )
    assert callback is not None

    callback(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert observed == [("progress", "started"), ("caller", "started")]


def test_sync_builtin_progress_failure_does_not_block_the_caller_observer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def broken_progress(_event: sf.Event) -> None:
        raise OSError("stdout closed")

    monkeypatch.setattr(
        "screamingface._evaluation.progress._progress_observer",
        lambda requested: broken_progress,
    )
    callback = _sync_event_observer(lambda event: observed.append(event.kind), True)
    assert callback is not None

    callback(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert observed == ["started"]


@pytest.mark.asyncio
async def test_async_evaluate_combines_builtin_and_async_caller_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "screamingface._evaluation.progress._progress_observer",
        lambda requested: lambda event: observed.append(("progress", event.kind)),
    )

    async def caller(event: sf.Event) -> None:
        observed.append(("caller", event.kind))

    callback = _async_event_observer(caller, True)
    assert callback is not None

    await callback(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert observed == [("progress", "started"), ("caller", "started")]


@pytest.mark.asyncio
async def test_async_builtin_progress_failure_does_not_block_the_caller_observer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def broken_progress(_event: sf.Event) -> None:
        raise OSError("stdout closed")

    monkeypatch.setattr(
        "screamingface._evaluation.progress._progress_observer",
        lambda requested: broken_progress,
    )

    async def caller(event: sf.Event) -> None:
        observed.append(event.kind)

    callback = _async_event_observer(caller, True)
    assert callback is not None

    await callback(sf.events.Started(**envelope(), url4="(@)!'hello'"))

    assert observed == ["started"]
