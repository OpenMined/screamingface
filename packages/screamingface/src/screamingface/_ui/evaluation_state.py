"""Accumulated view of one Evaluation, folded from public Events only.

Deliberately free of ipywidgets and of wall-clock reads: every number here is derived
from Events the Engine actually sent, so the panel can never show a figure the run did
not produce, and the fold stays directly testable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from screamingface.events import Event, Span, Started, Terminated, Usage

# A candidate is one Engine run, so terminal Events are the only honest completion
# signal — model Spans fire many times per candidate and cannot stand in for it.
_TERMINAL_ORDER = ("failed", "timed_out", "stopped", "succeeded")


@dataclass(slots=True)
class _EvaluationProgress:
    """Running totals for one `evaluate()` call."""

    total_candidates: int | None = None
    completed: int = 0
    terminal_counts: dict[str, int] = field(default_factory=dict)
    model_calls: int = 0
    failed_calls: int = 0
    refusals: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    have_tokens: bool = False
    cost_usd: Decimal | None = None
    first_at: datetime | None = None
    latest_at: datetime | None = None
    activity: str | None = None
    error: str | None = None
    #: Newest-first ring of recent Events, so the panel can show work happening rather
    #: than a single frozen "last thing". Bounded: a long run emits thousands.
    feed: deque[tuple[float, str, str]] = field(default_factory=lambda: deque(maxlen=40))

    def observe(self, event: Event) -> None:
        self._stamp(event.timestamp)
        if isinstance(event, Started):
            self.activity = "Run started"
            self._note(event, "start", "run started")
        elif isinstance(event, Span):
            self._observe_span(event)
        elif isinstance(event, Usage):
            self._observe_usage(event)
        elif isinstance(event, Terminated):
            self._observe_terminated(event)

    @property
    def running(self) -> bool:
        return not self.finished

    @property
    def finished(self) -> bool:
        """True once every candidate has reported a terminal Event."""

        return self.total_candidates is not None and self.completed >= self.total_candidates

    @property
    def status(self) -> str:
        """Worst terminal status seen, or 'running' while work is outstanding."""

        if not self.finished:
            return "running"
        for name in _TERMINAL_ORDER:
            if self.terminal_counts.get(name):
                return name
        return "succeeded"

    @property
    def fraction(self) -> float | None:
        """Completed share of candidates, or None when the total is unknown."""

        if not self.total_candidates:
            return None
        return min(1.0, self.completed / self.total_candidates)

    @property
    def elapsed_seconds(self) -> float | None:
        if self.first_at is None or self.latest_at is None:
            return None
        return max(0.0, (self.latest_at - self.first_at).total_seconds())

    def _note(self, event: Event, kind: str, text: str) -> None:
        offset = 0.0
        if self.first_at is not None:
            offset = max(0.0, (event.timestamp - self.first_at).total_seconds())
        self.feed.appendleft((offset, kind, text))

    def _stamp(self, moment: datetime) -> None:
        if self.first_at is None or moment < self.first_at:
            self.first_at = moment
        if self.latest_at is None or moment > self.latest_at:
            self.latest_at = moment

    def _observe_span(self, event: Span) -> None:
        # Structural URL4 spans carry no request_model; only paid model work counts.
        if event.request_model is None:
            return
        self.model_calls += 1
        if event.status == "error":
            self.failed_calls += 1
        if event.refusal is not None:
            self.refusals += 1
        if event.input_tokens is not None:
            self.input_tokens += event.input_tokens
            self.have_tokens = True
        if event.output_tokens is not None:
            self.output_tokens += event.output_tokens
            self.have_tokens = True
        self.activity = event.request_model
        self._note(event, "error" if event.status == "error" else "model", _span_text(event))

    def _observe_usage(self, event: Usage) -> None:
        # 'subtree' repeats what its children already reported — summing both double counts.
        if event.scope != "self":
            return
        amount = event.usage.cost_usd
        if amount is None:
            return
        self.cost_usd = amount if self.cost_usd is None else self.cost_usd + amount

    def _observe_terminated(self, event: Terminated) -> None:
        self.completed += 1
        self.terminal_counts[event.status] = self.terminal_counts.get(event.status, 0) + 1
        if event.error is not None and self.error is None:
            self.error = event.error.message
        self.activity = f"Run {event.status.replace('_', ' ')}"
        kind = "done" if event.status == "succeeded" else "error"
        self._note(event, kind, f"run {event.status.replace('_', ' ')}")


def _span_text(event: Span) -> str:
    """One model call, summarised the way the text observer already words it."""

    parts = [str(event.request_model)]
    if event.refusal is not None:
        parts.append("refused")
    elif event.status == "error":
        parts.append("failed")
    if event.start is not None and event.end is not None:
        parts.append(f"{(event.end - event.start).total_seconds():.1f}s")
    if event.input_tokens is not None or event.output_tokens is not None:
        parts.append(f"{event.input_tokens or 0:,}/{event.output_tokens or 0:,} tok")
    return " · ".join(parts)


__all__: list[str] = []
