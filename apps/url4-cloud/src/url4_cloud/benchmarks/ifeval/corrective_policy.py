"""Versioned constants for IFEval corrective protocol construction."""

from __future__ import annotations

import hashlib

from url4_cloud.benchmarks.ifeval.definition import REVISION as IFEVAL_REVISION

MAX_ATTEMPTS = 3
MIN_MEMBERS = 2
MAX_MEMBERS = 4
MEMBER_LETTERS = "abcd"
SELF_CORRECTIVE_ID = "ifeval/self-corrective"
VERIFYING_ENSEMBLE_ID = "ifeval/verifying-ensemble"
SELF_PROTOCOL_REVISION = "self-corrective-v1"
ENSEMBLE_PROTOCOL_REVISION = "verifying-ensemble-v1"

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
JUDGE_PICK_INSTRUCTION = (
    "Pick the best candidate answer for the request. Prefer candidates whose verdict is "
    "PASSED. Reply with exactly one letter naming your pick and nothing else."
)

# INVARIANT: URL4 context prose ships unescaped — a single quote corrupts the rendered
# expression's re-parse and a top-level comma splits the context into slots. The focused
# iterative-correction test pins both restrictions for every entry in this collection.
PROSE_CONSTANTS = (
    RETRY_INSTRUCTION,
    SELF_FEEDBACK_INSTRUCTION,
    JUDGE_FEEDBACK_INSTRUCTION,
    JUDGE_PICK_INSTRUCTION,
)

# Every prose constant and shape bound defines score meaning and therefore revision identity.
SELF_CORRECTIVE_REVISION = hashlib.sha256(
    "\n".join(
        (
            IFEVAL_REVISION,
            SELF_PROTOCOL_REVISION,
            str(MAX_ATTEMPTS),
            RETRY_INSTRUCTION,
            SELF_FEEDBACK_INSTRUCTION,
        )
    ).encode()
).hexdigest()[:16]
VERIFYING_ENSEMBLE_REVISION = hashlib.sha256(
    "\n".join(
        (
            IFEVAL_REVISION,
            ENSEMBLE_PROTOCOL_REVISION,
            str(MAX_ATTEMPTS),
            str(MIN_MEMBERS),
            str(MAX_MEMBERS),
            RETRY_INSTRUCTION,
            JUDGE_FEEDBACK_INSTRUCTION,
            JUDGE_PICK_INSTRUCTION,
        )
    ).encode()
).hexdigest()[:16]
SELF_ROUTE_PREFIX = f"/benchmarks/ifeval/self-corrective/{SELF_CORRECTIVE_REVISION}"
ENSEMBLE_ROUTE_PREFIX = f"/benchmarks/ifeval/verifying-ensemble/{VERIFYING_ENSEMBLE_REVISION}"
SELF_AGGREGATE_ROUTE = f"{SELF_ROUTE_PREFIX}/aggregate"
ENSEMBLE_AGGREGATE_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/aggregate"
SELECT_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/select"
RESOLVE_CANDIDATE_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/resolve-candidate"
MEMBER_RECORD_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/member-record"
MEMBER_ANSWER_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/member-answer"
SYNTHESIZER_BINDING = "$candidate_synthesizer"


__all__: list[str] = []
