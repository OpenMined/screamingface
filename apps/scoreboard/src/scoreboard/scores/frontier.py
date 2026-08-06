"""Open/closed frontier computation (OME-323, spec §5/§6).

Pure function, no I/O — takes already-fetched schemas so it's directly
unit-testable without a DB.
"""

from __future__ import annotations

from scoreboard.classification.openness import classify_baseline, classify_score

from .schemas import BaselineSchema, FrontierPoint, FrontierResult, ScoreSchema


def _current_split(
    scores: list[ScoreSchema], baselines: list[BaselineSchema]
) -> tuple[int, int, float]:
    """`open_count`/`closed_count`/`open_share` over ALL rows, Scores and Baselines
    together — the "how much of the frontier is open right now" number."""
    openness_calls = [classify_score(score) for score in scores]
    openness_calls += [classify_baseline(baseline) for baseline in baselines]
    open_count = sum(1 for openness in openness_calls if openness == "open")
    closed_count = len(openness_calls) - open_count
    total = open_count + closed_count
    open_share = open_count / total if total else 0.0
    return open_count, closed_count, open_share


def _compute_trend(scores: list[ScoreSchema]) -> tuple[FrontierPoint | None, list[FrontierPoint]]:
    """Walks Score rows ONLY, ordered by `submitted_at`. A Baseline's `imported_at`
    isn't a trustworthy real-world timestamp, so a Baseline never enters this walk
    at all — not merely "excluded from the printed list". The holder advances only
    on a strict accuracy improvement — an exact tie leaves the existing holder in
    place (spec §6's tie-breaking resolution).
    """
    trend: list[FrontierPoint] = []
    current: FrontierPoint | None = None
    for score in sorted(scores, key=lambda s: s.submitted_at):
        if current is not None and score.accuracy <= current.accuracy:
            continue
        current = FrontierPoint(
            at=score.submitted_at,
            accuracy=score.accuracy,
            openness=classify_score(score),
            holder="score",
            label=score.spec_id,
        )
        trend.append(current)
    return current, trend


def compute_frontier(
    scores: list[ScoreSchema],
    baselines: list[BaselineSchema],
) -> FrontierResult:
    """Two independent passes (spec §6's baseline-timing resolution — deliberately
    NOT one merged computation): the current open/closed split over all rows
    (`_current_split`), and the trend over Score rows only (`_compute_trend`).
    """
    open_count, closed_count, open_share = _current_split(scores, baselines)
    current, trend = _compute_trend(scores)

    return FrontierResult(
        open_count=open_count,
        closed_count=closed_count,
        open_share=open_share,
        current=current,
        trend=trend,
    )
