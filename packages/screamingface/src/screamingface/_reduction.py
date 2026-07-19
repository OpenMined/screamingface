"""Pure deterministic reducer execution shared with engine adapters."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence


def select_majority(answers: Sequence[str]) -> str:
    """Return the exact-string majority, breaking ties by input position."""

    if isinstance(answers, (str, bytes)) or len(answers) < 2:
        raise ValueError("majority vote requires at least two answers")
    for answer in answers:
        if not isinstance(answer, str):
            raise TypeError("majority-vote answers must be strings")
        if not answer.strip():
            raise ValueError("majority-vote answers must not be blank")

    counts = Counter(answers)
    highest = max(counts.values())
    return next(answer for answer in answers if counts[answer] == highest)


__all__ = ["select_majority"]
