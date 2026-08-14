"""A first-class, string-compatible ScreamingFace URL4 value."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from url4 import Expression, Iteration, Node, RelExpr, RelUrl, Source, Text, Url4Error, build, walk
from url4.core.nodes import children

from screamingface._evaluation.policy import DEFAULT_ANSWER_PROMPT, DEFAULT_SYNTHESIS_PROMPT
from screamingface._evaluation.topology import _RecipeTopology, _topology_from_expression

_BINDING = re.compile(r"(?:model|synthesis)_\d+")
_REFERENCE = re.compile(r"\$(model_\d+|synthesis_\d+)")
_BENCHMARK_ROUTE = re.compile(
    r"/benchmarks/([A-Za-z0-9._~/-]+?)/"
    r"(?:cases|tasks|aggregate|criterion-verdict|criterion-evaluation|case-evaluation)\b"
)
_INTEGER = re.compile(r"-?(?:0|[1-9]\d*)")
_FLOAT = re.compile(r"-?(?:(?:0|[1-9]\d*)\.\d+|(?:0|[1-9]\d*)[eE][+-]?\d+)")
_NESTED_RECIPE_ROUTES = frozenset(
    {
        "/ensemble/corrective/v1/member",
        "/ensemble/corrective/v1/role",
    }
)
_DEFAULT_CORRECTIVE_ROUNDS = 3


class Url4(str):
    """An immutable URL4 expression that can produce an editable Python fork."""

    def __new__(cls, value: str) -> Url4:
        if not isinstance(value, str):
            raise TypeError("URL4 must be a string")
        if not value.strip():
            raise ValueError("URL4 must be a non-empty string")
        return super().__new__(cls, value)

    def to_python(self) -> str:
        """Return editable ScreamingFace Python for a compiled Candidate or Evaluation."""

        return _to_python(self)


@dataclass(frozen=True, slots=True)
class _Call:
    binding: str
    model: str
    dependencies: tuple[str, ...]
    prompt: str
    params: tuple[tuple[str, str], ...]


def _to_python(value: str) -> str:
    try:
        root = build(value)
    except Url4Error as exc:
        raise ValueError(f"URL4 must be valid URL4: {exc}") from exc
    candidate, linked = _candidate_expression(root)
    calls = _calls(candidate)
    topology = _topology_from_expression(candidate)
    final = _final_binding(candidate, calls, topology)
    _validate_topology(topology, calls, final)
    lines = _render_topology(topology, calls, indent=0)
    lines[0] = f"candidate = {lines[0]}"
    source = ["import screamingface as sf", "", *lines]
    if linked:
        benchmark = _benchmark_id(root)
        if benchmark is not None:
            source.extend(["", *_evaluation_call(benchmark, _limit(root))])
    return "\n".join(source)


def _candidate_expression(root: Node) -> tuple[Expression, bool]:
    if not isinstance(root, Expression):
        raise ValueError("URL4 must contain a compiled ScreamingFace Candidate")
    for node in root.sources:
        if isinstance(node, Source) and node.name == "candidate" and isinstance(node.value, Text):
            try:
                candidate = build(node.value.value)
            except Url4Error as exc:
                raise ValueError("URL4 contains an invalid embedded Candidate") from exc
            if not isinstance(candidate, Expression):
                raise ValueError("URL4 contains an invalid embedded Candidate")
            return candidate, True
    return root, False


def _calls(candidate: Expression) -> dict[str, _Call]:
    calls: dict[str, _Call] = {}
    for node in _executable_nodes(candidate):
        if (
            not isinstance(node, Source)
            or node.name is None
            or _BINDING.fullmatch(node.name) is None
            or not isinstance(node.value, RelExpr)
            or not isinstance(node.value.intent, Text)
        ):
            continue
        context = node.value.context or ""
        dependencies = tuple(dict.fromkeys(_REFERENCE.findall(context)))
        calls[node.name] = _Call(
            binding=node.name,
            model=node.value.path.removeprefix("/"),
            dependencies=dependencies,
            prompt=_python_text(node.value.intent.value),
            params=_params(node.value.params),
        )
    if not calls:
        raise ValueError("URL4 contains no compiled ScreamingFace model calls")
    return calls


def _executable_nodes(value: Node):
    """Walk static nodes plus URL4 bodies carried as executable loop data."""

    yield value
    for child in children(value):
        yield from _executable_nodes(child)
    if isinstance(value, Iteration):
        try:
            if value.intent is None:
                raise ValueError("URL4 Candidate iteration body has no result intent")
            body = build(f"({value.body})!{value.intent}")
        except Url4Error as exc:
            raise ValueError("URL4 Candidate contains an invalid iteration body") from exc
        yield from _executable_nodes(body)
    if (
        isinstance(value, RelExpr)
        and value.path in _NESTED_RECIPE_ROUTES
        and isinstance(value.intent, Text)
    ):
        try:
            nested = build(value.intent.value)
        except Url4Error as exc:
            raise ValueError("URL4 Candidate contains an invalid nested Recipe") from exc
        yield from _executable_nodes(nested)


def _final_binding(
    candidate: Expression,
    calls: dict[str, _Call],
    topology: _RecipeTopology,
) -> str:
    if not isinstance(candidate.intent, Text):
        raise ValueError("URL4 Candidate has an unsupported result binding")
    match = re.fullmatch(r"\$(model_\d+|synthesis_\d+|loop_candidate)", candidate.intent.value)
    if match is None:
        raise ValueError("URL4 Candidate has an unsupported result binding")
    selected = match.group(1)
    if topology.kind in {"corrective_loop", "self_corrective"}:
        if selected != topology.binding or not _has_binding(candidate, selected):
            raise ValueError("URL4 Candidate has an unsupported result binding")
    elif selected not in calls:
        raise ValueError("URL4 Candidate has an unsupported result binding")
    return selected


def _has_binding(value: Expression, name: str) -> bool:
    return any(isinstance(node, Source) and node.name == name for node in value.sources)


def _render_model(
    call: _Call,
    *,
    role: str,
    explicit_name: str | None,
    indent: int,
    force_name: bool = False,
) -> list[str]:
    prefix = " " * indent
    lines = [f"{prefix}sf.Model(", f"{prefix}    {call.model!r},"]
    inferred_name = call.model.rsplit("/", 1)[-1]
    if explicit_name is not None and (force_name or explicit_name != inferred_name):
        lines.append(f"{prefix}    name={explicit_name!r},")
    default_prompt = DEFAULT_SYNTHESIS_PROMPT if role == "synthesis" else DEFAULT_ANSWER_PROMPT
    if call.prompt != default_prompt:
        lines.append(f"{prefix}    prompt={call.prompt!r},")
    params = _editable_params(call)
    if params:
        lines.append(f"{prefix}    params={params!r},")
    lines.append(f"{prefix})")
    return lines


def _render_topology(
    value: _RecipeTopology,
    calls: dict[str, _Call],
    *,
    indent: int,
) -> list[str]:
    if value.kind == "model":
        assert value.role is not None
        lines = _render_model(
            calls[value.binding],
            role=value.role,
            explicit_name=value.name,
            indent=indent,
            force_name=value.named,
        )
    elif value.kind == "pipeline":
        lines = _render_pipeline_topology(value, calls, indent=indent)
    elif value.kind in {"corrective_loop", "self_corrective"}:
        lines = _render_corrective_topology(value, calls, indent=indent)
    else:
        lines = _render_fusion_topology(value, calls, indent=indent)
    return lines


def _render_corrective_topology(
    value: _RecipeTopology,
    calls: dict[str, _Call],
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent
    if value.kind == "self_corrective":
        member = value.members[0]
        lines = [f"{prefix}sf.SelfCorrective("]
        rendered = _render_topology(member, calls, indent=indent + 4)
        rendered[-1] += ","
        lines.extend(rendered)
        if value.name != member.name:
            lines.append(f"{prefix}    name={value.name!r},")
    else:
        assert value.judge is not None
        lines = [f"{prefix}sf.CorrectiveLoop(", f"{prefix}    ["]
        for member in value.members:
            rendered = _render_topology(member, calls, indent=indent + 8)
            rendered[-1] += ","
            lines.extend(rendered)
        lines.append(f"{prefix}    ],")
        inferred_name = "+".join(member.name for member in value.members)
        if value.name != inferred_name:
            lines.append(f"{prefix}    name={value.name!r},")
        judge = _render_topology(value.judge, calls, indent=indent + 4)
        judge[0] = f"{prefix}    judge={judge[0].lstrip()}"
        judge[-1] += ","
        lines.extend(judge)
    if value.max_rounds != _DEFAULT_CORRECTIVE_ROUNDS:
        lines.append(f"{prefix}    max_rounds={value.max_rounds!r},")
    lines.append(f"{prefix})")
    return lines


def _render_pipeline_topology(
    value: _RecipeTopology,
    calls: dict[str, _Call],
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent
    lines = [f"{prefix}sf.Pipeline(", f"{prefix}    ["]
    for stage in value.stages:
        rendered = _render_topology(stage, calls, indent=indent + 8)
        rendered[-1] += ","
        lines.extend(rendered)
    lines.append(f"{prefix}    ],")
    inferred_name = "->".join(stage.name for stage in value.stages)
    if value.named or value.name != inferred_name:
        lines.append(f"{prefix}    name={value.name!r},")
    lines.append(f"{prefix})")
    return lines


def _render_fusion_topology(
    value: _RecipeTopology,
    calls: dict[str, _Call],
    *,
    indent: int,
) -> list[str]:
    assert value.synthesizer is not None
    prefix = " " * indent
    lines = [f"{prefix}sf.Fusion(", f"{prefix}    ["]
    for member in value.members:
        rendered = _render_topology(member, calls, indent=indent + 8)
        rendered[-1] += ","
        lines.extend(rendered)
    lines.append(f"{prefix}    ],")
    inferred_name = "+".join(member.name for member in value.members)
    if value.name != inferred_name:
        lines.append(f"{prefix}    name={value.name!r},")
    synthesizer = _render_topology(value.synthesizer, calls, indent=indent + 4)
    synthesizer[0] = f"{prefix}    synthesizer={synthesizer[0].lstrip()}"
    synthesizer[-1] += ","
    lines.extend(synthesizer)
    lines.append(f"{prefix})")
    return lines


def _validate_topology(
    value: _RecipeTopology,
    calls: dict[str, _Call],
    final: str,
) -> None:
    if value.binding != final:
        raise ValueError("URL4 Candidate Recipe topology does not match its result binding")
    if value.kind in {"corrective_loop", "self_corrective"}:
        expected = set(_topology_model_bindings(value))
        if not expected.issubset(calls):
            raise ValueError("URL4 Candidate Recipe topology does not match its model calls")
        return
    bindings: set[str] = set()
    _validate_topology_node(value, calls, input_dependencies=(), bindings=bindings)
    if bindings != set(calls):
        raise ValueError("URL4 Candidate Recipe topology does not match its model calls")


def _topology_model_bindings(value: _RecipeTopology):
    if value.kind == "model":
        yield value.binding
        return
    if value.kind == "pipeline":
        for stage in value.stages:
            yield from _topology_model_bindings(stage)
        return
    for member in value.members:
        yield from _topology_model_bindings(member)
    if value.kind == "fusion":
        assert value.synthesizer is not None
        yield from _topology_model_bindings(value.synthesizer)
    elif value.kind == "corrective_loop":
        assert value.judge is not None
        yield from _topology_model_bindings(value.judge)


def _validate_topology_node(
    value: _RecipeTopology,
    calls: dict[str, _Call],
    *,
    input_dependencies: tuple[str, ...],
    bindings: set[str],
) -> None:
    if value.kind == "model":
        call = calls.get(value.binding)
        if call is None or call.dependencies != input_dependencies:
            raise ValueError("URL4 Candidate Recipe topology does not match its model calls")
        bindings.add(value.binding)
        return
    if value.kind == "pipeline":
        dependencies = input_dependencies
        for stage in value.stages:
            _validate_topology_node(
                stage,
                calls,
                input_dependencies=dependencies,
                bindings=bindings,
            )
            dependencies = (stage.binding,)
        return
    assert value.synthesizer is not None
    for member in value.members:
        _validate_topology_node(
            member,
            calls,
            input_dependencies=input_dependencies,
            bindings=bindings,
        )
    synthesis_dependencies = tuple(
        dict.fromkeys((*input_dependencies, *(member.binding for member in value.members)))
    )
    _validate_topology_node(
        value.synthesizer,
        calls,
        input_dependencies=synthesis_dependencies,
        bindings=bindings,
    )


def _editable_params(call: _Call) -> dict[str, str | int | float | bool]:
    selected: dict[str, str | int | float | bool] = {}
    for name, value in call.params:
        selected[name] = _scalar(value)
    return selected


def _params(values: tuple[tuple[str, str | None], ...]) -> tuple[tuple[str, str], ...]:
    if any(value is None for _, value in values):
        raise ValueError("URL4 Candidate model parameters must have scalar values")
    return tuple((name, value) for name, value in values if value is not None)


def _scalar(value: str) -> str | int | float | bool:
    selected: str | int | float | bool = value
    if value == "true":
        selected = True
    elif value == "false":
        selected = False
    elif _INTEGER.fullmatch(value):
        selected = int(value)
    elif _FLOAT.fullmatch(value):
        number = float(value)
        if math.isfinite(number):
            selected = number
    return selected


def _python_text(value: str) -> str:
    return value.replace("\u2028", "\n").replace("$$", "$")


def _benchmark_id(root: Node) -> str | None:
    for node in walk(root):
        path = (
            node.path
            if isinstance(node, RelExpr)
            else node.value
            if isinstance(node, RelUrl)
            else None
        )
        if path is None or (match := _BENCHMARK_ROUTE.fullmatch(path)) is None:
            continue
        components = match.group(1).split("/")
        if len(components) >= 2:
            return "/".join(components[:-1])
    return None


def _limit(root: Node) -> int | None:
    for node in walk(root):
        if isinstance(node, Iteration) and node.directives.slice is not None:
            start, stop = node.directives.slice
            if start == 0:
                return stop
    return None


def _evaluation_call(benchmark: str, limit: int | None) -> list[str]:
    lines = ["report = sf.evaluate(", "    candidate,", f"    benchmark={benchmark!r},"]
    if limit is not None:
        lines.append(f"    limit={limit},")
    lines.append(")")
    return lines


__all__ = ["Url4"]
