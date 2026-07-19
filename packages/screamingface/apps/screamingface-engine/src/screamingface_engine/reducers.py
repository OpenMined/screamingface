"""URL4 adapters for deterministic ScreamingFace reducers."""

from __future__ import annotations

import json
import re
from typing import NoReturn

from screamingface._reduction import select_majority
from url4 import Request, ResolutionError

MAJORITY_VOTE_ROUTE = "/reducers/majority-vote"
_MEMBER_KEY = re.compile(r"member_([1-9][0-9]*)\Z")


def majority_vote(request: Request) -> str:
    """Select a member answer from URL4's resolved structured context."""

    if request.intent:
        _invalid("majority vote does not accept an intent")
    if request.params:
        _invalid(f"majority vote does not accept parameters: {sorted(request.params)}")

    try:
        payload = json.loads(request.context)
    except json.JSONDecodeError:
        _invalid("majority-vote context must be a JSON object")
    if not isinstance(payload, dict):
        _invalid("majority-vote context must be a JSON object")

    indexed: dict[int, str] = {}
    for key, answer in payload.items():
        match = _MEMBER_KEY.fullmatch(key)
        if match is None:
            _invalid("majority-vote keys must be contiguous member_1 through member_n")
        if not isinstance(answer, str):
            _invalid("majority-vote answers must be strings")
        indexed[int(match.group(1))] = answer

    expected = list(range(1, len(indexed) + 1))
    if len(indexed) < 2 or sorted(indexed) != expected:
        _invalid("majority vote requires contiguous member_1 through member_n with n >= 2")

    try:
        return select_majority([indexed[position] for position in expected])
    except (TypeError, ValueError) as exc:
        _invalid(str(exc))


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["MAJORITY_VOTE_ROUTE", "majority_vote"]
