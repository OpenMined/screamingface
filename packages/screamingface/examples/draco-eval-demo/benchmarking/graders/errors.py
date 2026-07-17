"""Grader-family errors that must ABORT a run instead of scoring a row.

`_eval_one` in benchmarking/arena/base.py re-raises these alongside
SpendGuardError — a swallowed rubric-shape mismatch would grade every
row 0.0 while spending real judge money (the HealthBench audit's
failure mode: output that looks like a legitimate result, not an error).
"""

from __future__ import annotations


class RubricShapeError(ValueError):
    """The rubric failed to parse, flattened to zero criteria, or has no
    positive-weight criterion — grading it would produce a meaningless
    score. Raised BEFORE any judge call fires."""


class JudgeVerdictError(RuntimeError):
    """No judge run produced a FULL set of validated verdicts for a row.

    Scoring a partial run would bias the score: negative-points items
    never sit in the denominator, so losing one to a judge failure can
    only inflate the row. And a row frozen at 0.0 after every reply
    failed validation silently deflates the aggregate mean while judge
    money was spent. Per-row, NOT run-fatal: the arena's `_eval_one`
    skips the row (nothing is written), so a resume retries it — unlike
    RubricShapeError, which aborts the whole run."""
