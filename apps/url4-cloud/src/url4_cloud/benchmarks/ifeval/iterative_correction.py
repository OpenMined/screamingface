"""The two corrective IFEval Variants — solo self-correction and the LANL ensemble.

- self-corrective: the Candidate answers, the deterministic checker reports
  violations, the Candidate AUTHORS ITS OWN feedback and retries — the {solo + loop}
  ablation that Skurikhin et al., "Beyond Leaderboards: Tokenomics of Agentic Small
  Language Model Ensembles" (LANL, https://openreview.net/forum?id=XSIYfTm2h7), never ran.
- lanl-ensemble (2..4 direct Model members): a reproduction of the paper's §2 control
flow:

    every member answers → the deterministic checker verifies each answer →
    any strict passer STOPS the case (the judge only tie-breaks between multiple
    passers) → only a no-pass round buys a judge-feedback call and a retry round →
    at most 3 attempts → a case that never passes selects the answer with maximal
    strict-satisfaction fraction (judge tie-break on exact ties).

HOW conditionality lives in a static URL4 DAG: deterministic GATE endpoints return a
JSON array that is either EMPTY (skip) or carries one payload (run), and the
conditional work sits in the body of an `iterate` over that array — zero items means
the subtree never executes, so a round-1 pass costs N member calls and nothing else.
No url4-core change; the flow's semantics are pinned by `LANL_FLOW`, which is hashed
into `LANL_ENSEMBLE_REVISION` (the expression text alone cannot show a gate's
decision rule, so the revision hash carries it instead).

Both Variants emit one attempt-tagged check record per executed attempt and share the
same earliest-strict-pass Aggregation implementation. They remain separately identified
because the LANL paper did not run the self-corrective ablation.

KNOWN JITTER (Non-ASCII Roulette): two official rows (keys 1122, 1129) draw random
constraint parameters per check — official-harness behavior. The lanl-ensemble checks a
selected answer twice (the member check that feeds the gate, and the re-check that
becomes the grading record), and the two draws are independent, so on those rows the
gate and the record can disagree — worst case a case early-exits as passed but records a
fail (<=2/541 prompt-level jitter, on rows the official harness re-rolls every run
anyway). Eliminating it means carrying the member check record through as the attempt
record — a protocol-shape change and revision bump, deliberately not taken.
"""

from __future__ import annotations

from url4 import Node, RelExpr, Text, expr, iterate, ref, render, src, struct
from url4_cloud.benchmarks.definition import Benchmark, candidate
from url4_cloud.benchmarks.ifeval.corrective_policy import (
    JUDGE_FEEDBACK_INSTRUCTION,
    LANL_AGGREGATE_ROUTE,
    LANL_ENSEMBLE_ID,
    LANL_ENSEMBLE_REVISION,
    LANL_ENVELOPE_ROUTE,
    LANL_GATE_ROUTE,
    LANL_SELECT_ROUTE,
    LANL_TIE_BREAK_INSTRUCTION,
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MEMBER_ANSWER_ROUTE,
    MEMBER_LETTERS,
    MEMBER_RECORD_ROUTE,
    MIN_MEMBERS,
    PROSE_CONSTANTS,
    RESOLVE_CANDIDATE_ROUTE,
    RETRY_INSTRUCTION,
    SELF_AGGREGATE_ROUTE,
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
    SELF_FEEDBACK_INSTRUCTION,
    SYNTHESIZER_BINDING,
)
from url4_cloud.benchmarks.ifeval.definition import (
    CASE_COUNT,
    CASE_EVALUATION_ROUTE,
    CASES_ROUTE,
    CHECK_ROUTE,
    install_ifeval,
)
from url4_cloud.benchmarks.protocol import build_evaluation_protocol


def _solo_attempt_input(attempt: int) -> str:
    if attempt == 1:
        return "$item.input"
    previous = attempt - 1
    return (
        "$item.input"
        f" | Previous answer: $check_{previous}.answer"
        f" | Feedback: $self_feedback_{previous}.output"
        f" | {RETRY_INSTRUCTION}"
    )


def _build_solo(case_count: int) -> Node:
    """Self-correction: the Candidate coaches itself between attempts.

    Think of it as a student re-sitting the same exam question up to 3 times,
    writing their own study notes between sittings. Per case, in execution order:

    1. Attempt k answers (`answer_k`) — attempt 1 sees the bare prompt; attempts
       2..3 see the prompt + previous answer + the self-authored feedback.
    2. The deterministic checker grades it (`check_k`) into an attempt-tagged record.
    3. Between attempts (k < MAX_ATTEMPTS): the checker's violations are sanitized
       into feedback text (`feedback_k`), then the Candidate turns that into its own
       coaching (`self_feedback_k`) — a second model call, mirroring the judge role
       the ensemble variant gives to a separate model.
    4. All attempt records are packed into one Case Evaluation envelope, and the
       cross-row reducer scores each case on its EARLIEST strict-passing attempt.

    Worked cost example (1 case): pass on attempt 2 = 2 answer calls +
    2 self-feedback-authoring calls... except attempts here are UNCONDITIONAL —
    unlike the LANL variant, all 3 attempts always execute (5 model calls per case
    regardless of when it first passes); early attempts that already passed simply
    win at Aggregation time.
    """

    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Stage 1 + 2 — attempt k answers, then the checker grades it.
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
            # Stage 3 — between attempts: sanitize violations into feedback text, then
            # the Candidate authors its own coaching from it.
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
                        f" | Your answer: $check_{attempt}.answer"
                        f" | Verification feedback: $feedback_{attempt}"
                        f" | {SELF_FEEDBACK_INSTRUCTION}",
                        web_search=False,
                    ),
                    name=f"self_feedback_{attempt}",
                    weight=0.0,
                )
            )
    # Stage 4 — pack all attempt records into one Case Evaluation envelope; the
    # reducer scores the earliest strict pass.
    checked = expr(
        *attempts,
        src(
            RelExpr(
                path=CASE_EVALUATION_ROUTE,
                context=_endpoint_payload(
                    {
                        f"attempt_{attempt}": f"$check_{attempt}"
                        for attempt in range(1, MAX_ATTEMPTS + 1)
                    }
                ),
                intent=Text("$item.id"),
            ),
            name="case_evaluation",
            weight=0.0,
        ),
        intent=Text("$case_evaluation"),
    )
    return _reduced_rows(checked, case_count, aggregate_route=SELF_AGGREGATE_ROUTE)


def _member_attempt_input(attempt: int) -> str:
    if attempt == 1:
        return "$question"
    return (
        "$question"
        f" | Your previous answer: $previous_answer_{attempt}"
        f" | Judge feedback: $judge_feedback_{attempt - 1}.output"
        f" | {RETRY_INSTRUCTION}"
    )


def _member_round(collection: Node, attempt: int) -> Node:
    """Run one attempt over a runtime-sized collection of direct member expressions.

    Think of it as one exam sitting for the whole team: every member writes an
    answer, every answer is graded, and the round's output is one validated record
    per member. Per member ($item), in execution order:

    1. (attempts >= 2 only) Fetch THIS member's previous answer from the prior
       round by its stable letter key — each member retries its own work, not a
       teammate's.
    2. The member model answers (`member_answer_k`) — attempt 1 sees the bare
       question; later attempts see question + own previous answer + judge feedback.
    3. The deterministic checker grades the answer (`member_check_k`).
    4. The check record is sanitized into feedback text (`member_feedback_k`) —
       "PASSED" or a violations sentence; this string is what the gates read.
    5. Everything is packed into one validated member record (`member_record_k`):
       identity (key/name/kind/expression) + answer + finish_reason + feedback.

    The iterate returns the array of stage-5 records — the round the gate, select,
    and next round all consume.
    """

    answer = f"member_answer_{attempt}"
    check = f"member_check_{attempt}"
    feedback = f"member_feedback_{attempt}"
    record = f"member_record_{attempt}"
    sources = []
    if attempt > 1:
        # Stage 1 — this member's OWN previous answer, fetched by its letter key.
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
            # Stage 2 — the member model answers.
            src(
                candidate(
                    _member_attempt_input(attempt),
                    binding="$item.expression",
                    web_search=False,
                ),
                name=answer,
                weight=0.0,
            ),
            # Stage 3 — the checker grades; Stage 4 — the record becomes feedback text.
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
            # Stage 5 — one validated member record: identity + answer + feedback.
            src(
                RelExpr(
                    path=MEMBER_RECORD_ROUTE,
                    context=_endpoint_payload(
                        {
                            "key": "$item.key",
                            "name": "$item.name",
                            "kind": "$item.kind",
                            "expression": "$item.expression",
                            "answer": f"${check}.answer",
                            "finish_reason": f"${check}.finish_reason",
                            "refusal": f"${check}.refusal",
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


def _tie_break(attempt: int) -> tuple:
    """0-or-1 judge tie-break: the gate emits a payload only for >=2 passers (or an
    exact never-pass satisfaction tie on the final attempt)."""

    gate = src(
        RelExpr(
            path=LANL_GATE_ROUTE,
            context=f"$member_round_{attempt}",
            intent=Text(f"tie:$case_id:{attempt}"),
        ),
        name=f"tie_gate_{attempt}",
        weight=0.0,
    )
    pick = src(
        iterate(
            ref(f"tie_gate_{attempt}"),
            body=(
                src(
                    candidate(
                        _structured_context(
                            {
                                "request": "$question",
                                "task": LANL_TIE_BREAK_INSTRUCTION,
                                "candidates": "$item.candidates",
                            }
                        ),
                        binding=SYNTHESIZER_BINDING,
                        web_search=False,
                    ),
                    name=f"tie_reply_{attempt}",
                    weight=0.0,
                ),
            ),
            intent=Text(f"$tie_reply_{attempt}"),
            on_error="fail",
        ),
        name=f"tie_pick_{attempt}",
        weight=0.0,
    )
    return gate, pick


def _attempt_sources(attempt: int) -> list:
    """The post-round half of one executed attempt (the round itself is a sibling).

    Given `member_round_k` already ran, in execution order:

    1. Tie gate + gated judge pick (`_tie_break`) — a 0-or-1-item collection; the
       judge model runs ONLY when the gate emits a payload (>=2 passers, or an
       exact never-pass satisfaction tie on the final attempt).
    2. Select (`selection_k`) — a deterministic endpoint picks the attempt's
       representative answer VERBATIM: the lone passer, the judge's letter among
       passers, or the maximal-satisfaction fallback.
    3. Re-check (`check_k`) — the selected answer is graded again to become the
       attempt's grading record for Aggregation (see the module docstring's
       KNOWN JITTER note on why this re-check can rarely disagree with stage 1's
       inputs on two official rows).
    """

    # Stage 1 — tie gate + gated judge pick.
    sources = list(_tie_break(attempt))
    sources.extend(
        (
            # Stage 2 — deterministic verbatim selection of the representative answer.
            src(
                RelExpr(
                    path=LANL_SELECT_ROUTE,
                    # WHY _endpoint_payload: the select endpoint _json_payload()s its
                    # context, so it must arrive as a bare JSON object — the named
                    # `payload=` wrapper resolves to a labeled section ("payload: {…}"),
                    # which is model-prompt formatting, not JSON.
                    context=_endpoint_payload(
                        {
                            "round": f"$member_round_{attempt}",
                            "tie": f"$tie_pick_{attempt}",
                        }
                    ),
                    intent=Text(f"$case_id:{attempt}"),
                ),
                name=f"selection_{attempt}",
                weight=0.0,
            ),
            # Stage 3 — re-check the selection: this record is what Aggregation scores.
            src(
                RelExpr(
                    path=CHECK_ROUTE,
                    context=f"$selection_{attempt}",
                    intent=Text(f"$case_id:{attempt}"),
                ),
                name=f"check_{attempt}",
                weight=0.0,
            ),
        )
    )
    return sources


def _gated_continuation(attempt: int) -> tuple:
    """Sources for the 0-or-1-item continuation into `attempt`.

    Think of it as an IF statement built from a loop that runs 0 or 1 times: the
    gate endpoint returns [] (stop — someone passed, or the budget is spent) or
    one payload (continue), and the retry work lives in an `iterate` over that
    array, so "skip" means the subtree literally never executes.

    In execution order, when the gate emits a payload:

    1. Judge feedback (`judge_feedback_{k-1}`) — a model call reached ONLY here,
       which is what makes it true that feedback is authored solely for a no-pass
       round.
    2. The next member round (`member_round_k`) — every member retries.
    3. The attempt's select + re-check (`_attempt_sources`).
    4. Recursion: the continue-gate into attempt k+1 (until MAX_ATTEMPTS), then
       the outcome struct {check, next} the envelope route later flattens into
       consecutive attempts.

    The gate call is a NAMED source (references in a collection-position call are
    not substituted — the gate must be resolved as an ordinary sibling first), and
    the `iterate` walks that name.
    """

    # The gate: [] = stop (a passer, or budget spent); one payload = continue.
    gate_name = f"continue_gate_{attempt - 1}"
    gate = src(
        RelExpr(
            path=LANL_GATE_ROUTE,
            context=f"$member_round_{attempt - 1}",
            intent=Text(f"continue:$case_id:{attempt - 1}"),
        ),
        name=gate_name,
        weight=0.0,
    )
    body: list = [
        # Stage 1 — judge feedback. The judge authors corrective feedback only on this
        # path: reaching it means the previous round had no passer.
        src(
            candidate(
                _structured_context(
                    {
                        "request": "$question",
                        "task": JUDGE_FEEDBACK_INSTRUCTION,
                        "verdicts": f"$member_round_{attempt - 1}",
                    }
                ),
                binding=SYNTHESIZER_BINDING,
                web_search=False,
            ),
            name=f"judge_feedback_{attempt - 1}",
            weight=0.0,
        ),
        # Stage 2 — every member retries.
        src(_member_round(ref("members"), attempt), name=f"member_round_{attempt}", weight=0.0),
    ]
    # Stage 3 — this attempt's tie-break/select/re-check.
    body.extend(_attempt_sources(attempt))
    # Stage 4 — recurse into the next gated attempt, then emit the outcome. The judge's
    # feedback rides along so the envelope can persist WHAT the members were told —
    # without it the only model-authored step of the loop leaves no trace.
    judge_binding = f"$judge_feedback_{attempt - 1}.output"
    if attempt < MAX_ATTEMPTS:
        body.extend(_gated_continuation(attempt + 1))
        out = struct(
            {"check": f"$check_{attempt}", "judge": judge_binding, "next": f"$next_{attempt}"}
        )
    else:
        out = struct({"check": f"$check_{attempt}", "judge": judge_binding})
    body.append(src(out, name=f"outcome_{attempt}", weight=0.0))
    continuation = iterate(
        ref(gate_name),
        body=tuple(body),
        intent=Text(f"$outcome_{attempt}"),
        on_error="fail",
    )
    return gate, src(continuation, name=f"next_{attempt - 1}", weight=0.0)


def _build_lanl(case_count: int) -> Node:
    """One case: attempt 1 always runs; attempts 2..3 sit behind continue-gates.

    Think of it as a quiz team with an early buzzer: everyone answers, and the
    moment any answer passes the machine check, the case is over. Per case, in
    execution order:

    1. Resolve members ONCE per run (`members`) — validates the 2..4 member
       bindings and the synthesizer against declared Model routes.
    2. Bind `question` / `case_id` from the case row.
    3. `member_round_1` — every member answers and is checked (N model calls).
    4. Attempt 1's tie-break/select/re-check (`_attempt_sources(1)`).
    5. `_gated_continuation(2)` — attempts 2..3, each behind a continue-gate that
       returns [] once any member passed or the budget is spent.
    6. The envelope route flattens {attempt_1, next} into consecutive attempt
       records; the aggregate route scores every case on its earliest strict pass.

    Worked cost example (N = 3 members): a case whose round 1 has exactly one
    passer costs 3 model calls total — no judge, no retries. Two passers: 3 + 1
    tie-break judge call. fail/fail/pass: 3 rounds x 3 members + 2 judge-feedback
    calls = 11 (+1 if the passing round needs a tie-break). Never-pass: 11, +1
    judge call only on an exact satisfaction tie. This early-exit shape is the
    paper's cost story — checker verdicts are free; model calls are not.
    """

    # Stage 1 — resolve and validate the member/synthesizer bindings once per run.
    resolution = RelExpr(
        path=RESOLVE_CANDIDATE_ROUTE,
        context="$candidate_members",
        intent=Text(SYNTHESIZER_BINDING),
    )
    # INVARIANT: the SDK supplies an ordinary URL4 struct whose fields reference ordinary
    # `candidate_member_N` bindings. Resolution validates and canonicalizes those expressions
    # once before any row can invoke a member; it never chooses or defaults a Judge.
    members = src(resolution, name="members", weight=0.0)

    sources: list = [
        # Stage 2 — bind the case row's question and id.
        src("$item.input", name="question", weight=0.0),
        src("$item.id", name="case_id", weight=0.0),
        # Stage 3 — round 1: every member answers and is checked.
        src(_member_round(ref("members"), 1), name="member_round_1", weight=0.0),
    ]
    # Stage 4 — attempt 1's tie-break/select/re-check.
    sources.extend(_attempt_sources(1))
    # Stage 5 — attempts 2..3 behind continue-gates.
    sources.extend(_gated_continuation(2))
    # Stage 6 — flatten the gated chain into one Case Evaluation envelope.
    sources.append(
        src(
            RelExpr(
                path=LANL_ENVELOPE_ROUTE,
                # WHY _endpoint_payload: the envelope route _json_payload()s its
                # context — same bare-JSON contract as the select endpoint above.
                context=_endpoint_payload({"attempt_1": "$check_1", "next": "$next_1"}),
                intent=Text("$case_id"),
            ),
            name="case_evaluation",
            weight=0.0,
        )
    )
    checked = expr(*sources, intent=Text("$case_evaluation"))
    return _reduced_rows(
        checked,
        case_count,
        aggregate_route=LANL_AGGREGATE_ROUTE,
        row_bindings=(members,),
    )


def _reduced_rows(
    checked: Node,
    case_count: int,
    *,
    aggregate_route: str,
    row_bindings: tuple[Node, ...] = (),
) -> Node:
    # INVARIANT: both shapes emit exactly one exact Case Evaluation per row (solo packs
    # attempt-tagged check records; lanl packs the gated chain via its envelope route),
    # so the Aggregator never has to discover grading records inside arbitrary text.
    return build_evaluation_protocol(
        cases_route=CASES_ROUTE,
        case_evaluation=checked,
        selected_case_count=case_count,
        available_case_count=CASE_COUNT,
        aggregate_route=aggregate_route,
        bindings=row_bindings,
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

IFEVAL_LANL_ENSEMBLE = Benchmark(
    id=LANL_ENSEMBLE_ID,
    variant="lanl-ensemble",
    title="IFEval LANL Early-Exit Ensemble",
    description=(
        "A reproduction of the Skurikhin et al. agentic-ensemble protocol "
        "(https://openreview.net/forum?id=XSIYfTm2h7): every Fusion member answers, the "
        "deterministic checker verifies each draft, and a strict pass STOPS the case — "
        "the synthesizer judge only tie-breaks between multiple passers, authors "
        "corrective feedback only when nobody passed, and retries are bounded at three "
        "attempts. A case that never passes selects the maximally-satisfying member "
        "answer. Selected answers are always a member answer verbatim. The paper's "
        "judge prompts are unpublished; this Variant's own prompts are revision inputs."
    ),
    revision=LANL_ENSEMBLE_REVISION,
    case_count=CASE_COUNT,
    build=_build_lanl,
    install=install_ifeval,
)

__all__ = [
    "IFEVAL_LANL_ENSEMBLE",
    "IFEVAL_SELF_CORRECTIVE",
    "MAX_ATTEMPTS",
    "MAX_MEMBERS",
    "MEMBER_LETTERS",
    "MIN_MEMBERS",
    "PROSE_CONSTANTS",
]
