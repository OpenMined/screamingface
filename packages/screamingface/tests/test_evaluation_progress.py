"""Notebook and terminal contracts for synchronous evaluation progress."""

from __future__ import annotations

import io

import pytest

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
    assert "frontier · gpqa@1 · Running cases 1/2" in rendered
    assert rendered.count("frontier · gpqa@1 · Complete 2/2") == 1


def test_progress_setting_is_strict() -> None:
    with pytest.raises(TypeError, match="True, False, or None"):
        _progress.Progress("frontier", "gpqa@1", "yes")  # type: ignore[arg-type]
