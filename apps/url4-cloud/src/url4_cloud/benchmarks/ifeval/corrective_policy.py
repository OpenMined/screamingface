"""Versioned constants for IFEval corrective protocol construction."""

from __future__ import annotations

import hashlib

from url4_cloud.benchmarks.ifeval.definition import REVISION as IFEVAL_REVISION

MAX_ATTEMPTS = 3
MIN_MEMBERS = 2
MAX_MEMBERS = 4
MEMBER_LETTERS = "abcd"
SELF_CORRECTIVE_ID = "ifeval/self-corrective"
LANL_ENSEMBLE_ID = "ifeval/lanl-ensemble"
SELF_PROTOCOL_REVISION = "self-corrective-three-attempt-v1"

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
LANL_TIE_BREAK_INSTRUCTION = (
    "Every candidate answer already satisfies the requirements. Pick the best-written "
    "one. Reply with exactly one letter naming your pick and nothing else."
)

# INVARIANT: URL4 context prose ships unescaped — a single quote corrupts the rendered
# expression's re-parse and a top-level comma splits the context into slots. The focused
# iterative-correction test pins both restrictions for every entry in this collection.
PROSE_CONSTANTS = (
    RETRY_INSTRUCTION,
    SELF_FEEDBACK_INSTRUCTION,
    JUDGE_FEEDBACK_INSTRUCTION,
    LANL_TIE_BREAK_INSTRUCTION,
)

# The lanl-ensemble control-flow contract, hashed into its revision. The flow lives in
# deterministic gate/select endpoints rather than in visible URL4 structure, so the
# revision hash — not the expression text — is what pins it; changing ANY clause of
# this sentence is a protocol change and must read differently here.
LANL_FLOW = (
    "at most 3 attempts; every member answers each executed attempt; an attempt with "
    ">=1 strict passer STOPS the case; the judge tie-breaks only among passers of the "
    "stopping attempt; judge feedback is authored only for a no-pass attempt; a case "
    "that never passes selects the answer with maximal strict-satisfaction fraction, "
    "judge tie-break on exact ties; the selected answer is always a member answer "
    "verbatim, carrying the member's refusal marking"
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
# The reproduction of Skurikhin et al. §2 (the early-exit ensemble). The paper does
# not publish its judge prompts, so ours are named revision inputs; the control flow
# is pinned by LANL_FLOW.
# v2: member records carry the check record's refusal, and selection re-encodes the
# chosen member's refusal instead of erasing it — an all-refuse Case publishes as
# refused, never as a scored output holding refusal prose.
LANL_PROTOCOL_REVISION = "lanl-early-exit-ensemble-v2"
LANL_ENSEMBLE_REVISION = hashlib.sha256(
    "\n".join(
        (
            IFEVAL_REVISION,
            LANL_PROTOCOL_REVISION,
            LANL_FLOW,
            str(MAX_ATTEMPTS),
            str(MIN_MEMBERS),
            str(MAX_MEMBERS),
            RETRY_INSTRUCTION,
            JUDGE_FEEDBACK_INSTRUCTION,
            LANL_TIE_BREAK_INSTRUCTION,
        )
    ).encode()
).hexdigest()[:16]

SELF_ROUTE_PREFIX = f"/benchmarks/ifeval/self-corrective/{SELF_CORRECTIVE_REVISION}"
LANL_ROUTE_PREFIX = f"/benchmarks/ifeval/lanl-ensemble/{LANL_ENSEMBLE_REVISION}"
SELF_AGGREGATE_ROUTE = f"{SELF_ROUTE_PREFIX}/aggregate"
LANL_AGGREGATE_ROUTE = f"{LANL_ROUTE_PREFIX}/aggregate"
LANL_GATE_ROUTE = f"{LANL_ROUTE_PREFIX}/gate"
LANL_SELECT_ROUTE = f"{LANL_ROUTE_PREFIX}/select"
LANL_ENVELOPE_ROUTE = f"{LANL_ROUTE_PREFIX}/case-evaluation"
RESOLVE_CANDIDATE_ROUTE = f"{LANL_ROUTE_PREFIX}/resolve-candidate"
MEMBER_RECORD_ROUTE = f"{LANL_ROUTE_PREFIX}/member-record"
MEMBER_ANSWER_ROUTE = f"{LANL_ROUTE_PREFIX}/member-answer"
SYNTHESIZER_BINDING = "$candidate_synthesizer"


__all__: list[str] = []
