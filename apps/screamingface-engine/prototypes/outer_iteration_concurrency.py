"""PROTOTYPE: does outer ``iteration.concurrency=1`` finish one Case at a time?

This intentionally exercises the real shared Benchmark protocol and URL4 scheduler.
It records Case endpoint starts/finishes and Aggregation so we can distinguish
whole-Case serialization from merely serial collection admission.

Run from ``apps/screamingface-engine`` with:

    uv run python prototypes/outer_iteration_concurrency.py
"""

from __future__ import annotations

import asyncio
import json

from screamingface_engine.benchmarks.protocol import build_evaluation_protocol
from url4 import RelExpr, Text, expr, render, src, struct
from url4.peer.server import Request, Url4Node


async def main() -> None:  # noqa: PLR0915 - linear timeline keeps the proof auditable
    node = Url4Node("outer-iteration-concurrency-prototype")
    node.data(
        "/prototype/cases",
        json.dumps(
            [
                {"id": "case-1", "delay_ms": 30},
                {"id": "case-2", "delay_ms": 20},
                {"id": "case-3", "delay_ms": 10},
            ]
        ),
        media_type="application/json",
    )

    active_cases: set[str] = set()
    max_active_cases = 0
    active_inner_branches = 0
    max_active_inner_branches = 0
    timeline: list[str] = []

    @node.endpoint("/prototype/case-branch")
    async def case_branch(request: Request) -> str:
        nonlocal active_inner_branches, max_active_cases, max_active_inner_branches
        case = json.loads(request.context)
        active_cases.add(case["id"])
        active_inner_branches += 1
        max_active_cases = max(max_active_cases, len(active_cases))
        max_active_inner_branches = max(max_active_inner_branches, active_inner_branches)
        timeline.append(
            f"start {case['id']} branch {request.intent} "
            f"(Cases={len(active_cases)}, inner={active_inner_branches})"
        )
        branch_delay = case["delay_ms"] + (10 if request.intent == "a" else 0)
        await asyncio.sleep(branch_delay / 1000)
        active_inner_branches -= 1
        timeline.append(
            f"finish {case['id']} branch {request.intent} "
            f"(Cases={len(active_cases)}, inner={active_inner_branches})"
        )
        return request.intent

    @node.endpoint("/prototype/complete-case")
    def complete_case(request: Request) -> str:
        payload = json.loads(request.context)
        active_cases.remove(payload["case_id"])
        timeline.append(f"complete {payload['case_id']} (Cases={len(active_cases)})")
        return json.dumps({"case_id": payload["case_id"], "score": 1.0})

    @node.endpoint("/prototype/aggregate")
    def aggregate(request: Request) -> str:
        timeline.append("aggregate all Case Results")
        return request.context

    case_evaluation = expr(
        src(
            RelExpr(path="/prototype/case-branch", context="$item", intent=Text("a")),
            name="a",
            weight=0.0,
        ),
        src(
            RelExpr(path="/prototype/case-branch", context="$item", intent=Text("b")),
            name="b",
            weight=0.0,
        ),
        src(
            RelExpr(
                path="/prototype/complete-case",
                context=render(struct({"case_id": "$item.id", "a": "$a", "b": "$b"})),
                intent=Text("complete"),
            ),
            name="case_result",
            weight=0.0,
        ),
        intent=Text("$case_result"),
    )
    protocol = build_evaluation_protocol(
        cases_route="/prototype/cases",
        case_evaluation=case_evaluation,
        selected_case_count=3,
        available_case_count=3,
        aggregate_route="/prototype/aggregate",
    )
    expression = render(protocol)
    result = await node.evaluate(expression)

    assert "iteration.concurrency=1" in expression
    assert max_active_cases == 1
    assert max_active_inner_branches == 2

    print("Question: does the outer iteration serialize each complete Case evaluation?")
    print(f"Directive rendered: {'iteration.concurrency=1' in expression}")
    for event in timeline:
        print(f"  {event}")
    print(f"Maximum simultaneously active Cases: {max_active_cases}")
    print(f"Maximum parallel branches inside one Case: {max_active_inner_branches}")
    print(f"Final result: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
