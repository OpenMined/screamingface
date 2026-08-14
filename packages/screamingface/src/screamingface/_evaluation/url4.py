"""Replay one complete ScreamingFace evaluation URL4 without recompiling it."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from url4 import Expression, RelExpr, Source, Text, build

from screamingface._core.ports import AsyncRunTransport, SyncRunTransport
from screamingface._evaluation.model import (
    Candidate,
    _canonical_url4,
    _compiled_candidate,
    _compiled_operation,
    _member_projection,
)
from screamingface._evaluation.results import report_from_url4_outcome
from screamingface._evaluation.topology import (
    _RecipeTopology,
    _topology_bindings,
    _topology_from_expression,
)
from screamingface.events import Event
from screamingface.report import Report

_REFERENCE = re.compile(r"\$(model_\d+|synthesis_\d+)")


def evaluate_url4_sync(
    transport: SyncRunTransport,
    url4: str,
    on_event: Callable[[Event], None] | None,
    progress: bool | None,
) -> Report:
    """Execute one already-linked evaluation expression unchanged."""

    from screamingface._evaluation.runner import (
        _close_event_observer,
        _evaluation_options,
        _sync_event_observer,
    )

    _evaluation_options(on_event, progress)
    candidate = _candidate_from_url4(url4)
    observer = _sync_event_observer(
        on_event,
        progress,
        1,
        "URL4 replay",
        candidate_models=candidate.models,
        candidate_urls=(candidate.url4,),
    )
    try:
        outcome = transport.run(candidate, observer)
    except BaseException:
        _close_event_observer(observer)
        raise
    return report_from_url4_outcome(candidate, outcome)


async def evaluate_url4_async(
    transport: AsyncRunTransport,
    url4: str,
    on_event: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
) -> Report:
    """Asynchronously execute one already-linked evaluation expression unchanged."""

    from screamingface._evaluation.runner import (
        _async_event_observer,
        _close_event_observer,
        _evaluation_options,
    )

    _evaluation_options(on_event, progress)
    candidate = _candidate_from_url4(url4)
    observer = _async_event_observer(
        on_event,
        progress,
        1,
        "URL4 replay",
        candidate_models=candidate.models,
        candidate_urls=(candidate.url4,),
    )
    try:
        outcome = await transport.run(candidate, observer)
    except BaseException:
        _close_event_observer(observer)
        raise
    return report_from_url4_outcome(candidate, outcome)


def _candidate_from_url4(value: str) -> Candidate:
    """Recover the Candidate projection embedded by the ScreamingFace linker.

    The benchmark owns the outer expression. Its zero-weight ``candidate`` binding
    carries the independently compiled Candidate expression as text, which is the
    stable seam needed to rebuild Report metadata without changing the URL4 that runs.
    """

    url4 = _canonical_url4(value, "Evaluation")
    root = build(url4)
    candidate_text = _candidate_text(root)
    candidate = build(candidate_text)
    if not isinstance(candidate, Expression) or not isinstance(candidate.intent, Text):
        raise ValueError("Evaluation URL4 contains an invalid embedded Candidate expression")

    _reject_corrective_replay(candidate)
    calls = _candidate_calls(candidate)
    final = _final_binding(candidate.intent.value, calls)
    selected = _dependency_closure(final, calls)
    topology = _topology_from_expression(candidate)
    return _candidate_from_topology(url4, topology, calls, final, selected)


def _reject_corrective_replay(candidate: Expression) -> None:
    """Refuse corrective-loop artifacts with a named reason, not a shape error.

    WHY: the flat call scan below cannot see the model calls a loop nests inside
    its gated `iterate` bodies, so replay validation would report a misleading
    topology mismatch. Extending replay to gated candidates is follow-up work;
    until then the refusal names the actual limitation. A malformed topology
    falls through to the ordinary validation path unchanged.
    """

    try:
        topology = _topology_from_expression(candidate)
    except ValueError:
        return
    if topology.kind in {"corrective_loop", "self_corrective"}:
        raise ValueError(
            "Evaluation URL4 contains a corrective-loop Candidate; URL4 replay does "
            "not support gated corrective candidates yet — re-run the evaluation "
            "from its Recipe instead"
        )


def _candidate_from_topology(
    url4: str,
    topology: _RecipeTopology,
    calls: dict[str, tuple[str, tuple[str, ...]]],
    final: str,
    selected: set[str],
) -> Candidate:
    bindings = _topology_bindings(topology)
    if topology.binding != final or set(bindings) != set(calls):
        raise ValueError("Evaluation URL4 Recipe topology does not match its model calls")
    # INVARIANT: the inert topology metadata must agree with the executable calls —
    # each call's parsed `$`-references equal the walker's context dependencies.
    for name, (_, context_dependencies) in calls.items():
        if bindings[name].context_dependencies != context_dependencies:
            raise ValueError("Evaluation URL4 Recipe topology does not match its model calls")
    fusion_names = _direct_fusion_output_names(topology)
    operations = tuple(
        _compiled_operation(
            id=f"op_{name}",
            kind=bindings[name].node.role or "model",
            label=(
                f"{fusion_names.get(name, bindings[name].node.name)} "
                f"{'synthesis' if bindings[name].node.role == 'synthesis' else 'answer'}"
            ),
            depends_on=tuple(
                f"op_{dependency}" for dependency in bindings[name].operation_dependencies
            ),
        )
        for name in calls
        if name in selected
    )
    members = (
        tuple(
            _member_projection(
                operation_id=f"op_{member.binding}",
                name=member.name,
                kind=member.kind,
                models=_models(member.binding, calls),
            )
            for member in topology.members
        )
        if topology.kind == "fusion"
        else ()
    )
    return _compiled_candidate(
        name=topology.name,
        kind=topology.kind,
        models=_models(final, calls),
        url4=url4,
        operations=operations,
        members=members,
    )


def _direct_fusion_output_names(value: _RecipeTopology) -> dict[str, str]:
    selected: dict[str, str] = {}

    def visit(node: _RecipeTopology) -> None:
        if node.kind == "model":
            return
        children = node.stages if node.kind == "pipeline" else node.members
        for child in children:
            visit(child)
        if node.synthesizer is not None:
            visit(node.synthesizer)
            if node.synthesizer.kind == "model":
                selected[node.binding] = node.name

    visit(value)
    return selected


def _candidate_text(root: object) -> str:
    if isinstance(root, Expression):
        for node in root.sources:
            if (
                isinstance(node, Source)
                and node.name == "candidate"
                and isinstance(node.value, Text)
            ):
                return node.value.value
    raise ValueError(
        "Evaluation URL4 must contain the embedded `candidate` recipe produced by ScreamingFace"
    )


def _candidate_calls(candidate: Expression) -> dict[str, tuple[str, tuple[str, ...]]]:
    calls: dict[str, tuple[str, tuple[str, ...]]] = {}
    for node in candidate.sources:
        if not isinstance(node, Source) or not isinstance(node.value, RelExpr):
            continue
        name = node.name
        if name is None or not re.fullmatch(r"(?:model|synthesis)_\d+", name):
            continue
        dependencies = tuple(dict.fromkeys(_REFERENCE.findall(node.value.context or "")))
        calls[name] = (node.value.path.removeprefix("/"), dependencies)
    if not calls:
        raise ValueError("Evaluation URL4 contains no executable Candidate model calls")
    return calls


def _final_binding(intent: str, calls: dict[str, tuple[str, tuple[str, ...]]]) -> str:
    match = re.fullmatch(r"\$(model_\d+|synthesis_\d+)", intent)
    if match is None or match.group(1) not in calls:
        raise ValueError("Evaluation URL4 Candidate has an unsupported result binding")
    return match.group(1)


def _dependency_closure(
    name: str,
    calls: dict[str, tuple[str, tuple[str, ...]]],
) -> set[str]:
    selected: set[str] = set()

    def visit(current: str) -> None:
        if current in selected:
            return
        if current not in calls:
            raise ValueError(f"Evaluation URL4 Candidate references unknown binding {current!r}")
        for dependency in calls[current][1]:
            visit(dependency)
        selected.add(current)

    visit(name)
    return selected


def _models(
    name: str,
    calls: dict[str, tuple[str, tuple[str, ...]]],
) -> tuple[str, ...]:
    selected = _dependency_closure(name, calls)
    return tuple(dict.fromkeys(route for key, (route, _) in calls.items() if key in selected))


__all__: list[str] = []
