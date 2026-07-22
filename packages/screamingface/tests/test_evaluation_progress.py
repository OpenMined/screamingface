"""Notebook and terminal contracts for synchronous evaluation progress."""

from __future__ import annotations

import io

import pytest
from IPython import display as ipython_display
from ipywidgets import HTML

from screamingface import _progress


def test_progress_html_is_safe_accessible_and_uses_shared_visual_tokens() -> None:
    state = _progress._State(
        "fusion<script>",
        "gpqa@1",
        "running",
        "Running cases",
        completed=2,
        total=5,
    )

    html = _progress.progress_html(state)

    assert "fusion&lt;script&gt;" in html
    assert "fusion<script>" not in html
    assert "class='sf-ui sf-progress'" in html
    assert "role='progressbar'" in html
    assert "aria-valuemax='5'" in html
    assert "aria-valuenow='2'" in html
    assert "width:40.00%" in html
    assert "data:image/gif;base64," in html
    assert "class='sf-progress__loader running'" in html
    assert "sf-progress__loader-fallback'>😱" in html
    assert "prefers-reduced-motion:reduce" in html
    assert ".jp-mod-theme-dark .sf-ui" in html
    assert "border-radius" not in html
    assert "box-shadow" not in html
    assert "gradient" not in html


def test_forced_terminal_progress_is_concise_and_auto_progress_can_stay_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_progress, "_in_notebook", lambda: False)
    output = io.StringIO()
    monkeypatch.setattr(_progress.sys, "stderr", output)

    visible = _progress.Progress("frontier", "gpqa@1", True)
    visible.stage("running", "Running cases", total=2)
    visible.advance()
    visible.finish()

    silent = _progress.Progress("frontier", "gpqa@1", None)
    silent.stage("running", "Running cases", total=2)
    silent.advance(2)
    silent.finish()

    rendered = output.getvalue()
    assert "😱 frontier · gpqa@1 · Running cases 1/2" in rendered
    assert rendered.count("frontier · gpqa@1 · Complete 2/2") == 1


def test_notebook_progress_uses_live_widget_updates_and_keeps_completed_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[object] = []
    monkeypatch.setattr(ipython_display, "display", shown.append)
    monkeypatch.setattr(_progress, "_in_notebook", lambda: True)

    progress = _progress.Progress("frontier", "gpqa@1", None)
    progress.stage("running", "Running cases", total=2)

    assert len(shown) == 1
    widget = shown[0]
    assert isinstance(widget, HTML)
    assert "Running cases" in widget.value
    assert "0/2" in widget.value

    progress.advance()
    assert "1/2" in widget.value

    progress.finish()
    assert "class='sf-progress__status complete'" in widget.value
    assert "class='sf-progress__loader complete'" in widget.value
    assert "Complete" in widget.value
    assert "2/2" in widget.value


def test_progress_setting_is_strict() -> None:
    with pytest.raises(TypeError, match="True, False, or None"):
        _progress.Progress("frontier", "gpqa@1", "yes")  # type: ignore[arg-type]


def test_operation_progress_tracks_concurrency_counts_failures_history_and_elapsed() -> None:
    progress = _progress.Progress("16 candidates", "draco-lite@1", False)
    progress.stage("running", "Executing shared graph", total=16)
    progress.operation(
        "model",
        "started",
        "Running opus",
        operation_id="case-1:model:opus",
    )
    progress.operation(
        "model",
        "started",
        "Running gpt",
        operation_id="case-1:model:gpt",
    )
    progress.elapsed(42.0)
    progress.operation(
        "model",
        "completed",
        "Completed opus",
        operation_id="case-1:model:opus",
    )
    progress.operation(
        "model",
        "failed",
        "Failed gpt <upstream>",
        operation_id="case-1:model:gpt",
    )

    model = next(value for value in progress._state.operations if value.stage == "model")
    assert (model.started, model.completed, model.failed) == (2, 1, 1)
    assert progress._state.active == ()
    assert progress._state.elapsed_seconds == 42.0
    assert [value.status for value in progress._state.recent] == ["failed", "completed"]

    html = _progress.progress_html(progress._state)
    assert "Models" in html
    assert "1 ok" in html
    assert "1 failed" in html
    assert "42s" in html
    assert "Failed gpt &lt;upstream&gt;" in html
    assert "Operation-level progress" in html

    progress.partial("5/16 candidates scored", completed=5, total=16)
    assert progress._state.stage == "partial"
    assert "sf-progress__status partial" in _progress.progress_html(progress._state)


def test_operation_progress_distinguishes_unavailable_from_failed() -> None:
    progress = _progress.Progress("16 candidates", "draco-lite@1", False)
    progress.operation(
        "grading",
        "skipped",
        "Scoring unavailable for gpt",
        operation_id="case-1:grading:gpt",
    )
    progress.operation(
        "candidate",
        "skipped",
        "Unavailable gpt (0/1 cases scored)",
        operation_id="candidate:gpt",
    )

    html = _progress.progress_html(progress._state)
    assert "Scoring" in html
    assert "Results" in html
    assert html.count("1 unavailable") == 2
    assert "Scoring unavailable for gpt" in html
    assert "–</span>" in html
    assert "1 failed" not in html
