"""Live, dependency-light progress for synchronous notebook evaluation."""

from __future__ import annotations

import sys
from base64 import b64encode
from dataclasses import dataclass
from functools import cache
from html import escape
from importlib.resources import files
from threading import RLock
from typing import Literal, Protocol

from screamingface._display import STYLE

type ProgressSetting = bool | None
type ProgressStage = Literal[
    "checking",
    "running",
    "grading",
    "aggregating",
    "complete",
    "stopped",
    "failed",
]

_ACTIVE_STAGES = {"checking", "running", "grading", "aggregating"}

_PROGRESS_STYLE = (
    STYLE
    + """<style>
.sf-progress{border:1px solid var(--sf-line-2)}
.sf-progress__head{height:48px;display:flex;align-items:center;gap:12px;padding:0 12px;
  border-bottom:1px solid var(--sf-line)}
.sf-progress__identity{min-width:0}
.sf-progress__title{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sf-progress__benchmark{color:var(--sf-ink-3);font:11px/1.4 "IBM Plex Mono",ui-monospace,
  monospace}
.sf-progress__status{margin-left:auto;color:var(--sf-ink-2);font:600 11px/1.4
  "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;
  white-space:nowrap}
.sf-progress__status.complete{color:var(--sf-gain)}
.sf-progress__status.stopped{color:var(--sf-blind)}
.sf-progress__status.failed{color:var(--sf-blind)}
.sf-progress__body{padding:12px}
.sf-progress__line{display:flex;justify-content:space-between;gap:12px;color:var(--sf-ink-2)}
.sf-progress__activity{display:flex;align-items:center;gap:8px;min-width:0}
.sf-progress__loader{width:20px;height:20px;display:inline-grid;place-items:center;flex:0 0 20px}
.sf-progress__loader.complete,.sf-progress__loader.stopped,.sf-progress__loader.failed{display:none}
.sf-progress__loader-image{grid-area:1/1;width:20px;height:20px;display:block;object-fit:contain}
.sf-progress__loader-fallback{grid-area:1/1;display:none;font-size:16px;line-height:1}
.sf-progress__count{color:var(--sf-ink-3);font:12px/1.4 "IBM Plex Mono",ui-monospace,
  monospace;font-variant-numeric:tabular-nums;white-space:nowrap}
.sf-progress__track{height:4px;margin-top:10px;background:var(--sf-surface-2);overflow:hidden}
.sf-progress__fill{height:100%;background:var(--sf-ink);transition:width .18s ease}
.sf-progress__fill.complete{background:var(--sf-gain)}
.sf-progress__fill.stopped{background:var(--sf-blind)}
.sf-progress__fill.failed{background:var(--sf-blind)}
@media (prefers-reduced-motion:reduce){
  .sf-progress__loader-image{display:none}
  .sf-progress__loader-fallback{display:inline}
}
</style>"""
)


@dataclass(frozen=True, slots=True)
class _State:
    recipe_name: str
    benchmark_id: str
    stage: ProgressStage
    label: str
    completed: int = 0
    total: int | None = None


class _Backend(Protocol):
    def update(self, state: _State) -> None: ...


class _NotebookBackend:
    def __init__(self, state: _State) -> None:
        from IPython.display import display
        from ipywidgets import HTML

        # WHY: widget comm messages are delivered while a synchronous VS Code/Jupyter cell is
        # busy. Display-id updates can be buffered by those frontends until the cell completes,
        # which makes paid model execution look completely opaque.
        self._widget = HTML(value=progress_html(state))
        display(self._widget)

    def update(self, state: _State) -> None:
        self._widget.value = progress_html(state)


class _TextBackend:
    def __init__(self, state: _State) -> None:
        self._last_length = 0
        self.update(state)

    def update(self, state: _State) -> None:
        count = "" if state.total is None else f" {state.completed}/{state.total}"
        loader = "😱 " if state.stage in _ACTIVE_STAGES else ""
        line = f"{loader}{state.recipe_name} · {state.benchmark_id} · {state.label}{count}"
        padding = " " * max(0, self._last_length - len(line))
        ending = "\n" if state.stage in {"complete", "stopped", "failed"} else ""
        print(f"\r{line}{padding}", end=ending, file=sys.stderr, flush=True)
        self._last_length = len(line)


class Progress:
    """Internal stage tracker shared by run, grade, and evaluate."""

    def __init__(
        self,
        recipe_name: str,
        benchmark_id: str,
        setting: ProgressSetting,
    ) -> None:
        _validate_setting(setting)
        self._enabled = _in_notebook() if setting is None else setting
        self._notebook = self._enabled and _in_notebook()
        self._state = _State(recipe_name, benchmark_id, "checking", "Checking requirements")
        self._backend: _Backend | None = None
        self._lock = RLock()

    def stage(self, stage: ProgressStage, label: str, *, total: int | None = None) -> None:
        with self._lock:
            self._state = _State(
                self._state.recipe_name,
                self._state.benchmark_id,
                stage,
                label,
                total=total,
            )
            self._render()

    def advance(self, count: int = 1) -> None:
        if count < 0:
            raise ValueError("progress advance must not be negative")
        with self._lock:
            total = self._state.total
            completed = self._state.completed + count
            if total is not None:
                completed = min(completed, total)
            self._state = _State(
                self._state.recipe_name,
                self._state.benchmark_id,
                self._state.stage,
                self._state.label,
                completed,
                total,
            )
            self._render()

    def observe(self, stage: ProgressStage, label: str) -> None:
        """Update a live stage label without losing completed case progress."""

        with self._lock:
            self._state = _State(
                self._state.recipe_name,
                self._state.benchmark_id,
                stage,
                label,
                self._state.completed,
                self._state.total,
            )
            self._render()

    def finish(self, label: str = "Complete") -> None:
        total = self._state.total
        with self._lock:
            self._state = _State(
                self._state.recipe_name,
                self._state.benchmark_id,
                "complete",
                label,
                total or 0,
                total,
            )
            self._render()

    def fail(self, message: str) -> None:
        with self._lock:
            self._state = _State(
                self._state.recipe_name,
                self._state.benchmark_id,
                "failed",
                message,
                self._state.completed,
                self._state.total,
            )
            self._render()

    def stop(self, label: str, *, completed: int, total: int) -> None:
        if completed < 0 or total < 1 or completed > total:
            raise ValueError("stopped progress requires 0 <= completed <= total")
        with self._lock:
            self._state = _State(
                self._state.recipe_name,
                self._state.benchmark_id,
                "stopped",
                label,
                completed,
                total,
            )
            self._render()

    def _render(self) -> None:
        if not self._enabled:
            return
        if self._backend is None:
            self._backend = (
                _NotebookBackend(self._state) if self._notebook else _TextBackend(self._state)
            )
            return
        self._backend.update(self._state)


def progress_html(state: _State) -> str:
    """Render one safe progress snapshot using the shared notebook visual system."""

    total = state.total
    completed = state.completed
    percent = (
        100.0
        if state.stage == "complete" and total is None
        else (0.0 if not total else min(100.0, completed / total * 100.0))
    )
    count = "" if total is None else f"{completed}/{total}"
    return (
        f"{_PROGRESS_STYLE}<div class='sf-ui sf-progress' "
        "aria-label='ScreamingFace evaluation progress'>"
        "<div class='sf-progress__head'><div class='sf-progress__identity'>"
        f"<div class='sf-progress__title'>{escape(state.recipe_name)}</div>"
        f"<div class='sf-progress__benchmark'>{escape(state.benchmark_id)}</div></div>"
        f"<div class='sf-progress__status {state.stage}'>{escape(state.stage)}</div></div>"
        "<div class='sf-progress__body'><div class='sf-progress__line'>"
        "<span class='sf-progress__activity'>"
        f"<span class='sf-progress__loader {state.stage}' aria-hidden='true'>"
        f"<img class='sf-progress__loader-image' src='{_loader_data_uri()}' alt=''>"
        "<span class='sf-progress__loader-fallback'>😱</span></span>"
        f"<span>{escape(state.label)}</span></span>"
        f"<span class='sf-progress__count'>{count}</span></div>"
        "<div class='sf-progress__track' role='progressbar' "
        f"aria-valuemin='0' aria-valuemax='{total or 0}' aria-valuenow='{completed}'>"
        f"<div class='sf-progress__fill {state.stage}' style='width:{percent:.2f}%'></div>"
        "</div></div></div>"
    )


@cache
def _loader_data_uri() -> str:
    payload = files("screamingface").joinpath("assets/scream-shaking.gif").read_bytes()
    return f"data:image/gif;base64,{b64encode(payload).decode('ascii')}"


def _validate_setting(setting: ProgressSetting) -> None:
    if setting is not None and not isinstance(setting, bool):
        raise TypeError("progress must be True, False, or None")


def _in_notebook() -> bool:
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        return False
    shell = get_ipython()
    return shell is not None and (
        shell.__class__.__name__ == "ZMQInteractiveShell"
        or getattr(shell, "kernel", None) is not None
    )


__all__ = ["Progress", "ProgressSetting", "progress_html"]
