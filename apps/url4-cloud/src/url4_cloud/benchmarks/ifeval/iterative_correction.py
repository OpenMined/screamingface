"""Shape-adaptive corrective IFEval: self-correction for solos, a verifying ensemble for Fusions.

One Benchmark id, one revision, two candidate shapes:

- solo (no member bindings): the Candidate answers, the deterministic checker reports
  violations, the Candidate AUTHORS ITS OWN feedback and retries — the {solo + loop}
  ablation that Skurikhin et al., "Beyond Leaderboards: Tokenomics of Agentic Small
  Language Model Ensembles" (LANL, https://openreview.net/forum?id=XSIYfTm2h7), never ran.
- ensemble (2..4 direct Model members): Skurikhin et al.'s verifying ensemble. Every member
  draft is checked individually; the Candidate's SYNTHESIZER acts as JUDGE — it authors
  the corrective feedback when nobody passes and tie-breaks among passers otherwise. The
  selection is a member's answer VERBATIM (deterministic select route), so the judge can
  never break a constraint a member satisfied. The judge belongs to the system under
  test, as in the source study — its [Ens-1] and [Ens-2] configurations share members
  and differ only in the judge model.

Both shapes emit one attempt-tagged selection/check record per attempt, so one
aggregation (earliest strict pass, pass@attempt) covers them.
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

BENCHMARK_ID = "ifeval-iterative-correction"
MAX_ATTEMPTS = 3
MIN_MEMBERS = 2
MAX_MEMBERS = 4
MEMBER_LETTERS = "abcd"
PROTOCOL_REVISION = "shape-adaptive-iterative-correction-v1"

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

# WHY every prose constant and shape bound is a hash input: they define the protocol.
# Changing any of them changes what a score means, so it must change the exam identity.
REVISION = hashlib.sha256(
    "\n".join(
        (
            IFEVAL_REVISION,
            PROTOCOL_REVISION,
            str(MAX_ATTEMPTS),
            str(MIN_MEMBERS),
            str(MAX_MEMBERS),
            RETRY_INSTRUCTION,
            SELF_FEEDBACK_INSTRUCTION,
            JUDGE_FEEDBACK_INSTRUCTION,
            JUDGE_PICK_INSTRUCTION,
        )
    ).encode()
).hexdigest()[:16]
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"
SELECT_ROUTE = f"{ROUTE_PREFIX}/select"
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
    return _rows(attempts, case_count)


def _member_binding(member: int) -> str:
    return f"$candidate_model_member_{member}"


def _member_attempt_input(member: int, attempt: int) -> str:
    if attempt == 1:
        return "$item.input"
    previous = attempt - 1
    return (
        "$item.input"
        f" | Your previous answer: $member_{member}_answer_{previous}"
        f" | Judge feedback: $judge_feedback_{previous}"
        f" | {RETRY_INSTRUCTION}"
    )


def build_members(case_count: int, members: int) -> Node:
    """Iterative-correction ensemble loop: members answer, each is checked, the synthesizer
    judges — tie-breaking among passers (selected answer returned verbatim) or, when
    nobody passes, turning the checker's violations into corrective feedback for the
    next attempt. At most MAX_ATTEMPTS rounds; earliest strict pass scores.

    Recreates Skurikhin et al., "Beyond Leaderboards: Tokenomics of Agentic Small
    Language Model Ensembles" (https://openreview.net/forum?id=XSIYfTm2h7).
    """

    if not MIN_MEMBERS <= members <= MAX_MEMBERS:
        raise ValueError(
            f"ifeval-iterative-correction takes {MIN_MEMBERS}..{MAX_MEMBERS} direct members"
            f" — got {members}"
        )
    letters = MEMBER_LETTERS[:members]
    sources = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for member in range(1, members + 1):
            answer = f"member_{member}_answer_{attempt}"
            sources.extend(
                (
                    src(
                        candidate(
                            _member_attempt_input(member, attempt),
                            binding=_member_binding(member),
                            web_search=False,
                        ),
                        name=answer,
                        weight=0.0,
                    ),
                    src(
                        RelExpr(
                            path=CHECK_ROUTE,
                            context=f"${answer}",
                            intent=Text(f"$item.id:{attempt}"),
                        ),
                        name=f"member_{member}_check_{attempt}",
                        weight=0.0,
                    ),
                    src(
                        RelExpr(
                            path=CHECK_ROUTE,
                            context=f"$member_{member}_check_{attempt}",
                            intent=Text("feedback"),
                        ),
                        name=f"member_{member}_feedback_{attempt}",
                        weight=0.0,
                    ),
                )
            )

        # the judge is part of the SYSTEM under test (Skurikhin et al. vary it per ensemble),
        # so it comes from the Candidate — the exam pins only the prompts and rules.
        sources.append(
            src(
                candidate(
                    _judge_pick_input(letters, attempt),
                    binding=SYNTHESIZER_BINDING,
                    web_search=False,
                ),
                name=f"judge_pick_{attempt}",
                weight=0.0,
            )
        )
        sources.append(
            src(
                RelExpr(
                    path=SELECT_ROUTE,
                    context=_select_payload(letters, attempt),
                    intent=Text("select"),
                ),
                name=f"selection_{attempt}",
                weight=0.0,
            )
        )
        sources.append(
            src(
                RelExpr(
                    path=CHECK_ROUTE,
                    context=f"$selection_{attempt}",
                    intent=Text(f"$item.id:{attempt}"),
                ),
                name=f"selection_check_{attempt}",
                weight=0.0,
            )
        )
        if attempt < MAX_ATTEMPTS:
            # WHY judge-authored feedback: in the reproduced protocol the judge
            # converts checker violations into natural-language coaching for the
            # members. Inputs are the sanitized feedback texts only — instruction
            # ids never reach any model.
            sources.append(
                src(
                    candidate(
                        _judge_feedback_input(letters, attempt),
                        binding=SYNTHESIZER_BINDING,
                        web_search=False,
                    ),
                    name=f"judge_feedback_{attempt}",
                    weight=0.0,
                )
            )
    return _rows(sources, case_count, letters=letters)


def _judge_pick_input(letters: str, attempt: int) -> str:
    return _structured_context(
        {
            "request": "$item.input",
            "task": JUDGE_PICK_INSTRUCTION,
            "candidates": {
                letter: {
                    "answer": f"$member_{index}_answer_{attempt}",
                    "verdict": f"$member_{index}_feedback_{attempt}",
                }
                for index, letter in enumerate(letters, 1)
            },
        }
    )


def _judge_feedback_input(letters: str, attempt: int) -> str:
    return _structured_context(
        {
            "request": "$item.input",
            "task": JUDGE_FEEDBACK_INSTRUCTION,
            "verdicts": {
                letter: f"$member_{index}_feedback_{attempt}"
                for index, letter in enumerate(letters, 1)
            },
        }
    )


def _select_payload(letters: str, attempt: int) -> str:
    return _endpoint_payload(
        {
            "pick": f"$judge_pick_{attempt}",
            **{
                letter: f"$member_{index}_answer_{attempt}"
                for index, letter in enumerate(letters, 1)
            },
            **{
                f"f{letter}": f"$member_{index}_feedback_{attempt}"
                for index, letter in enumerate(letters, 1)
            },
        }
    )


def _rows(sources: list, case_count: int, *, letters: str | None = None) -> Node:
    # INVARIANT: both shapes emit exactly one attempt-tagged check record per attempt
    # (solo: the answer's check; ensemble: the selection's check), so ONE aggregation
    # scores both — earliest strict pass, pass@attempt telemetry preserved.
    record = "check" if letters is None else "selection_check"
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
            RelExpr(path=AGGREGATE_ROUTE, context="$rows", intent=Text("aggregate")),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )


def _structured_context(value: dict[str, object]) -> str:
    return render(src(struct(value), name="payload"))


def _endpoint_payload(value: dict[str, object]) -> str:
    return render(struct(value))


IFEVAL_ITERATIVE_CORRECTION = Benchmark(
    id=BENCHMARK_ID,
    family=IFEVAL.family,
    variant="iterative-correction",
    title="IFEval Iterative Correction",
    description=(
        "IFEval with a bounded three-attempt correction protocol that adapts to the "
        "Candidate shape. A solo Model self-corrects: it reads the deterministic "
        "checker's violations, authors its own feedback, and retries. A Fusion runs the "
        "verifying ensemble of Skurikhin et al. (LANL): every member draft is checked "
        "individually and the Fusion's synthesizer acts as JUDGE — it tie-breaks among "
        "passing answers (returned verbatim, never rewritten) and authors corrective "
        "feedback when nobody passes. The synthesizer BLENDS on 'ifeval' but JUDGES "
        "here. Scores are not comparable to canonical single-pass IFEval numbers."
    ),
    revision=REVISION,
    case_count=CASE_COUNT,
    required_models=(),
    build=_build_solo,
    member_build=build_members,
    install=install_family,
)

__all__ = [
    "IFEVAL_ITERATIVE_CORRECTION",
    "MAX_ATTEMPTS",
    "MAX_MEMBERS",
    "MEMBER_LETTERS",
    "MIN_MEMBERS",
    "PROSE_CONSTANTS",
]
