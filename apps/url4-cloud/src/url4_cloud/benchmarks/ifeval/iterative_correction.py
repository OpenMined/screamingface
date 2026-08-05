"""The two explicit corrective IFEval Variants.

- self-corrective: the Candidate answers, the deterministic checker reports
  violations, the Candidate AUTHORS ITS OWN feedback and retries — the {solo + loop}
  ablation that Skurikhin et al., "Beyond Leaderboards: Tokenomics of Agentic Small
  Language Model Ensembles" (LANL, https://openreview.net/forum?id=XSIYfTm2h7), never ran.
- verifying-ensemble (2..4 direct Model members): an OpenMined variant inspired by
  Skurikhin et al.'s ensemble. Every member draft is checked individually; the Candidate's
  SYNTHESIZER acts as JUDGE — it authors corrective feedback and tie-breaks among passers.
  The selection is a member's answer VERBATIM (deterministic select route), so the judge can
  never break a constraint a member satisfied. Unlike the source study's conditional loop,
  this URL4 executes all three attempts and Judge steps unconditionally.

Both Variants emit one attempt-tagged selection/check record per attempt and share the
same earliest-strict-pass Aggregation implementation. They remain separately identified
because the LANL paper did not run the self-corrective ablation.
"""

from __future__ import annotations

from url4 import Node, RelExpr, Text, expr, iterate, ref, render, src, struct
from url4_cloud.benchmarks.definition import Benchmark, candidate
from url4_cloud.benchmarks.ifeval.corrective_policy import (
    ENSEMBLE_AGGREGATE_ROUTE,
    JUDGE_FEEDBACK_INSTRUCTION,
    JUDGE_PICK_INSTRUCTION,
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MEMBER_ANSWER_ROUTE,
    MEMBER_LETTERS,
    MEMBER_RECORD_ROUTE,
    MIN_MEMBERS,
    PROSE_CONSTANTS,
    RESOLVE_CANDIDATE_ROUTE,
    RETRY_INSTRUCTION,
    SELECT_ROUTE,
    SELF_AGGREGATE_ROUTE,
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
    SELF_FEEDBACK_INSTRUCTION,
    SYNTHESIZER_BINDING,
    VERIFYING_ENSEMBLE_ID,
    VERIFYING_ENSEMBLE_REVISION,
)
from url4_cloud.benchmarks.ifeval.definition import (
    CASE_COUNT,
    CASES_ROUTE,
    CHECK_ROUTE,
    install_ifeval,
)


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
    """Build one member-count-independent verifying-ensemble expression."""

    # FOLLOW-UP(khoa): This architecture refactor intentionally preserves the current
    # three-round implementation. If we later align its control flow more closely with
    # the published LANL protocol, keep that work inside this Benchmark Variant: a
    # deterministic decision route can return [] to skip a URL4 branch or one payload to
    # run it, allowing early acceptance, passer-only tie-breaking, and retries only when
    # no member passes. Confirm the authors' prompts and all-fail behavior before calling
    # that implementation an exact reproduction.

    resolution = RelExpr(
        path=RESOLVE_CANDIDATE_ROUTE,
        context="$candidate_members",
        intent=Text(SYNTHESIZER_BINDING),
    )
    # INVARIANT: the SDK supplies an ordinary URL4 struct whose fields reference ordinary
    # `candidate_member_N` bindings. Resolution validates and canonicalizes those expressions
    # once before any row can invoke a member; it never chooses or defaults a Judge.
    members = src(resolution, name="members", weight=0.0)
    sources = [
        src("$item.input", name="question", weight=0.0),
        src("$item.id", name="case_id", weight=0.0),
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        round_name = f"member_round_{attempt}"
        sources.append(
            src(
                _member_round(
                    ref("members"),
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
        row_bindings=(members,),
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
    row_bindings: tuple[Node, ...] = (),
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
    row_set = expr(
        *row_bindings,
        src(rows, name="selected_rows", weight=0.0),
        intent=Text("$selected_rows"),
    )
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
    variant="self-corrective",
    title="IFEval Self-corrective",
    description=(
        "IFEval with a bounded three-attempt self-correction ablation. The complete "
        "Candidate reads deterministic verification feedback, authors its own coaching, "
        "and retries. The LANL paper did not evaluate this additional protocol."
    ),
    revision=SELF_CORRECTIVE_REVISION,
    case_count=CASE_COUNT,
    build=_build_solo,
    install=install_ifeval,
)

IFEVAL_VERIFYING_ENSEMBLE = Benchmark(
    id=VERIFYING_ENSEMBLE_ID,
    variant="verifying-ensemble",
    title="IFEval Verifying Ensemble",
    description=(
        "An OpenMined verifying-ensemble variant inspired by Skurikhin et al.: two to four "
        "direct Fusion members are checked and retried independently while the explicit "
        "Fusion synthesizer selects answers and authors corrective feedback. Selected answers "
        "remain verbatim, and all three attempts execute unconditionally."
    ),
    revision=VERIFYING_ENSEMBLE_REVISION,
    case_count=CASE_COUNT,
    build=_build_members,
    install=install_ifeval,
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
