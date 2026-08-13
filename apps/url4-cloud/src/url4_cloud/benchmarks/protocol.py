"""URL4 composition capabilities shared by Engine-owned Benchmarks."""

from __future__ import annotations

from url4 import Node, RelExpr, Text, expr, iterate, src
from url4_cloud.benchmarks.evaluation import positive_count

EVALUATION_PROTOCOL_REVISION = "ordered-case-evaluation-v1"


def build_evaluation_protocol(
    *,
    cases_route: str,
    case_evaluation: Node,
    selected_case_count: int,
    available_case_count: int,
    aggregate_route: str,
    bindings: tuple[Node, ...] = (),
) -> Node:
    """Compose ordered Case evaluation and typed Aggregation around one Case node."""

    _route(cases_route, "cases_route")
    _route(aggregate_route, "aggregate_route")
    positive_count(available_case_count, "available_case_count")
    positive_count(selected_case_count, "selected_case_count")
    if selected_case_count > available_case_count:
        raise ValueError("selected_case_count cannot exceed available_case_count")
    if not isinstance(case_evaluation, Node):
        raise TypeError("case_evaluation must be a URL4 Node")
    if any(not isinstance(binding, Node) for binding in bindings):
        raise TypeError("bindings must contain only URL4 Nodes")

    case_evaluations = iterate(
        cases_route,
        body=(src(case_evaluation, name="evaluated", weight=0.0),),
        intent=Text("$evaluated"),
        slice=(None if selected_case_count == available_case_count else (0, selected_case_count)),
        on_error="collect",
    )
    selected_case_evaluations = expr(
        *bindings,
        src(case_evaluations, name="selected_case_evaluations", weight=0.0),
        intent=Text("$selected_case_evaluations"),
    )
    return expr(
        src(selected_case_evaluations, name="case_evaluations", weight=0.0),
        src(
            RelExpr(
                path=aggregate_route,
                context="$case_evaluations",
                intent=Text(f"aggregate:{selected_case_count}"),
            ),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )


def _route(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError(f"{label} must be an absolute URL4 path")
    return value


__all__ = ["EVALUATION_PROTOCOL_REVISION", "build_evaluation_protocol"]
