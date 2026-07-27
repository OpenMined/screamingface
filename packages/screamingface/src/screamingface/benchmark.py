"""Universal benchmark and case value objects."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, overload

from screamingface.aggregators import Aggregator, Mean
from screamingface.graders import Grader
from screamingface.recipe import Recipe
from screamingface.tools import Tool, _tool_values

type CaseProducer = Callable[[], Iterable[Case]]

if TYPE_CHECKING:
    from screamingface._progress import ProgressSetting
    from screamingface.report import Report, StudyReport


@dataclass(frozen=True, slots=True, init=False)
class Case:
    """One model input plus a sealed JSON reference and reporting metadata."""

    id: str
    input: str
    _reference_json: str = field(repr=False)
    _metadata_json: str = field(repr=False)

    def __init__(
        self,
        id: str,
        input: str,
        reference: object = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        object.__setattr__(self, "id", _nonempty(id, "case id"))
        object.__setattr__(self, "input", _nonempty(input, "case input", strip=False))
        object.__setattr__(self, "_reference_json", _json_text(reference, "case reference"))
        normalized_metadata: object = {} if metadata is None else metadata
        object.__setattr__(
            self,
            "_metadata_json",
            _json_text(normalized_metadata, "case metadata", require_object=True),
        )

    @property
    def reference(self) -> object:
        return json.loads(self._reference_json)

    @property
    def metadata(self) -> dict[str, object]:
        value = json.loads(self._metadata_json)
        assert isinstance(value, dict)
        return value

    def _to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "input": self.input,
            "reference": self.reference,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True, init=False)
class Benchmark:
    """A compact benchmark definition with an intentionally private case source."""

    id: str
    title: str
    grader: Grader
    aggregator: Aggregator
    tools: tuple[Tool, ...]
    max_tool_calls: int | None
    _case_source: tuple[Case, ...] | CaseProducer | None = field(repr=False)
    _cases_route: str | None = field(repr=False)
    _grader_route: str | None = field(repr=False)
    _aggregator_route: str | None = field(repr=False)
    _tool_policy_route: str | None = field(repr=False)
    _candidate_route: str | None = field(repr=False)
    _candidate_aggregator_route: str | None = field(repr=False)

    def __init__(
        self,
        id: str,
        *,
        cases: Sequence[Case] | CaseProducer,
        grader: Grader,
        title: str | None = None,
        aggregator: Aggregator | None = None,
        tools: Sequence[Tool] = (),
        max_tool_calls: int | None = None,
    ) -> None:
        benchmark_id = _nonempty(id, "benchmark id")
        if not isinstance(grader, Grader):
            raise TypeError("benchmark grader must be an sf.Grader")
        selected_aggregator = aggregator or Mean()
        if not isinstance(selected_aggregator, Aggregator):
            raise TypeError("benchmark aggregator must be an sf.Aggregator")
        source: tuple[Case, ...] | CaseProducer
        if callable(cases):
            source = cases
        elif isinstance(cases, Sequence) and not isinstance(cases, str | bytes):
            source = _validate_cases(cases)
        else:
            raise TypeError("benchmark cases must be a sequence or zero-argument callable")
        object.__setattr__(self, "id", benchmark_id)
        object.__setattr__(self, "title", _nonempty(title or benchmark_id, "benchmark title"))
        object.__setattr__(self, "grader", grader)
        object.__setattr__(self, "aggregator", selected_aggregator)
        selected_tools = _tool_values(tools)
        object.__setattr__(self, "tools", selected_tools)
        object.__setattr__(
            self,
            "max_tool_calls",
            _tool_calls(max_tool_calls, has_tools=bool(selected_tools)),
        )
        _set_local_execution(self, source)

    @classmethod
    def _from_engine(
        cls,
        id: str,
        *,
        title: str,
        cases_route: str,
        grader: Grader,
        grader_route: str,
        aggregator: Aggregator,
        aggregator_route: str,
        candidate_route: str | None = None,
        candidate_aggregator_route: str | None = None,
        tool_policy_route: str | None = None,
        tools: Sequence[Tool] = (),
        max_tool_calls: int | None = None,
    ) -> Benchmark:
        """Construct one immutable engine-advertised benchmark manifest."""

        value = object.__new__(cls)
        benchmark_id = _nonempty(id, "benchmark id")
        if not isinstance(grader, Grader):
            raise TypeError("benchmark grader must be an sf.Grader")
        if not isinstance(aggregator, Aggregator):
            raise TypeError("benchmark aggregator must be an sf.Aggregator")
        selected_tools = _tool_values(tools)
        if selected_tools and tool_policy_route is None:
            raise ValueError("engine tool-enabled benchmark requires a tool policy route")
        if not selected_tools and tool_policy_route is not None:
            raise ValueError("engine tool-free benchmark cannot declare a tool policy route")
        object.__setattr__(value, "id", benchmark_id)
        object.__setattr__(value, "title", _nonempty(title, "benchmark title"))
        object.__setattr__(value, "grader", grader)
        object.__setattr__(value, "aggregator", aggregator)
        object.__setattr__(value, "tools", selected_tools)
        object.__setattr__(
            value,
            "max_tool_calls",
            _tool_calls(max_tool_calls, has_tools=bool(selected_tools)),
        )
        object.__setattr__(value, "_case_source", None)
        object.__setattr__(value, "_cases_route", _route(cases_route, "benchmark cases route"))
        object.__setattr__(value, "_grader_route", _route(grader_route, "benchmark grader route"))
        object.__setattr__(
            value,
            "_aggregator_route",
            _route(aggregator_route, "benchmark aggregator route"),
        )
        object.__setattr__(
            value,
            "_tool_policy_route",
            (
                _route(tool_policy_route, "benchmark tool policy route")
                if tool_policy_route is not None
                else None
            ),
        )
        if (candidate_route is None) != (candidate_aggregator_route is None):
            raise ValueError(
                "engine benchmark candidate route and candidate aggregator route must coexist"
            )
        _set_candidate_routes(value, candidate_route, candidate_aggregator_route)
        return value

    @overload
    def evaluate(
        self,
        candidate: Recipe,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Report: ...

    @overload
    def evaluate(
        self,
        candidate: Sequence[Recipe],
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> StudyReport: ...

    def evaluate(
        self,
        candidate: Recipe | Sequence[Recipe],
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Report | StudyReport:
        """Evaluate one Recipe or one ordered candidate set through the URL4 engine."""

        from screamingface._benchmark_execution import evaluate_benchmark, evaluate_candidates

        if isinstance(candidate, Recipe):
            return evaluate_benchmark(self, candidate, first=first, progress=progress)
        return evaluate_candidates(self, candidate, first=first, progress=progress)

    def url4(self, candidate: Recipe | Sequence[Recipe], *, first: int | None = None) -> str:
        """Compile the complete benchmark slice without executing it."""

        from screamingface._benchmark_execution import benchmark_url4, candidates_url4

        if isinstance(candidate, Recipe):
            return benchmark_url4(self, candidate, first=first)
        return candidates_url4(self, candidate, first=first)

    def _repr_html_(self) -> str:
        from screamingface._card_display import benchmark_card_html

        return benchmark_card_html(self)

    def _materialize_cases(self) -> tuple[Case, ...]:
        if self._case_source is None:
            raise RuntimeError("engine-advertised benchmark cases are evaluated by the engine")
        values = self._case_source() if callable(self._case_source) else self._case_source
        return _validate_cases(tuple(values))


def _set_local_execution(benchmark: Benchmark, source: tuple[Case, ...] | CaseProducer) -> None:
    object.__setattr__(benchmark, "_case_source", source)
    for name in (
        "_cases_route",
        "_grader_route",
        "_aggregator_route",
        "_tool_policy_route",
        "_candidate_route",
        "_candidate_aggregator_route",
    ):
        object.__setattr__(benchmark, name, None)


def _set_candidate_routes(
    benchmark: Benchmark,
    candidate_route: str | None,
    aggregator_route: str | None,
) -> None:
    route = (
        _route(candidate_route, "benchmark candidate route")
        if candidate_route is not None
        else None
    )
    aggregate = (
        _route(aggregator_route, "benchmark candidate aggregator route")
        if aggregator_route is not None
        else None
    )
    object.__setattr__(benchmark, "_candidate_route", route)
    object.__setattr__(benchmark, "_candidate_aggregator_route", aggregate)


def _validate_cases(values: Sequence[Case]) -> tuple[Case, ...]:
    cases = tuple(values)
    if not cases:
        raise ValueError("benchmark must contain at least one case")
    if not all(isinstance(case, Case) for case in cases):
        raise TypeError("benchmark case producers must yield sf.Case values")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        duplicate = next(case_id for case_id in ids if ids.count(case_id) > 1)
        raise ValueError(f"duplicate case ID: {duplicate}")
    return cases


def _tool_calls(value: int | None, *, has_tools: bool) -> int | None:
    if not has_tools:
        if value is not None:
            raise ValueError("max_tool_calls must be None for a tool-free benchmark")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 32:
        raise ValueError("max_tool_calls is required and must be a positive integer from 1 to 32")
    return value


def _nonempty(value: object, label: str, *, strip: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value.strip() if strip else value


def _json_text(value: Any, label: str, *, require_object: bool = False) -> str:
    if require_object and not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    try:
        return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must contain only JSON values") from exc


def _route(value: object, label: str) -> str:
    route = _nonempty(value, label)
    if not route.startswith("/") or route.startswith("//") or "?" in route or "#" in route:
        raise ValueError(f"{label} must be a same-engine absolute path")
    return route
