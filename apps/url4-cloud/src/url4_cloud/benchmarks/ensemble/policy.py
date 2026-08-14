"""Versioned constants for the benchmark-independent corrective loop.

FEATURE: OME-796 — the LANL corrective protocol as a generic capability. The
client compiles the ENTIRE loop (member fan-out, rounds, gates, select) into one
whole-`$candidate` expression; the engine contributes only the three pure
data->data endpoints under `CORRECTIVE_PREFIX` plus each benchmark's advertised
check surface. Everything here is transport contract: the client mirrors these
route strings and prompts verbatim when it renders a loop expression, so any
change is a protocol change.
"""

from __future__ import annotations

import hashlib

# WHY a version segment instead of a revision hash in the route: the client
# renders these routes into candidate expressions without fetching them from any
# manifest (they are engine capability, not benchmark surface — the same class of
# wire constant as /benchmarks/candidate). A semantic change to gate/select
# semantics ships as /v2 routes; CORRECTIVE_FLOW below documents and hashes the
# semantics the v1 routes implement.
CORRECTIVE_API_VERSION = "v1"
CORRECTIVE_PREFIX = f"/ensemble/corrective/{CORRECTIVE_API_VERSION}"
GATE_ROUTE = f"{CORRECTIVE_PREFIX}/gate"
SELECT_ROUTE = f"{CORRECTIVE_PREFIX}/select"
ANSWER_ROUTE = f"{CORRECTIVE_PREFIX}/answer"

# The check-surface port record — every benchmark adapter returns exactly this
# shape: {schema, passed: bool, satisfaction: float in [0,1], feedback: sanitized
# text, answer: echoed draft}. `passed` replaces the old "PASSED" feedback
# sentinel; `satisfaction` replaces the IFEval-private `_strict_satisfaction`
# call inside gate/select (each benchmark computes its own behind the adapter).
CHECK_SURFACE_SCHEMA = "screamingface.check-surface.v1"

# The structural floor is a PANEL rule (a corrective panel needs >=2 drafts to
# select between); the ceiling is the letter-picker mechanism cap — a judge
# tie-break names an answer by one letter.
MIN_MEMBERS = 2
MAX_MEMBERS = 4
MEMBER_LETTERS = "abcd"
DEFAULT_MAX_ROUNDS = 3

RETRY_INSTRUCTION = (
    "Write a new answer to the original request. Correct every requirement named in the "
    "feedback and return only the new answer."
)
SELF_FEEDBACK_INSTRUCTION = (
    "Write short concrete feedback telling yourself how to fix every failed requirement "
    "named in the verification feedback. Do not write a new answer."
)
JUDGE_FEEDBACK_INSTRUCTION = (
    "You are the judge for a team of answer writers. Their answers failed the listed "
    "requirements. Write short concrete corrective feedback that tells the writers how "
    "to satisfy every failed requirement. Do not write an answer yourself."
)
TIE_BREAK_INSTRUCTION = (
    "Every candidate answer already satisfies the requirements. Pick the best-written "
    "one. Reply with exactly one letter naming your pick and nothing else."
)

# INVARIANT: URL4 context prose ships unescaped — a single quote corrupts the
# rendered expression's re-parse and a top-level comma splits the context into
# slots. The corrective substrate test pins both restrictions for every entry.
PROSE_CONSTANTS = (
    RETRY_INSTRUCTION,
    SELF_FEEDBACK_INSTRUCTION,
    JUDGE_FEEDBACK_INSTRUCTION,
    TIE_BREAK_INSTRUCTION,
)

# The corrective control-flow contract, hashed into the protocol revision. The
# flow lives in deterministic gate/select endpoints rather than in visible URL4
# structure, so this sentence — not the expression text — is what pins it;
# changing ANY clause is a protocol change and must read differently here.
CORRECTIVE_FLOW = (
    "at most max_rounds attempts; every member answers each executed attempt; an "
    "attempt with >=1 passing check STOPS the case; the judge tie-breaks only among "
    "passers of the stopping attempt; judge feedback is authored only for a no-pass "
    "attempt; a case that never passes selects the answer with maximal check "
    "satisfaction, judge tie-break on exact ties; the selected answer is always a "
    "member answer verbatim"
)

# Every prose constant and shape bound defines answer-selection meaning and
# therefore protocol identity. Run records carry this revision (via the client's
# recipe topology) alongside the benchmark revision embedded in the check route.
CORRECTIVE_PROTOCOL_REVISION = hashlib.sha256(
    "\n".join(
        (
            CORRECTIVE_API_VERSION,
            CORRECTIVE_FLOW,
            CHECK_SURFACE_SCHEMA,
            str(MIN_MEMBERS),
            str(MAX_MEMBERS),
            RETRY_INSTRUCTION,
            SELF_FEEDBACK_INSTRUCTION,
            JUDGE_FEEDBACK_INSTRUCTION,
            TIE_BREAK_INSTRUCTION,
        )
    ).encode()
).hexdigest()[:16]

__all__ = [
    "ANSWER_ROUTE",
    "CHECK_SURFACE_SCHEMA",
    "CORRECTIVE_API_VERSION",
    "CORRECTIVE_FLOW",
    "CORRECTIVE_PREFIX",
    "CORRECTIVE_PROTOCOL_REVISION",
    "DEFAULT_MAX_ROUNDS",
    "GATE_ROUTE",
    "JUDGE_FEEDBACK_INSTRUCTION",
    "MAX_MEMBERS",
    "MEMBER_LETTERS",
    "MIN_MEMBERS",
    "PROSE_CONSTANTS",
    "RETRY_INSTRUCTION",
    "SELECT_ROUTE",
    "SELF_FEEDBACK_INSTRUCTION",
    "TIE_BREAK_INSTRUCTION",
]
