"""Three-member verifier-guided IFEval as an Engine-owned Benchmark protocol."""

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
from url4_cloud.benchmarks.ifeval.definition import REVISION as IFEVAL_REVISION

BENCHMARK_ID = "ifeval-corrective-ensemble"
MEMBER_COUNT = 3
MAX_ATTEMPTS = 3
JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"
JUDGE_PARAMS = (("max_tokens", "4096"),)
PROTOCOL_REVISION = "three-member-verifier-guided-selection-v1"
RETRY_TASK = (
    "Your previous answer failed the checker feedback above. Write a completely new answer "
    "to the request that satisfies every stated requirement."
)
JUDGE_PROMPT = (
    "Pick the best candidate answer for the request. Prefer candidates whose verdict is "
    "PASSED. Reply with exactly one letter naming your pick and nothing else."
)

REVISION = hashlib.sha256(
    "\n".join(
        (
            IFEVAL_REVISION,
            PROTOCOL_REVISION,
            str(MEMBER_COUNT),
            str(MAX_ATTEMPTS),
            JUDGE_MODEL,
            repr(JUDGE_PARAMS),
            RETRY_TASK,
            JUDGE_PROMPT,
        )
    ).encode()
).hexdigest()[:16]
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
SELECT_ROUTE = f"{ROUTE_PREFIX}/select"
FINALIZE_ROUTE = f"{ROUTE_PREFIX}/finalize"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"


def _member_binding(member: int) -> str:
    return f"$candidate_model_member_{member}"


def _member_input(member: int, attempt: int) -> str:
    if attempt == 1:
        return "$item.input"
    previous = attempt - 1
    return _structured_context(
        {
            "request": "$item.input",
            "your_previous_answer": f"$member_{member}_answer_{previous}",
            "checker_feedback": f"$member_{member}_feedback_{previous}",
            "task": RETRY_TASK,
        }
    )


def _build(case_count: int) -> Node:
    """Build the exact three-member, three-attempt check/retry/select protocol."""

    sources = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for member in range(1, MEMBER_COUNT + 1):
            answer = f"member_{member}_answer_{attempt}"
            check = f"member_{member}_check_{attempt}"
            sources.extend(
                (
                    src(
                        candidate(
                            _member_input(member, attempt),
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
                        name=check,
                        weight=0.0,
                    ),
                    src(
                        RelExpr(path=CHECK_ROUTE, context=f"${check}", intent=Text("feedback")),
                        name=f"member_{member}_feedback_{attempt}",
                        weight=0.0,
                    ),
                )
            )

        letters = "abc"
        judge = f"judge_{attempt}"
        selection = f"selection_{attempt}"
        selection_check = f"selection_check_{attempt}"
        sources.extend(
            (
                src(
                    RelExpr(
                        path="/" + JUDGE_MODEL,
                        context=_structured_context(
                            {
                                "request": "$item.input",
                                "candidates": {
                                    letter: {
                                        "answer": f"$member_{member}_answer_{attempt}",
                                        "verdict": f"$member_{member}_feedback_{attempt}",
                                    }
                                    for member, letter in enumerate(letters, 1)
                                },
                            }
                        ),
                        intent=Text(JUDGE_PROMPT),
                        params=JUDGE_PARAMS,
                    ),
                    name=judge,
                    weight=0.0,
                ),
                src(
                    RelExpr(
                        path=SELECT_ROUTE,
                        context=_endpoint_payload(
                            {
                                "pick": f"${judge}",
                                **{
                                    letter: f"$member_{member}_answer_{attempt}"
                                    for member, letter in enumerate(letters, 1)
                                },
                            }
                        ),
                        intent=Text("select"),
                    ),
                    name=selection,
                    weight=0.0,
                ),
                src(
                    RelExpr(
                        path=CHECK_ROUTE,
                        context=f"${selection}",
                        intent=Text(f"$item.id:{attempt}"),
                    ),
                    name=selection_check,
                    weight=0.0,
                ),
                src(
                    RelExpr(
                        path=CHECK_ROUTE,
                        context=f"${selection_check}",
                        intent=Text("feedback"),
                    ),
                    name=f"selection_feedback_{attempt}",
                    weight=0.0,
                ),
            )
        )

    final_answer = RelExpr(
        path=FINALIZE_ROUTE,
        context=_endpoint_payload(
            {
                key: value
                for attempt in range(1, MAX_ATTEMPTS + 1)
                for key, value in (
                    (f"s{attempt}", f"$selection_{attempt}"),
                    (f"f{attempt}", f"$selection_feedback_{attempt}"),
                )
            }
        ),
        intent=Text("finalize"),
    )
    sources.extend(
        (
            src(final_answer, name="final_answer", weight=0.0),
            src(
                RelExpr(
                    path=CHECK_ROUTE,
                    context="$final_answer",
                    intent=Text("$item.id"),
                ),
                name="final_check",
                weight=0.0,
            ),
        )
    )
    checked = expr(*sources, intent=Text("$final_check"))
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


IFEVAL_CORRECTIVE_ENSEMBLE = Benchmark(
    id=BENCHMARK_ID,
    family=IFEVAL.family,
    variant="corrective-ensemble",
    title="IFEval Corrective Ensemble",
    description=(
        "IFEval with three Model members independently checked and retried for three attempts. "
        "A pinned Benchmark judge selects one member answer per attempt and deterministic "
        "finalization returns the earliest passing selection."
    ),
    revision=REVISION,
    case_count=CASE_COUNT,
    required_models=(JUDGE_MODEL,),
    build=_build,
    install=install_family,
)

__all__ = ["IFEVAL_CORRECTIVE_ENSEMBLE", "MAX_ATTEMPTS", "MEMBER_COUNT"]
