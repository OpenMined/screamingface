"""Fixed three-attempt corrective IFEval as a distinct Engine-owned Benchmark."""

from __future__ import annotations

import hashlib

from url4 import Node, RelExpr, Text, expr, iterate, src
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

BENCHMARK_ID = "ifeval-corrective"
MAX_ATTEMPTS = 3
PROTOCOL_REVISION = "fixed-three-attempt-corrective-v1"
RETRY_INSTRUCTION = (
    "Write a new answer to the original request. Correct every requirement named in the "
    "verification feedback and return only the new answer."
)

REVISION = hashlib.sha256(
    "\n".join(
        (
            IFEVAL_REVISION,
            PROTOCOL_REVISION,
            str(MAX_ATTEMPTS),
            RETRY_INSTRUCTION,
        )
    ).encode()
).hexdigest()[:16]
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"


def _attempt_input(attempt: int) -> str:
    if attempt == 1:
        return "$item.input"
    previous = attempt - 1
    return (
        "$item.input"
        f" | Previous answer: $answer_{previous}"
        f" | Verification feedback: $feedback_{previous}"
        f" | {RETRY_INSTRUCTION}"
    )


def _build(case_count: int) -> Node:
    """Build three explicit attempts; URL4 currently has no conditional early stop."""

    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts.extend(
            (
                src(
                    candidate(_attempt_input(attempt), web_search=False),
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

    checked = expr(
        *attempts,
        intent=Text(" ".join(f"$check_{attempt}" for attempt in range(1, MAX_ATTEMPTS + 1))),
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


IFEVAL_CORRECTIVE = Benchmark(
    id=BENCHMARK_ID,
    family=IFEVAL.family,
    variant="corrective",
    title="IFEval Corrective",
    description=(
        "IFEval with a fixed three-attempt Engine-owned correction protocol. Every attempt "
        "is verified deterministically; sanitized failures guide the next Candidate Invocation."
    ),
    revision=REVISION,
    case_count=CASE_COUNT,
    required_models=(),
    build=_build,
    install=install_family,
)

__all__ = ["IFEVAL_CORRECTIVE", "MAX_ATTEMPTS"]
