"""Versioned semantics for DRACO's mid-run check surface — `draco-pass.v1`.

DRACO grades; it does not pass or fail. A corrective loop needs a boolean, so
this module *invents* one — and because an invented boolean decides which draft
a run submits, every input to it is named and versioned here:

- the threshold on the normalized weighted score,
- the judge instructions the check pass uses,
- the prompt framing that carries the rubric to the judge.

`CHECK_CRITERION` rides in the check route, so a different criterion is a
different route — visible in the manifest, in every compiled Candidate url4, and
in the recipe topology of every run record. Changing any constant here without
bumping the name silently changes what "passed" meant on past leaderboard rows.

WHY one batched pass, when canonical DRACO judges one criterion per call:
canonical grading spends 5 passes x N criteria (median 38) per case — at loop
rates (members x rounds) that is hundreds of judge calls per case. The check is
a STEERING instrument, not the scorer: canonical grading still produces the
published number. The batched prompt keeps the official framing (criterion type
visible, weights hidden) so the two instruments disagree as little as a cheaper
instrument can.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

CHECK_CRITERION = "draco-pass.v1"
# Normalized weighted score in [0, 1]; >= passes. 0.7 is the reviewed v1 position:
# high enough that a passing draft satisfies the heavily-weighted criteria, low
# enough that a loop terminates on real answers rather than grinding to max_rounds.
CHECK_THRESHOLD = 0.7
# One judge call plus two retries. A retry exists for unusable REPLIES (unparseable
# or incomplete), never to shop for a better verdict — the prompt is identical and
# only the cache-slot parameter moves.
CHECK_ATTEMPTS = 3

# INVARIANT: this ships as a rendered URL4 intent — a single quote would corrupt the
# expression's re-parse, and a newline would need escaping. Kept quote- and
# newline-free, and pinned by the check-surface tests.
CHECK_INSTRUCTIONS = (
    "You are grading one response against a numbered list of rubric requirements. "
    "For each requirement decide MET when the response satisfies it and UNMET when it "
    "does not. A requirement marked negative describes something the response must "
    "avoid: mark it MET only when the response actually does the thing it should avoid. "
    "Judge only what the response says. Return raw JSON only, starting with [ and "
    "containing one object per requirement in order, each with the fields id and "
    "status, where status is MET or UNMET. Do not add commentary."
)


def build_check_prompt(
    question: str,
    answer: str,
    criteria: Sequence[Mapping[str, Any]],
) -> str:
    """Frame one whole-rubric check pass for the judge.

    Mirrors the canonical per-criterion framing (`<query>` / `<response>` /
    requirement + type) with the requirements numbered so the reply maps back by
    ordinal. Weights never appear: the judge reports satisfaction, and scoring
    applies the weights afterwards.
    """

    lines = [
        "<query>",
        question,
        "</query>",
        "<response>",
        answer,
        "</response>",
        "<requirements>",
    ]
    for ordinal, criterion in enumerate(criteria, start=1):
        kind = "negative" if float(criterion.get("weight", 0)) < 0 else "positive"
        lines.append(f"[{ordinal}] ({kind}) {criterion['requirement']}")
    lines.append("</requirements>")
    return "\n".join(lines)


def answer_salt(answer: str) -> str:
    """A per-draft cache key so one draft's verdict can never serve another."""

    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "CHECK_ATTEMPTS",
    "CHECK_CRITERION",
    "CHECK_INSTRUCTIONS",
    "CHECK_THRESHOLD",
    "answer_salt",
    "build_check_prompt",
]
