"""Versioned, inert Recipe topology carried by newly compositional Candidate URL4."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, cast

from url4 import Expression, Node, Source, Text, src

_SCHEMA = "screamingface.recipe.v1"
_SOURCE_NAME = "_sf_recipe"
_BINDING = re.compile(r"(?:model|synthesis)_\d+")
type _TopologyKind = Literal["model", "fusion", "pipeline"]
type _OperationRole = Literal["model", "synthesis"]


@dataclass(frozen=True, slots=True)
class _RecipeTopology:
    """One public Recipe node mapped to its executable result binding."""

    kind: _TopologyKind
    name: str
    binding: str
    named: bool = False
    role: _OperationRole | None = None
    members: tuple[_RecipeTopology, ...] = ()
    synthesizer: _RecipeTopology | None = None
    stages: tuple[_RecipeTopology, ...] = ()


@dataclass(frozen=True, slots=True)
class _TopologyBinding:
    """One executable model call: its leaf node plus both dependency notions."""

    node: _RecipeTopology
    context_dependencies: tuple[str, ...]
    operation_dependencies: tuple[str, ...]


def _topology_bindings(value: _RecipeTopology) -> dict[str, _TopologyBinding]:
    """One walk of a Recipe topology, shared by every consumer.

    Think of it as the topology's dependency rulebook evaluated once: each model
    leaf gets its binding plus TWO dependency tuples, because the same tree carries
    two distinct notions —

    - ``context_dependencies``: which earlier bindings this call's rendered context
      references (a Fusion synthesizer reads the upstream input AND every member's
      answer, deduplicated in that order). Replay validation compares these against
      the ``$``-references parsed out of the executable calls.
    - ``operation_dependencies``: the operation DAG's edges as the compiler records
      them (a Fusion synthesizer depends only on its members — the upstream edge is
      already carried by each member).

    Worked example — ``pipeline(model_1, fusion(members=[model_2], synth))`` where
    the synthesizer executes as ``synthesis_1``: ``model_2`` has context AND
    operation deps ``("model_1",)`` (fusion members inherit the pipeline stage
    input), while ``synthesis_1`` has context deps ``("model_1", "model_2")`` but
    operation deps ``("model_2",)`` only.

    INVARIANT: a new Recipe kind extends THIS walker (one branch), never a fork —
    replay decoding and validation must agree by construction.
    """

    selected: dict[str, _TopologyBinding] = {}

    def visit(
        node: _RecipeTopology,
        context: tuple[str, ...],
        operations: tuple[str, ...],
    ) -> None:
        if node.kind == "model":
            entry = _TopologyBinding(node, context, operations)
            previous = selected.setdefault(node.binding, entry)
            if previous != entry:
                raise ValueError("Evaluation URL4 has conflicting Recipe topology metadata")
            return
        if node.kind == "pipeline":
            stage_context, stage_operations = context, operations
            for stage in node.stages:
                visit(stage, stage_context, stage_operations)
                stage_context = (stage.binding,)
                stage_operations = (stage.binding,)
            return
        for member in node.members:
            visit(member, context, operations)
        assert node.synthesizer is not None
        member_bindings = tuple(member.binding for member in node.members)
        visit(
            node.synthesizer,
            tuple(dict.fromkeys((*context, *member_bindings))),
            member_bindings,
        )

    visit(value, (), ())
    return selected


def _topology_source(value: _RecipeTopology) -> Node:
    return src(Text(_encode_topology(value)), name=_SOURCE_NAME, weight=0.0)


def _topology_from_expression(value: Expression) -> _RecipeTopology:
    matches = [
        node for node in value.sources if isinstance(node, Source) and node.name == _SOURCE_NAME
    ]
    if not matches:
        raise ValueError("URL4 Candidate is missing required Recipe metadata")
    if len(matches) != 1 or not isinstance(matches[0].value, Text):
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata")
    raw = matches[0].value.value
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "recipe"}:
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata")
    if payload["schema"] != _SCHEMA:
        raise ValueError("URL4 Candidate has unsupported Recipe topology metadata")
    try:
        return _decode_node(payload["recipe"])
    except RecursionError as exc:
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata") from exc


def _encode_topology(value: _RecipeTopology) -> str:
    payload = {"schema": _SCHEMA, "recipe": _encode_node(value)}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _encode_node(value: _RecipeTopology) -> dict[str, object]:
    if value.kind == "model":
        assert value.role is not None
        return {
            "binding": value.binding,
            "kind": value.kind,
            "name": value.name,
            "named": value.named,
            "role": value.role,
        }
    if value.kind == "pipeline":
        return {
            "binding": value.binding,
            "kind": value.kind,
            "name": value.name,
            "named": value.named,
            "stages": [_encode_node(stage) for stage in value.stages],
        }
    assert value.synthesizer is not None
    return {
        "binding": value.binding,
        "kind": value.kind,
        "members": [_encode_node(member) for member in value.members],
        "name": value.name,
        "synthesizer": _encode_node(value.synthesizer),
    }


def _decode_node(value: object) -> _RecipeTopology:
    if not isinstance(value, dict):
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata")
    kind = value.get("kind")
    name = _text(value.get("name"))
    binding = _binding(value.get("binding"))
    decoder = {
        "model": _decode_model,
        "pipeline": _decode_pipeline,
        "fusion": _decode_fusion,
    }.get(kind if isinstance(kind, str) else "")
    if decoder is None:
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata")
    return decoder(value, name, binding)


def _decode_model(
    value: dict[object, object],
    name: str,
    binding: str,
) -> _RecipeTopology:
    if set(value) != {"binding", "kind", "name", "named", "role"}:
        raise ValueError("URL4 Candidate has invalid Model topology metadata")
    named = value["named"]
    role = value["role"]
    if not isinstance(named, bool) or role not in {"model", "synthesis"}:
        raise ValueError("URL4 Candidate has invalid Model topology metadata")
    return _RecipeTopology(
        kind="model",
        name=name,
        binding=binding,
        named=named,
        role=cast(_OperationRole, role),
    )


def _decode_pipeline(
    value: dict[object, object],
    name: str,
    binding: str,
) -> _RecipeTopology:
    if set(value) != {"binding", "kind", "name", "named", "stages"}:
        raise ValueError("URL4 Candidate has invalid Pipeline topology metadata")
    named = value["named"]
    stages_value = value["stages"]
    if not isinstance(named, bool) or not isinstance(stages_value, list):
        raise ValueError("URL4 Candidate has invalid Pipeline topology metadata")
    stages = tuple(_decode_node(stage) for stage in stages_value)
    if not stages or binding != stages[-1].binding:
        raise ValueError("URL4 Candidate has invalid Pipeline topology metadata")
    return _RecipeTopology(
        kind="pipeline",
        name=name,
        binding=binding,
        named=named,
        stages=stages,
    )


def _decode_fusion(
    value: dict[object, object],
    name: str,
    binding: str,
) -> _RecipeTopology:
    if set(value) != {"binding", "kind", "members", "name", "synthesizer"}:
        raise ValueError("URL4 Candidate has invalid Fusion topology metadata")
    members_value = value["members"]
    if not isinstance(members_value, list):
        raise ValueError("URL4 Candidate has invalid Fusion topology metadata")
    members = tuple(_decode_node(member) for member in members_value)
    synthesizer = _decode_node(value["synthesizer"])
    if not members or binding != synthesizer.binding:
        raise ValueError("URL4 Candidate has invalid Fusion topology metadata")
    return _RecipeTopology(
        kind="fusion",
        name=name,
        binding=binding,
        members=members,
        synthesizer=synthesizer,
    )


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata")
    return value


def _binding(value: object) -> str:
    selected = _text(value)
    if _BINDING.fullmatch(selected) is None:
        raise ValueError("URL4 Candidate has invalid Recipe topology metadata")
    return selected


__all__: list[str] = []
