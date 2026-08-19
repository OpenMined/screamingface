"""Live notebook panel for a running `evaluate()`, driven by public Events."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from decimal import Decimal
from html import escape
from typing import Any

from screamingface._ui.evaluation_state import _CandidateCaseProgress, _EvaluationProgress
from screamingface._ui.style import FUSION_GRADIENT, STYLE
from screamingface.events import Event

_STYLE = (
    STYLE
    + f"""<style>
.sf-eval{{border:0;border-radius:0;padding:4px 14px 14px}}
.sf-eval__title{{font-size:20px;font-weight:700;line-height:1.2;letter-spacing:-.01em}}
.sf-eval__sub{{font-size:13px;color:var(--sf-ink-2);margin-top:3px}}
/* the track is a well; the fill carries the fusion gradient — square, no radius */
.sf-eval__track{{position:relative;height:8px;background:var(--sf-line);overflow:hidden;
  margin-top:14px}}
.sf-eval__fill{{display:block;height:100%;background-repeat:no-repeat;
  background-position:center;background-size:100% 100%;background-image:{FUSION_GRADIENT};
  transition:width .35s ease-out}}
/* unknown denominator: never fake a fraction — sweep a short band to show liveness */
.sf-eval__fill--sweep{{width:38%;background-size:100% 100%;
  animation:sf-eval-sweep 1.5s ease-in-out infinite}}
@keyframes sf-eval-sweep{{0%{{transform:translateX(-100%)}}100%{{transform:translateX(365%)}}}}
@media(prefers-reduced-motion:reduce){{.sf-eval__fill--sweep{{animation:none;width:100%}}}}
.sf-eval__meta{{display:flex;align-items:center;justify-content:space-between;gap:12px;
  margin-top:8px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  color:var(--sf-ink-2)}}
.sf-eval__state{{display:inline-flex;align-items:center;gap:8px;white-space:nowrap}}
.sf-eval__state .sq{{flex:0 0 auto;width:9px;height:9px;background:var(--sf-ink-3)}}
.sf-eval__state.running .sq{{background:var(--sf-accent)}}
.sf-eval__state.succeeded .sq{{background:var(--sf-success-solid)}}
.sf-eval__state.incomplete .sq{{background:var(--sf-warning-solid)}}
.sf-eval__state.failed .sq,.sf-eval__state.timed_out .sq,
.sf-eval__state.stopped .sq{{background:var(--sf-blind)}}
/* stat table: hairline cells, mono figures, tabular so digits stop jittering as they tick */
.sf-eval__stats{{display:grid;grid-template-columns:repeat(3,1fr);
  border:1px solid var(--sf-line);margin-top:14px}}
.sf-eval__stat{{padding:10px 12px;border-right:1px solid var(--sf-line);min-width:0}}
.sf-eval__stat:last-child{{border-right:0}}
.sf-eval__stat-k{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  text-transform:uppercase;letter-spacing:.08em;color:var(--sf-ink-3)}}
.sf-eval__stat-v{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:18px;
  margin-top:3px;font-variant-numeric:tabular-nums;color:var(--sf-ink);
  overflow:hidden;text-overflow:ellipsis}}
.sf-eval__act{{margin-top:10px;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:12px;color:var(--sf-ink-3);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}}
/* pre-flight spend disclosure: calm and present, never a red banner (OME-845) */
.sf-eval__note{{margin-top:8px;padding:7px 10px;border:1px solid var(--sf-line);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;
  color:var(--sf-ink-2);line-height:1.5}}
.sf-eval__candidates{{margin-top:14px;border:1px solid var(--sf-line)}}
.sf-eval__candidate{{padding:10px 12px;border-bottom:1px solid var(--sf-line)}}
.sf-eval__candidate:last-child{{border-bottom:0}}
.sf-eval__candidate-head{{display:flex;align-items:baseline;justify-content:space-between;
  gap:12px;font-family:"IBM Plex Mono",ui-monospace,monospace}}
.sf-eval__candidate-name{{font-weight:600;color:var(--sf-ink);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}}
.sf-eval__candidate-score{{color:var(--sf-accent);white-space:nowrap;
  font-variant-numeric:tabular-nums}}
.sf-eval__case-track{{height:8px;margin-top:8px;background:var(--sf-line);
  overflow:hidden}}
.sf-eval__case-fill{{display:block;height:100%;background-repeat:no-repeat;
  background-position:right center;background-image:{FUSION_GRADIENT};
  transition:width .35s ease-out}}
.sf-eval__candidate-meta{{display:flex;justify-content:space-between;gap:12px;margin-top:6px;
  color:var(--sf-ink-3);font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;font-variant-numeric:tabular-nums}}
/* the feed: newest first, fixed height — proof of work, not a transcript */
.sf-eval__feed{{margin-top:12px;border:1px solid var(--sf-line);max-height:132px;
  overflow:auto}}
.sf-eval__ev{{display:flex;gap:10px;align-items:baseline;padding:5px 10px;
  border-bottom:1px solid var(--sf-line);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px}}
.sf-eval__ev:last-child{{border-bottom:0}}
.sf-eval__ev-t{{flex:0 0 auto;color:var(--sf-ink-3);font-variant-numeric:tabular-nums}}
.sf-eval__ev-m{{flex:1 1 auto;color:var(--sf-ink-2);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}}
.sf-eval__ev--error .sf-eval__ev-m{{color:var(--sf-blind)}}
.sf-eval__ev--done .sf-eval__ev-m,.sf-eval__ev--start .sf-eval__ev-m{{color:var(--sf-ink)}}
.sf-eval__err{{margin-top:10px;padding:8px 10px;border-left:2px solid var(--sf-blind);
  background:var(--sf-blind-bg);color:var(--sf-blind);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;white-space:pre-wrap}}
@media(max-width:680px){{.sf-eval__stats{{grid-template-columns:1fr}}
  .sf-eval__stat{{border-right:0;border-bottom:1px solid var(--sf-line)}}
  .sf-eval__stat:last-child{{border-bottom:0}}}}
</style>"""
)


def evaluation_panel_html(
    progress: _EvaluationProgress,
    benchmark: str | None = None,
    elapsed: float | None = None,
    check_disclosure: str | None = None,
) -> str:
    """Render the whole panel for the progress fold's current state.

    `elapsed` lets a live view pass wall-clock seconds. Without it the panel falls back to
    the span between the first and last Event, which is correct for a finished run but
    freezes between Events while one is still in flight.

    `check_disclosure` is the paid-check-call ceiling text; when the panel renders it,
    the Python warning it replaces stays suppressed (OME-845).
    """

    return (
        f"{_STYLE}<div class='sf-ui sf-eval' role='status' aria-live='polite' "
        "aria-label='ScreamingFace evaluation progress'>"
        f"{_head_html(progress, benchmark)}"
        f"{_bar_html(progress)}"
        f"{_meta_html(progress, elapsed)}"
        f"{_activity_html(progress)}"
        f"{_note_html(check_disclosure)}"
        f"{_candidate_progress_html(progress)}"
        f"{_stats_html(progress)}"
        f"{_feed_html(progress)}"
        f"{_error_html(progress)}</div>"
    )


def _head_html(progress: _EvaluationProgress, benchmark: str | None) -> str:
    title = "Evaluation complete" if progress.finished else "Evaluating"
    sub = f"Benchmark · {escape(benchmark)}" if benchmark else "Live run status"
    return f"<div class='sf-eval__title'>{title}</div><div class='sf-eval__sub'>{sub}</div>"


def _bar_html(progress: _EvaluationProgress) -> str:
    if progress.has_case_progress:
        return ""
    track = "sf-eval__track"
    fraction = progress.fraction
    if fraction is None:
        # No honest denominator — show liveness, not a made-up percentage.
        fill = "<span class='sf-eval__fill sf-eval__fill--sweep'></span>"
        return f"<div class='{track}'>{fill}</div>"
    percent = fraction * 100
    fill = f"<span class='sf-eval__fill' style='width:{percent:.1f}%'></span>"
    return f"<div class='{track}'>{fill}</div>"


def _meta_html(progress: _EvaluationProgress, elapsed: float | None = None) -> str:
    left = _candidate_text(progress)
    if elapsed is None:
        elapsed = progress.elapsed_seconds
    if elapsed is not None:
        left = f"{left} · {_duration(elapsed)}"
    status = progress.status
    return (
        f"<div class='sf-eval__meta'><span>{escape(left)}</span>"
        f"<span class='sf-eval__state {status}'><i class='sq'></i>"
        f"{escape(status.replace('_', ' '))}</span></div>"
    )


def _candidate_text(progress: _EvaluationProgress) -> str:
    total = progress.total_candidates
    if not total:
        return f"{progress.completed} done"
    noun = "candidate" if total == 1 else "candidates"
    return f"{progress.completed}/{total} {noun}"


def _activity_html(progress: _EvaluationProgress) -> str:
    activity = progress.activity or "Starting evaluation"
    return f"<div class='sf-eval__act'>phase · {escape(activity)}</div>"


def _note_html(check_disclosure: str | None) -> str:
    if check_disclosure is None:
        return ""
    return f"<div class='sf-eval__note'>check surface · {escape(check_disclosure)}</div>"


def _candidate_progress_html(progress: _EvaluationProgress) -> str:
    if not progress.has_case_progress and not progress.candidate_case_progress:
        return ""
    ordered_names = tuple(dict.fromkeys(progress.candidate_names_by_url.values()))
    values = tuple(_candidate_progress_value(progress, name) for name in ordered_names)
    seen = {value.name for value in values}
    values += tuple(
        value for name, value in progress.candidate_case_progress.items() if name not in seen
    )
    rows = "".join(_candidate_progress_row(value) for value in values)
    return f"<div class='sf-eval__candidates'>{rows}</div>"


def _candidate_progress_value(
    progress: _EvaluationProgress,
    name: str,
) -> _CandidateCaseProgress:
    existing = progress.candidate_case_progress.get(name)
    if existing is not None:
        return existing
    if progress.case_count is None:
        raise ValueError("Candidate Case progress requires a selected Case count")
    return _CandidateCaseProgress(
        name=name,
        total=progress.case_count,
        queued=progress.case_count,
        running_candidate=0,
        grading=0,
        complete=0,
        scored=0,
        coverage=0.0,
        score=None,
    )


def _candidate_progress_row(value: _CandidateCaseProgress) -> str:
    total = value.total
    complete_width = value.complete / total * 100
    score = _candidate_score_text(value)
    coverage = f"{value.coverage * 100:.1f}%"
    background_size = 100 if complete_width == 0 else 10_000 / complete_width
    fill = (
        f"<span class='sf-eval__case-fill' style='width:{complete_width:.3f}%;"
        f"background-size:{background_size:.1f}% 100%'></span>"
    )
    stages = _candidate_stage_text(value)
    return (
        "<div class='sf-eval__candidate'>"
        "<div class='sf-eval__candidate-head'>"
        f"<span class='sf-eval__candidate-name'>{escape(value.name)}</span>"
        f"<span class='sf-eval__candidate-score'>{escape(score)}</span>"
        "</div>"
        f"<div class='sf-eval__case-track'>{fill}</div>"
        "<div class='sf-eval__candidate-meta'>"
        f"<span>{value.complete}/{total} complete · {escape(stages)} · "
        f"{value.scored} scored</span>"
        f"<span>coverage · {coverage}</span>"
        "</div></div>"
    )


def _candidate_score_text(value: _CandidateCaseProgress) -> str:
    if value.score is not None:
        label = "score" if value.complete == value.total else "score so far"
        return f"{label} · {value.score:.6g}"
    if value.complete == value.total:
        return "score unavailable"
    state = "grading in progress" if value.grading else "awaiting first grade"
    return f"score · {state}"


def _candidate_stage_text(value: _CandidateCaseProgress) -> str:
    parts: list[str] = []
    if value.running_candidate:
        parts.append(f"{value.running_candidate} running Candidate")
    if value.grading:
        parts.append(f"{value.grading} grading")
    if value.queued:
        parts.append(f"{value.queued} queued")
    return " · ".join(parts) or "all Cases finished"


def _stats_html(progress: _EvaluationProgress) -> str:
    calls = "—" if progress.model_calls == 0 else f"{progress.model_calls:,}"
    if progress.failed_calls:
        calls = f"{calls} · {progress.failed_calls} failed"
    # The direction lives in the label so the figures stay on one line at panel width.
    tokens = (
        f"{_compact(progress.input_tokens)} / {_compact(progress.output_tokens)}"
        if progress.have_tokens
        else "—"
    )
    cost = "—" if progress.cost_usd is None else _money(progress.cost_usd)
    cells = (
        ("model calls", calls),
        ("tokens in / out", tokens),
        ("cost", cost),
    )
    body = "".join(
        f"<div class='sf-eval__stat'><div class='sf-eval__stat-k'>{escape(key)}</div>"
        f"<div class='sf-eval__stat-v'>{escape(value)}</div></div>"
        for key, value in cells
    )
    return f"<div class='sf-eval__stats'>{body}</div>"


def _feed_html(progress: _EvaluationProgress, limit: int = 12) -> str:
    """Recent Events, newest first — the panel's proof that work is happening."""

    if not progress.feed:
        return ""
    rows = "".join(
        f"<div class='sf-eval__ev sf-eval__ev--{escape(kind)}'>"
        f"<span class='sf-eval__ev-t'>{_offset(offset)}</span>"
        f"<span class='sf-eval__ev-m'>{escape(text)}</span></div>"
        for offset, kind, text in list(progress.feed)[:limit]
    )
    return f"<div class='sf-eval__feed'>{rows}</div>"


def _offset(seconds: float) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes:d}:{remainder:02d}"


def _error_html(progress: _EvaluationProgress) -> str:
    if progress.error is None:
        return ""
    return f"<div class='sf-eval__err' role='alert'>{escape(progress.error)}</div>"


def _compact(value: int) -> str:
    if value < 1_000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1_000:.1f}k"
    return f"{value / 1_000_000:.1f}M"


def _money(value: Decimal) -> str:
    if value != 0 and abs(value) < Decimal("0.01"):
        return f"${value:.4f}"
    return f"${value:,.2f}"


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {remainder:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class _NotebookEvaluationView:
    """ipywidgets shell: folds Events into state and repaints one HTML widget.

    Events arrive only when the Engine has something to say, and a single model call can
    run for minutes. Repainting solely on Events would leave the panel frozen for that
    whole stretch — indistinguishable from a hang — so a background ticker repaints on a
    fixed cadence and the clock is read from a monotonic source rather than Event stamps.
    """

    #: Repaint cadence while work is outstanding. One second reads as a live clock
    #: without flooding the notebook comm channel.
    _TICK_SECONDS = 1.0
    #: Backstop for a run that is interrupted before any terminal Event: the ticker is a
    #: daemon, but this stops it spinning for the life of a long-lived kernel.
    _MAX_TICK_SECONDS = 6 * 60 * 60

    def __init__(
        self,
        total_candidates: int | None = None,
        benchmark: str | None = None,
        case_count: int | None = None,
        candidate_models: tuple[str, ...] = (),
        candidate_urls: tuple[str, ...] = (),
        candidate_names: tuple[str, ...] = (),
        *,
        check_disclosure: str | None = None,
        clock: Callable[[], float] | None = None,
        tick: bool = True,
    ) -> None:
        import ipywidgets as widgets  # noqa: PLC0415 - optional notebook extra

        self._progress = _EvaluationProgress(
            total_candidates=total_candidates,
            case_count=case_count,
            candidate_models=frozenset(candidate_models),
            candidate_urls=frozenset(candidate_urls),
            candidate_names_by_url=_candidate_names(candidate_urls, candidate_names),
        )
        self._benchmark = benchmark
        self._check_disclosure = check_disclosure
        self._clock = time.monotonic if clock is None else clock
        self._started = self._clock()
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._html: Any = widgets.HTML(value=self._render())
        self._shown = False
        self._show()
        if tick:
            self._ticker = threading.Thread(
                target=self._tick_loop,
                name="screamingface-progress",
                daemon=True,
            )
            self._ticker.start()

    def __call__(self, event: Event) -> None:
        with self._lock:
            self._progress.observe(event, elapsed_seconds=self._clock() - self._started)
            finished = self._progress.finished
            self._html.value = self._render()
        if finished:
            self._done.set()

    def close(self) -> None:
        """Stop repainting and remove a live panel whose Evaluation raised."""

        self._done.set()
        self._html.close()

    def _render(self) -> str:
        # A finished run reports the span it actually took; a live one reports wall clock.
        elapsed = None if self._progress.finished else self._clock() - self._started
        return evaluation_panel_html(
            self._progress, self._benchmark, elapsed, self._check_disclosure
        )

    def _tick_loop(self) -> None:
        deadline = self._started + self._MAX_TICK_SECONDS
        while not self._done.wait(self._TICK_SECONDS):
            if self._clock() >= deadline:
                return
            try:
                with self._lock:
                    if self._progress.finished:
                        return
                    self._html.value = self._render()
            except Exception:
                # Progress is decorative: a dead comm or a closed widget must never
                # surface on this thread, and must not keep the loop spinning.
                return

    def _show(self) -> None:
        if self._shown:
            return
        from IPython.display import display  # noqa: PLC0415 - optional notebook extra

        display(self._html)
        self._shown = True


def _candidate_names(
    candidate_urls: tuple[str, ...], candidate_names: tuple[str, ...]
) -> dict[str, str]:
    if len(candidate_names) != len(candidate_urls):
        raise ValueError("Candidate progress names must match Candidate URLs")
    return dict(zip(candidate_urls, candidate_names, strict=True))


__all__: list[str] = []
