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
from typing import cast

from screamingface.events import Event, Log, Span, Started, Terminated, Usage

# A candidate is one Engine run, so terminal Events are the only honest completion
# signal — model Spans fire many times per candidate and cannot stand in for it.
_TERMINAL_ORDER = ("failed", "timed_out", "stopped", "succeeded")

# WHY a prefix rather than a fixed key list: the gateway owns the reason vocabulary and publishes
# one attribute per reason it saw. INVARIANT: the `cache.bypasses` total does not start with this
# prefix, so the total can never be harvested as a reason bucket.
_BYPASS_REASON_PREFIX = "cache.bypass."

UNSTATED_BYPASS_REASON = "unstated"
"""The Engine's bucket for a bypass that named no reason. Kept distinct from its `other` bucket:
`other` is a cardinality overflow, this is an absent value, and merging them would erase which."""


@dataclass(slots=True)
class _EvaluationProgress:
    """Running totals for one `evaluate()` call."""

    total_candidates: int | None = None
    candidate_models: frozenset[str] = field(default_factory=frozenset)
    candidate_urls: frozenset[str] = field(default_factory=frozenset)
    root_sources: set[str] = field(default_factory=set)
    cache_counts: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    cache_bypass_reasons: dict[str, dict[str, int]] = field(default_factory=dict)
    completed: int = 0
    terminal_counts: dict[str, int] = field(default_factory=dict)
    model_calls: int = 0
    candidate_calls: int = 0
    benchmark_calls: int = 0
    failed_calls: int = 0
    refusals: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    have_tokens: bool = False
    cost_usd: Decimal | None = None
    first_at: datetime | None = None
    latest_at: datetime | None = None
    arrival_elapsed_seconds: float | None = None
    activity: str | None = None
    error: str | None = None
    evaluation_started: bool = False
    #: Newest-first ring of recent Events, so the panel can show work happening rather
    #: than a single frozen "last thing". Bounded: a long run emits thousands.
    feed: deque[tuple[float, str, str]] = field(default_factory=lambda: deque(maxlen=40))

    def observe(self, event: Event, *, elapsed_seconds: float | None = None) -> None:
        self._stamp(event.timestamp)
        if elapsed_seconds is not None:
            self.arrival_elapsed_seconds = max(0.0, elapsed_seconds)
        if isinstance(event, Started):
            self._observe_started(event, elapsed_seconds)
        elif isinstance(event, Log):
            self._observe_cache_log(event)
        elif isinstance(event, Span):
            self._observe_span(event, elapsed_seconds)
        elif isinstance(event, Usage):
            self._observe_usage(event)
        elif isinstance(event, Terminated):
            self._observe_root_terminated(event, elapsed_seconds)

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
        event_elapsed = (
            None
            if self.first_at is None or self.latest_at is None
            else max(0.0, (self.latest_at - self.first_at).total_seconds())
        )
        if self.arrival_elapsed_seconds is None:
            return event_elapsed
        if event_elapsed is None:
            return self.arrival_elapsed_seconds
        return max(self.arrival_elapsed_seconds, event_elapsed)

    @property
    def cache_totals(self) -> tuple[int, int, int] | None:
        """Latest authoritative hit, miss, and bypass totals across Candidate Runs."""

        if not self.cache_counts:
            return None
        return (
            sum(counts[0] for counts in self.cache_counts.values()),
            sum(counts[1] for counts in self.cache_counts.values()),
            sum(counts[2] for counts in self.cache_counts.values()),
        )

    @property
    def cache_bypass_breakdown(self) -> tuple[tuple[str, int], ...]:
        """Bypass reasons across every Candidate Run, most frequent first.

        Ties break on the reason name so a live re-render cannot reorder equal counts.
        AIDEV-NOTE: `other` summed across runs collapses different reason sets — honest per run,
        imprecise in aggregate. Deliberately not surfaced; explaining it costs more than it buys.
        """

        totals: dict[str, int] = {}
        for reasons in self.cache_bypass_reasons.values():
            for reason, count in reasons.items():
                totals[reason] = totals.get(reason, 0) + count
        return tuple(sorted(totals.items(), key=lambda item: (-item[1], item[0])))

    @property
    def cache_hit_rate(self) -> float | None:
        counts = self.cache_totals
        if counts is None:
            return None
        hits, misses, _ = counts
        cacheable = hits + misses
        return None if cacheable == 0 else hits / cacheable

    def _note(
        self,
        event: Event,
        kind: str,
        text: str,
        elapsed_seconds: float | None = None,
    ) -> None:
        event_offset = (
            0.0
            if self.first_at is None
            else max(0.0, (event.timestamp - self.first_at).total_seconds())
        )
        offset = (
            event_offset
            if elapsed_seconds is None
            else max(event_offset, max(0.0, elapsed_seconds))
        )
        self.feed.appendleft((offset, kind, text))

    def _stamp(self, moment: datetime) -> None:
        if self.first_at is None or moment < self.first_at:
            self.first_at = moment
        if self.latest_at is None or moment > self.latest_at:
            self.latest_at = moment

    def _observe_started(self, event: Started, elapsed_seconds: float | None) -> None:
        if self.candidate_urls and event.url4 not in self.candidate_urls:
            return
        self.root_sources.add(event.source)
        self.activity = "Running candidate" if self.total_candidates == 1 else "Running candidates"
        if not self.evaluation_started:
            self.evaluation_started = True
            self._note(event, "start", "evaluation started", elapsed_seconds)

    def _observe_root_terminated(
        self,
        event: Terminated,
        elapsed_seconds: float | None,
    ) -> None:
        if self.candidate_urls and event.source not in self.root_sources:
            return
        self._observe_terminated(event, elapsed_seconds)

    def _observe_cache_log(self, event: Log) -> None:
        names = ("cache.hits", "cache.misses", "cache.bypasses")
        values = tuple(event.attributes.get(name) for name in names)
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            return
        self.cache_counts[event.run_id] = cast(tuple[int, int, int], values)
        # INVARIANT: the summary is a reconciliation, so it REPLACES this run's reason map rather
        # than adding to it — including replacing it with nothing when the run had no bypasses.
        # WHY the prefix is safe: `cache.bypasses` (the total) does not start with `cache.bypass.`,
        # so the total can never be read as a reason bucket.
        self.cache_bypass_reasons[event.run_id] = {
            key[len(_BYPASS_REASON_PREFIX) :]: value
            for key, value in event.attributes.items()
            if key.startswith(_BYPASS_REASON_PREFIX)
            and isinstance(value, int)
            and not isinstance(value, bool)
        }

    def _observe_span(self, event: Span, elapsed_seconds: float | None) -> None:
        # Structural URL4 spans carry no request_model; only paid model work counts.
        if event.request_model is None:
            return
        self._observe_cache_status(event)
        self.model_calls += 1
        if event.request_model in self.candidate_models:
            self.candidate_calls += 1
            role = "candidate"
            self.activity = _calls_activity("Running candidate", self.candidate_calls)
        else:
            self.benchmark_calls += 1
            role = "grading"
            self.activity = _calls_activity("Grading benchmark", self.benchmark_calls)
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
        self._note(
            event,
            "error" if event.status == "error" else "model",
            f"{role} · {_span_text(event)}",
            elapsed_seconds,
        )

    def _observe_cache_status(self, event: Span) -> None:
        if event.cache_status is None:
            return
        counts = list(self.cache_counts.get(event.run_id, (0, 0, 0)))
        counts[{"hit": 0, "miss": 1, "bypass": 2}[event.cache_status]] += 1
        self.cache_counts[event.run_id] = cast(tuple[int, int, int], tuple(counts))
        if event.cache_status != "bypass":
            return
        # WHY tally live rather than wait for the summary: the band is a diagnostic during the run,
        # and a bypass storm is worth seeing before the run ends. INVARIANT: a bypass naming no
        # reason still lands in a bucket, so the breakdown always sums to the bypass total.
        reason = (event.cache_reason or "").strip() or UNSTATED_BYPASS_REASON
        observed = self.cache_bypass_reasons.setdefault(event.run_id, {})
        observed[reason] = observed.get(reason, 0) + 1

    def _observe_usage(self, event: Usage) -> None:
        # 'subtree' repeats what its children already reported — summing both double counts.
        if event.scope != "self":
            return
        amount = event.usage.cost_usd
        if amount is None:
            return
        self.cost_usd = amount if self.cost_usd is None else self.cost_usd + amount

    def _observe_terminated(self, event: Terminated, elapsed_seconds: float | None) -> None:
        self.completed += 1
        self.terminal_counts[event.status] = self.terminal_counts.get(event.status, 0) + 1
        if event.error is not None and self.error is None:
            self.error = event.error.message
        kind = "done" if event.status == "succeeded" else "error"
        if not self.finished and self.total_candidates is not None:
            self.activity = (
                f"Running candidates · {self.completed}/{self.total_candidates} finished"
            )
            terminal = "finished" if event.status == "succeeded" else event.status.replace("_", " ")
            self._note(
                event,
                kind,
                f"candidate {self.completed}/{self.total_candidates} {terminal}"
                f"{self._cache_suffix(event.run_id)}",
                elapsed_seconds,
            )
            return
        terminal = "finished" if self.status == "succeeded" else self.status.replace("_", " ")
        self.activity = f"Evaluation {terminal}"
        self._note(
            event,
            kind,
            f"evaluation {terminal}{self._cache_suffix(event.run_id)}",
            elapsed_seconds,
        )

    def _cache_suffix(self, run_id: str) -> str:
        counts = self.cache_counts.get(run_id)
        if counts is None:
            return ""
        parts = [
            _cache_count(name, count)
            for name, count in zip(("hit", "miss", "bypass"), counts, strict=True)
            if count
        ]
        return f" · cache: {', '.join(parts)}" if parts else ""


def _cache_count(name: str, count: int) -> str:
    plural = {"hit": "hits", "miss": "misses", "bypass": "bypasses"}[name]
    return f"{count:,} {name if count == 1 else plural}"


def _calls_activity(phase: str, count: int) -> str:
    noun = "model call" if count == 1 else "model calls"
    return f"{phase} · {count} {noun} completed"


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
