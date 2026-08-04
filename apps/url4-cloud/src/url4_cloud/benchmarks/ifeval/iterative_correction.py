"""The two explicit corrective IFEval Variants.

- self-corrective: the Candidate answers, the deterministic checker reports
  violations, the Candidate AUTHORS ITS OWN feedback and retries — the {solo + loop}
  ablation that Skurikhin et al., "Beyond Leaderboards: Tokenomics of Agentic Small
  Language Model Ensembles" (LANL, https://openreview.net/forum?id=XSIYfTm2h7), never ran.
- verifying-ensemble (2..4 direct Model members): Skurikhin et al.'s ensemble. Every member
  draft is checked individually; the Candidate's SYNTHESIZER acts as JUDGE — it authors
  the corrective feedback when nobody passes and tie-breaks among passers otherwise. The
  selection is a member's answer VERBATIM (deterministic select route), so the judge can
  never break a constraint a member satisfied. The judge belongs to the system under
  test, as in the source study — its [Ens-1] and [Ens-2] configurations share members
  and differ only in the judge model.

Both Variants emit one attempt-tagged selection/check record per attempt and share the
same earliest-strict-pass Aggregation implementation. They remain separately identified
because the LANL paper did not run the self-corrective ablation.
"""

from __future__ import annotations

import hashlib

from url4 import Node, RelExpr, Text, expr, iterate, render, src, struct
from url4_cloud.benchmarks.definition import Benchmark, candidate
from url4_cloud.benchmarks.ifeval.definition import (
    CASE_COUNT,
    CASES_ROUTE,
    CHECK_ROUTE,
    IFEVAL,
    install_family,
)
from url4_cloud.benchmarks.ifeval.definition import (
    REVISION as IFEVAL_REVISION,
)

MAX_ATTEMPTS = 3
MIN_MEMBERS = 2
MAX_MEMBERS = 4
MEMBER_LETTERS = "abcd"
SELF_CORRECTIVE_ID = "ifeval/self-corrective"
VERIFYING_ENSEMBLE_ID = "ifeval/verifying-ensemble"
SELF_PROTOCOL_REVISION = "self-corrective-three-attempt-v1"
ENSEMBLE_PROTOCOL_REVISION = "lanl-verifying-ensemble-v1"

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
# expression's re-parse (checks run with raw $refs and sibling sources drop) and a
# top-level comma splits the context into slots. Proven by DAG repro (edge_probe5,
# 2026-08-03). AIDEV-NOTE: enforced by
# test_ifeval_iterative_correction.py::test_prose_constants_stay_quote_and_comma_free —
# keep every fixed prose constant free of both when editing.
PROSE_CONSTANTS = (
    RETRY_INSTRUCTION,
    SELF_FEEDBACK_INSTRUCTION,
    JUDGE_FEEDBACK_INSTRUCTION,
    JUDGE_PICK_INSTRUCTION,
)

# WHY every prose constant and shape bound is a hash input: they define a protocol.
# Changing any of them changes what a score means, so it changes that Variant's identity.
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
VALIDATE_MEMBERS_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/validate-members"
MEMBER_RECORD_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/member-record"
MEMBER_ANSWER_ROUTE = f"{ENSEMBLE_ROUTE_PREFIX}/member-answer"
SYNTHESIZER_BINDING = "$candidate_synthesizer"


def _solo_attempt_input(attempt: int) -> str:
    if attempt == 1:
        return "$item.input"
    previous = attempt - 1
    return (
        "$item.input"
        f" | Previous answer: $answer_{previous}"
        f" | Feedback: $self_feedback_{previous}"
        f" | {RETRY_INSTRUCTION}"
    )


def _build_solo(case_count: int) -> Node:
    """Self-correction: the Candidate coaches itself between attempts."""

    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts.extend(
            (
                src(
                    candidate(_solo_attempt_input(attempt), web_search=False),
                    name=f"answer_{attempt}",
                    weight=0.0,
                ),
                src(
                    RelExpr(
                        path=CHECK_ROUTE,
                        context=f"$answer_{attempt}",
                        intent=Text(f"$item.id:{attempt}"),
                    ),
                    name=f"check_{attempt}",
                    weight=0.0,
                ),
            )
        )
        if attempt < MAX_ATTEMPTS:
            # Only sanitized violation descriptions cross back into the Candidate. The raw
            # grading record retains private instruction ids and flows only to Aggregation.
            attempts.append(
                src(
                    RelExpr(
                        path=CHECK_ROUTE,
                        context=f"$check_{attempt}",
                        intent=Text("feedback"),
                    ),
                    name=f"feedback_{attempt}",
                    weight=0.0,
                )
            )
            # WHY a second Candidate call: the model AUTHORS its own feedback — the same
            # role the judge plays for the ensemble shape, played by the only model
            # present. Keeps solo vs ensemble comparable on one column.
            attempts.append(
                src(
                    candidate(
                        "$item.input"
                        f" | Your answer: $answer_{attempt}"
                        f" | Verification feedback: $feedback_{attempt}"
                        f" | {SELF_FEEDBACK_INSTRUCTION}",
                        web_search=False,
                    ),
                    name=f"self_feedback_{attempt}",
                    weight=0.0,
                )
            )
    return _rows(attempts, case_count, aggregate_route=SELF_AGGREGATE_ROUTE)


def _member_attempt_input(attempt: int) -> str:
    if attempt == 1:
        return "$question"
    return (
        "$question"
        f" | Your previous answer: $previous_answer_{attempt}"
        f" | Judge feedback: $judge_feedback_{attempt - 1}"
        f" | {RETRY_INSTRUCTION}"
    )


def _member_round(collection: Node, attempt: int) -> Node:
    """Run one attempt over a runtime-sized collection of direct member expressions."""

    answer = f"member_answer_{attempt}"
    check = f"member_check_{attempt}"
    feedback = f"member_feedback_{attempt}"
    record = f"member_record_{attempt}"
    sources = []
    if attempt > 1:
        sources.append(
            src(
                RelExpr(
                    path=MEMBER_ANSWER_ROUTE,
                    context=f"$member_round_{attempt - 1}",
                    intent=Text("$item.key"),
                ),
                name=f"previous_answer_{attempt}",
                weight=0.0,
            )
        )
    sources.extend(
        (
            src(
                candidate(
                    _member_attempt_input(attempt),
                    binding="$item.expression",
                    web_search=False,
                ),
                name=answer,
                weight=0.0,
            ),
            src(
                RelExpr(
                    path=CHECK_ROUTE,
                    context=f"${answer}",
                    intent=Text(f"$case_id:{attempt}"),
                ),
                name=check,
                weight=0.0,
            ),
            src(
                RelExpr(path=CHECK_ROUTE, context=f"${check}", intent=Text("feedback")),
                name=feedback,
                weight=0.0,
            ),
            src(
                RelExpr(
                    path=MEMBER_RECORD_ROUTE,
                    context=_endpoint_payload(
                        {
                            "key": "$item.key",
                            "name": "$item.name",
                            "kind": "$item.kind",
                            "expression": "$item.expression",
                            "answer": f"${answer}",
                            "feedback": f"${feedback}",
                        }
                    ),
                    intent=Text("record"),
                ),
                name=record,
                weight=0.0,
            ),
        )
    )
    return iterate(
        collection,
        body=tuple(sources),
        intent=Text(f"${record}"),
        concurrency=4,
        on_error="fail",
    )


def _build_members(case_count: int) -> Node:
    """Build one member-count-independent LANL verifying-ensemble expression."""

    # FOLLOW-UP(khoa): This architecture refactor intentionally preserves the current
    # three-round implementation. If we later align its control flow more closely with
    # the published LANL protocol, keep that work inside this Benchmark Variant: a
    # deterministic decision route can return [] to skip a URL4 branch or one payload to
    # run it, allowing early acceptance, passer-only tie-breaking, and retries only when
    # no member passes. Confirm the authors' prompts and all-fail behavior before calling
    # that implementation an exact reproduction.

    sources = [
        src("$item.input", name="question", weight=0.0),
        src("$item.id", name="case_id", weight=0.0),
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        round_name = f"member_round_{attempt}"
        sources.append(
            src(
                _member_round(
                    RelExpr(
                        path=VALIDATE_MEMBERS_ROUTE,
                        context=_endpoint_payload({"encoded": "$candidate_members"}),
                        intent=Text(f"validate-{attempt}"),
                    ),
                    attempt,
                ),
                name=round_name,
                weight=0.0,
            )
        )
        sources.extend(
            (
                src(
                    candidate(
                        _judge_pick_input(round_name),
                        binding=SYNTHESIZER_BINDING,
                        web_search=False,
                    ),
                    name=f"judge_pick_{attempt}",
                    weight=0.0,
                ),
                src(
                    RelExpr(
                        path=SELECT_ROUTE,
                        context=f"${round_name}",
                        intent=Text(f"$judge_pick_{attempt}"),
                    ),
                    name=f"selection_{attempt}",
                    weight=0.0,
                ),
                src(
                    RelExpr(
                        path=CHECK_ROUTE,
                        context=f"$selection_{attempt}",
                        intent=Text(f"$case_id:{attempt}"),
                    ),
                    name=f"selection_check_{attempt}",
                    weight=0.0,
                ),
            )
        )
        if attempt < MAX_ATTEMPTS:
            sources.append(
                src(
                    candidate(
                        _judge_feedback_input(round_name),
                        binding=SYNTHESIZER_BINDING,
                        web_search=False,
                    ),
                    name=f"judge_feedback_{attempt}",
                    weight=0.0,
                )
            )
    return _rows(
        sources,
        case_count,
        aggregate_route=ENSEMBLE_AGGREGATE_ROUTE,
        selection_records=True,
    )


def _judge_pick_input(round_name: str) -> str:
    return _structured_context(
        {
            "request": "$question",
            "task": JUDGE_PICK_INSTRUCTION,
            "candidates": f"${round_name}",
        }
    )


def _judge_feedback_input(round_name: str) -> str:
    return _structured_context(
        {
            "request": "$question",
            "task": JUDGE_FEEDBACK_INSTRUCTION,
            "verdicts": f"${round_name}",
        }
    )


def _rows(
    sources: list,
    case_count: int,
    *,
    aggregate_route: str,
    selection_records: bool = False,
) -> Node:
    # INVARIANT: both shapes emit exactly one attempt-tagged check record per attempt
    # (solo: the answer's check; ensemble: the selection's check), so ONE aggregation
    # scores both — earliest strict pass, pass@attempt telemetry preserved.
    record = "selection_check" if selection_records else "check"
    checked = expr(
        *sources,
        intent=Text(" ".join(f"${record}_{attempt}" for attempt in range(1, MAX_ATTEMPTS + 1))),
    )
    rows = iterate(
        CASES_ROUTE,
        body=(src(checked, name="checked", weight=1.0),),
        intent=Text("case"),
        slice=None if case_count == CASE_COUNT else (0, case_count),
        on_error="collect",
    )
    row_set = expr(src(rows, name="selected_rows", weight=0.0), intent=Text("$selected_rows"))
    return expr(
        src(row_set, name="rows", weight=0.0),
        src(
            RelExpr(path=aggregate_route, context="$rows", intent=Text("aggregate")),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )


def _structured_context(value: dict[str, object]) -> str:
    return render(src(struct(value), name="payload"))


def _endpoint_payload(value: dict[str, object]) -> str:
    return render(struct(value))


IFEVAL_SELF_CORRECTIVE = Benchmark(
    id=SELF_CORRECTIVE_ID,
    family=IFEVAL.family,
    variant="self-corrective",
    title="IFEval Self-corrective",
    description=(
        "IFEval with a bounded three-attempt self-correction ablation. The complete "
        "Candidate reads deterministic verification feedback, authors its own coaching, "
        "and retries. The LANL paper did not evaluate this additional protocol."
    ),
    revision=SELF_CORRECTIVE_REVISION,
    case_count=CASE_COUNT,
    required_models=(),
    build=_build_solo,
    install=install_family,
)

IFEVAL_VERIFYING_ENSEMBLE = Benchmark(
    id=VERIFYING_ENSEMBLE_ID,
    family=IFEVAL.family,
    variant="verifying-ensemble",
    title="IFEval Verifying Ensemble",
    description=(
        "The LANL iterative-correction protocol: every direct Fusion member is checked "
        "and retried independently while the Fusion synthesizer tie-breaks compliant "
        "answers and authors corrective feedback. Selected answers remain verbatim."
    ),
    revision=VERIFYING_ENSEMBLE_REVISION,
    case_count=CASE_COUNT,
    required_models=(),
    build=_build_members,
    install=install_family,
)

__all__ = [
    "IFEVAL_SELF_CORRECTIVE",
    "IFEVAL_VERIFYING_ENSEMBLE",
    "MAX_ATTEMPTS",
    "MAX_MEMBERS",
    "MEMBER_LETTERS",
    "MIN_MEMBERS",
    "PROSE_CONSTANTS",
]
