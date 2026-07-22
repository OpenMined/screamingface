"""Live, dependency-light progress for synchronous notebook evaluation."""

from __future__ import annotations

import sys
from base64 import b64encode
from dataclasses import dataclass, replace
from functools import cache
from html import escape
from importlib.resources import files
from threading import RLock
from typing import Literal, Protocol

from screamingface._display import STYLE

type ProgressSetting = bool | None
type OperationStage = Literal["model", "synthesis", "grading", "candidate"]
type OperationStatus = Literal["started", "completed", "failed", "skipped"]
type ProgressStage = Literal[
    "checking",
    "running",
    "grading",
    "aggregating",
    "complete",
    "partial",
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
.sf-progress__elapsed{color:var(--sf-ink-3);font-weight:400;letter-spacing:0}
.sf-progress__status.complete{color:var(--sf-gain)}
.sf-progress__status.partial{color:var(--sf-blind)}
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
.sf-progress__fill.partial{background:var(--sf-blind)}
.sf-progress__fill.stopped{background:var(--sf-blind)}
.sf-progress__fill.failed{background:var(--sf-blind)}
.sf-progress__stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;
  margin-top:12px;background:var(--sf-line)}
.sf-progress__stat{min-width:0;padding:8px 10px;background:var(--sf-surface)}
.sf-progress__stat-label{color:var(--sf-ink-3);font:10px/1.3 "IBM Plex Mono",ui-monospace,
  monospace;letter-spacing:.06em;text-transform:uppercase}
.sf-progress__stat-value{margin-top:2px;font:600 13px/1.35 "IBM Plex Mono",ui-monospace,
  monospace;font-variant-numeric:tabular-nums}
.sf-progress__stat-failed{color:var(--sf-blind);font-weight:400}
.sf-progress__stat-skipped{color:var(--sf-ink-3);font-weight:400}
.sf-progress__section{margin-top:12px;padding-top:10px;border-top:1px solid var(--sf-line)}
.sf-progress__section-head{display:flex;justify-content:space-between;color:var(--sf-ink-3);
  font:10px/1.3 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.06em;
  text-transform:uppercase}
.sf-progress__events{display:grid;gap:5px;margin-top:7px}
.sf-progress__event{display:flex;gap:7px;align-items:baseline;min-width:0;color:var(--sf-ink-2);
  font-size:12px;line-height:1.35}
.sf-progress__event-mark{width:10px;flex:0 0 10px;color:var(--sf-ink-3)}
.sf-progress__event-mark.failed{color:var(--sf-blind)}
.sf-progress__event-mark.skipped{color:var(--sf-ink-3)}
.sf-progress__event-label{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sf-progress__foot{margin-top:10px;color:var(--sf-ink-3);font:10px/1.35 "IBM Plex Mono",
  ui-monospace,monospace}
@media (max-width:640px){.sf-progress__stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
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
    elapsed_seconds: float = 0.0
    operations: tuple[_OperationCount, ...] = ()
    active: tuple[_ActiveOperation, ...] = ()
    recent: tuple[_RecentOperation, ...] = ()


@dataclass(frozen=True, slots=True)
class _OperationCount:
    stage: OperationStage
    started: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(frozen=True, slots=True)
class _ActiveOperation:
    id: str
    stage: OperationStage
    label: str


@dataclass(frozen=True, slots=True)
class _RecentOperation:
    status: Literal["completed", "failed", "skipped"]
    label: str


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
        elapsed = f" · {_duration(state.elapsed_seconds)}" if state.elapsed_seconds else ""
        loader = "😱 " if state.stage in _ACTIVE_STAGES else ""
        line = f"{loader}{state.recipe_name} · {state.benchmark_id} · {state.label}{count}{elapsed}"
        padding = " " * max(0, self._last_length - len(line))
        ending = "\n" if state.stage in {"complete", "partial", "stopped", "failed"} else ""
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
        self._operation_counts: dict[OperationStage, list[int]] = {
            stage: [0, 0, 0, 0] for stage in ("model", "synthesis", "grading", "candidate")
        }
        self._active_operations: dict[str, _ActiveOperation] = {}
        self._recent_operations: list[_RecentOperation] = []
        self._anonymous_operation = 0
        self._backend: _Backend | None = None
        self._lock = RLock()

    def stage(self, stage: ProgressStage, label: str, *, total: int | None = None) -> None:
        with self._lock:
            self._state = replace(self._state, stage=stage, label=label, completed=0, total=total)
            self._render()

    def advance(self, count: int = 1) -> None:
        if count < 0:
            raise ValueError("progress advance must not be negative")
        with self._lock:
            total = self._state.total
            completed = self._state.completed + count
            if total is not None:
                completed = min(completed, total)
            self._state = replace(self._state, completed=completed, total=total)
            self._render()

    def observe(self, stage: ProgressStage, label: str) -> None:
        """Update a live stage label without losing completed case progress."""

        with self._lock:
            self._state = replace(self._state, stage=stage, label=label)
            self._render()

    def elapsed(self, seconds: float) -> None:
        """Refresh elapsed time while preserving operation and completion state."""

        if seconds < 0:
            raise ValueError("progress elapsed time must not be negative")
        with self._lock:
            self._state = replace(self._state, elapsed_seconds=seconds)
            self._render()

    def operation(
        self,
        stage: OperationStage,
        status: OperationStatus,
        label: str,
        *,
        operation_id: str | None,
    ) -> None:
        """Record one independently identifiable engine operation."""

        with self._lock:
            identity = operation_id
            if identity is None:
                if status == "started":
                    self._anonymous_operation += 1
                    identity = f"anonymous:{stage}:{self._anonymous_operation}"
                else:
                    identity = next(
                        (
                            key
                            for key, value in self._active_operations.items()
                            if value.stage == stage
                        ),
                        f"anonymous:{stage}:terminal:{self._anonymous_operation}",
                    )
            counts = self._operation_counts[stage]
            if status == "started":
                counts[0] += 1
                self._active_operations[identity] = _ActiveOperation(identity, stage, label)
            else:
                if counts[0] <= counts[1] + counts[2] + counts[3]:
                    counts[0] += 1
                terminal_index = {"completed": 1, "failed": 2, "skipped": 3}[status]
                counts[terminal_index] += 1
                self._active_operations.pop(identity, None)
                self._recent_operations.insert(0, _RecentOperation(status, label))
                del self._recent_operations[4:]
            display_stage: ProgressStage = "grading" if stage == "grading" else "running"
            self._state = replace(
                self._state,
                stage=display_stage,
                label=label,
                operations=self._operation_summary(),
                active=tuple(self._active_operations.values()),
                recent=tuple(self._recent_operations),
            )
            self._render()

    def finish(self, label: str = "Complete") -> None:
        total = self._state.total
        with self._lock:
            self._active_operations.clear()
            self._state = replace(
                self._state,
                stage="complete",
                label=label,
                completed=total or 0,
                total=total,
                active=(),
            )
            self._render()

    def fail(self, message: str) -> None:
        with self._lock:
            self._active_operations.clear()
            self._state = replace(self._state, stage="failed", label=message, active=())
            self._render()

    def stop(self, label: str, *, completed: int, total: int) -> None:
        if completed < 0 or total < 1 or completed > total:
            raise ValueError("stopped progress requires 0 <= completed <= total")
        with self._lock:
            self._active_operations.clear()
            self._state = replace(
                self._state,
                stage="stopped",
                label=label,
                completed=completed,
                total=total,
                active=(),
            )
            self._render()

    def partial(self, label: str, *, completed: int, total: int) -> None:
        """Finish with a usable report whose requested results are incomplete."""

        if completed < 0 or total < 1 or completed > total:
            raise ValueError("partial progress requires 0 <= completed <= total")
        with self._lock:
            self._active_operations.clear()
            self._state = replace(
                self._state,
                stage="partial",
                label=label,
                completed=completed,
                total=total,
                active=(),
            )
            self._render()

    def _operation_summary(self) -> tuple[_OperationCount, ...]:
        return tuple(
            _OperationCount(stage, *self._operation_counts[stage])
            for stage in ("model", "synthesis", "grading", "candidate")
        )

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
    status = escape(state.stage)
    if state.elapsed_seconds:
        status += (
            " <span class='sf-progress__elapsed'>· "
            f"{escape(_duration(state.elapsed_seconds))}</span>"
        )
    detail = _operation_details(state)
    return (
        f"{_PROGRESS_STYLE}<div class='sf-ui sf-progress' "
        "aria-label='ScreamingFace evaluation progress'>"
        "<div class='sf-progress__head'><div class='sf-progress__identity'>"
        f"<div class='sf-progress__title'>{escape(state.recipe_name)}</div>"
        f"<div class='sf-progress__benchmark'>{escape(state.benchmark_id)}</div></div>"
        f"<div class='sf-progress__status {state.stage}'>{status}</div></div>"
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
        f"</div>{detail}</div></div>"
    )


def _operation_details(state: _State) -> str:
    if not state.operations and not state.active and not state.recent:
        return ""
    counts = {value.stage: value for value in state.operations}
    stats = "".join(
        _operation_stat(label, counts.get(stage))
        for stage, label in (
            ("model", "Models"),
            ("synthesis", "Synthesis"),
            ("grading", "Scoring"),
            ("candidate", "Results"),
        )
    )
    active = _event_section(
        "Active",
        tuple(("active", value.label) for value in state.active),
        total=len(state.active),
    )
    recent = _event_section(
        "Recent",
        tuple((value.status, value.label) for value in state.recent),
    )
    return (
        f"<div class='sf-progress__stats'>{stats}</div>{active}{recent}"
        "<div class='sf-progress__foot'>Operation-level progress · model output appears "
        "when each call completes</div>"
    )


def _operation_stat(label: str, value: _OperationCount | None) -> str:
    started = 0 if value is None else value.started
    completed = 0 if value is None else value.completed
    failed = 0 if value is None else value.failed
    skipped = 0 if value is None else value.skipped
    terminal = completed + failed + skipped
    if failed == 0 and skipped == 0:
        value_text = f"{terminal}/{started}"
    else:
        success_word = "scored" if label == "Scoring" else ("ready" if label == "Results" else "ok")
        parts = [f"{completed} {success_word}"]
        if skipped:
            parts.append(f"<span class='sf-progress__stat-skipped'>· {skipped} unavailable</span>")
        if failed:
            parts.append(f"<span class='sf-progress__stat-failed'>· {failed} failed</span>")
        value_text = "".join(parts)
    return (
        "<div class='sf-progress__stat'>"
        f"<div class='sf-progress__stat-label'>{escape(label)}</div>"
        f"<div class='sf-progress__stat-value'>{value_text}</div></div>"
    )


def _event_section(
    title: str,
    events: tuple[tuple[str, str], ...],
    *,
    total: int | None = None,
) -> str:
    if not events:
        return ""
    visible = events[:3]
    count = len(events) if total is None else total
    rows = "".join(
        "<div class='sf-progress__event'>"
        f"<span class='sf-progress__event-mark {escape(status)}'>"
        f"{_event_mark(status)}</span>"
        f"<span class='sf-progress__event-label'>{escape(label)}</span></div>"
        for status, label in visible
    )
    remaining = count - len(visible)
    suffix = "" if remaining <= 0 else f"<span>+{remaining} more</span>"
    return (
        "<div class='sf-progress__section'>"
        f"<div class='sf-progress__section-head'><span>{escape(title)}</span>{suffix}</div>"
        f"<div class='sf-progress__events'>{rows}</div></div>"
    )


def _event_mark(status: str) -> str:
    return {"failed": "!", "skipped": "–", "active": "•"}.get(status, "✓")


def _duration(seconds: float) -> str:
    rounded = max(0, int(seconds))
    minutes, remainder = divmod(rounded, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}h {minutes:02d}m {remainder:02d}s"
    if minutes:
        return f"{minutes:d}m {remainder:02d}s"
    return f"{remainder:d}s"


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
