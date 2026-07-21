"""Network-free recursive Fusion authoring plus benchmark orchestration facades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from screamingface.model_inputs import ParameterValue, _FusionMember, _ModelCall, make_model_call
from screamingface.reducers import Reducer

if TYPE_CHECKING:
    from screamingface._progress import ProgressSetting
    from screamingface.benchmark import Benchmark
    from screamingface.report import Report
    from screamingface.run import Run

_DEFAULT_PROMPT = "Answer the question."


@dataclass(frozen=True, slots=True, init=False)
class Fusion:
    """A shareable answer recipe backed by one model or composed from input Fusions."""

    name: str
    model: str | None
    prompt: str | None
    reducer: Reducer | None
    inputs: tuple[str | Fusion, ...]
    _parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)

    def __init__(
        self,
        name: str,
        *,
        model: str | None = None,
        inputs: Sequence[str | Fusion] | None = None,
        reducer: Reducer | None = None,
        prompt: str | None = None,
        params: Mapping[str, ParameterValue] | None = None,
    ) -> None:
        normalized_name = _name(name)
        if (model is None) == (inputs is None):
            raise ValueError("a Fusion requires exactly one of model or inputs")
        if model is not None:
            call = _atomic_call(model, prompt, params, reducer)
            values: tuple[str | Fusion, ...] = ()
            normalized_reducer = None
        else:
            values = _composite_inputs(inputs)
            normalized_reducer = _composite_reducer(reducer)
            if prompt is not None:
                raise ValueError("a composite Fusion cannot define prompt; configure atomic inputs")
            if params is not None:
                raise ValueError("a composite Fusion cannot define params; configure atomic inputs")
            call = None

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "model", None if call is None else call.model)
        object.__setattr__(self, "prompt", None if call is None else call.prompt)
        object.__setattr__(self, "reducer", normalized_reducer)
        object.__setattr__(self, "inputs", values)
        object.__setattr__(
            self,
            "_parameter_items",
            () if call is None else call.parameter_items,
        )
        _validate_graph(self)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self._parameter_items)

    @property
    def model_ids(self) -> tuple[str, ...]:
        """Atomic model routes in deterministic first-use order."""

        models: list[str] = []
        seen: set[int] = set()
        _collect_models(self, models, seen)
        return tuple(models)

    @property
    def _members(self) -> tuple[_FusionMember, ...]:
        """Atomic leaves in stable first-execution order."""

        members: list[_FusionMember] = []
        _collect_members(self, members, set())
        return tuple(members)

    @property
    def _reducers(self) -> tuple[Reducer, ...]:
        reducers: list[Reducer] = []
        _collect_reducers(self, reducers, set())
        return tuple(reducers)

    @property
    def url4(self) -> str:
        """Canonical parameterized URL4 recipe with an unbound ``$question``."""

        from screamingface._compiler import compile_fusion

        return compile_fusion(self)

    def run(
        self,
        benchmark: str | Benchmark,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Run:
        """Run selected benchmark cases through only the configured URL4 engine."""

        from screamingface._execution import run_fusion

        return run_fusion(self, benchmark, first=first, progress=progress)

    def evaluate(
        self,
        benchmark: str | Benchmark,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Report:
        """Preflight the complete requirement union, then run, grade, and aggregate."""

        from screamingface._execution import evaluate_fusion

        return evaluate_fusion(self, benchmark, first=first, progress=progress)


def _atomic_call(
    model: str,
    prompt: str | None,
    params: Mapping[str, ParameterValue] | None,
    reducer: Reducer | None,
):
    if reducer is not None:
        raise ValueError("an atomic Fusion cannot define a reducer")
    return make_model_call(
        model=model,
        prompt=_DEFAULT_PROMPT if prompt is None else prompt,
        params=params,
    )


def _composite_inputs(values: Sequence[str | Fusion] | None) -> tuple[str | Fusion, ...]:
    if values is None or isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("composite Fusion inputs must be a sequence")
    inputs = tuple(values)
    if not inputs:
        raise ValueError("a composite Fusion requires at least one input")
    for value in inputs:
        if isinstance(value, Fusion):
            continue
        if not isinstance(value, str) or not value.strip():
            raise TypeError("composite Fusion inputs must be model IDs or sf.Fusion values")
    return inputs


def _composite_reducer(value: Reducer | None) -> Reducer:
    if not isinstance(value, Reducer):
        raise TypeError("a composite Fusion requires a reducer implementing sf.Reducer")
    return value


def _collect_models(fusion: Fusion, models: list[str], seen: set[int]) -> None:
    identity = id(fusion)
    if identity in seen:
        return
    seen.add(identity)
    if fusion.model is not None:
        models.append(fusion.model)
        return
    for value in fusion.inputs:
        if isinstance(value, str):
            models.append(value.strip())
        else:
            _collect_models(value, models, seen)


def _collect_members(fusion: Fusion, members: list[_FusionMember], seen: set[int]) -> None:
    identity = id(fusion)
    if identity in seen:
        return
    seen.add(identity)
    if fusion.model is not None:
        assert fusion.prompt is not None
        members.append(
            _FusionMember(
                id=f"member_{len(members) + 1}",
                call=_ModelCall(fusion.model, fusion.prompt, fusion._parameter_items),
            )
        )
        return
    for value in fusion.inputs:
        if isinstance(value, str):
            members.append(
                _FusionMember(
                    id=f"member_{len(members) + 1}",
                    call=make_model_call(model=value, prompt=_DEFAULT_PROMPT),
                )
            )
        else:
            _collect_members(value, members, seen)


def _collect_reducers(fusion: Fusion, reducers: list[Reducer], seen: set[int]) -> None:
    identity = id(fusion)
    if identity in seen:
        return
    seen.add(identity)
    for value in fusion.inputs:
        if isinstance(value, Fusion):
            _collect_reducers(value, reducers, seen)
    if fusion.reducer is not None:
        reducers.append(fusion.reducer)


def _validate_graph(root: Fusion) -> None:
    names: dict[str, int] = {}
    visited: set[int] = set()
    active: set[int] = set()

    def visit(fusion: Fusion) -> None:
        identity = id(fusion)
        if identity in active:
            raise ValueError(f"Fusion graph contains a cycle at {fusion.name!r}")
        if identity in visited:
            return
        owner = names.get(fusion.name)
        if owner is not None and owner != identity:
            raise ValueError(f"duplicate Fusion name {fusion.name!r}")
        names[fusion.name] = identity
        active.add(identity)
        for value in fusion.inputs:
            if isinstance(value, Fusion):
                visit(value)
        active.remove(identity)
        visited.add(identity)

    visit(root)


def _name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("fusion name must not be empty")
    return "-".join(value.strip().lower().split())


__all__ = ["Fusion"]
