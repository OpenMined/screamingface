"""Universal benchmark and case value objects."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from screamingface.aggregators import Aggregator, Mean
from screamingface.graders import Grader
from screamingface.tools import Tool, _tool_values

type CaseProducer = Callable[[], Iterable[Case]]


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
    max_tool_rounds: int | None
    _case_source: tuple[Case, ...] | CaseProducer = field(repr=False)

    def __init__(
        self,
        id: str,
        *,
        cases: Sequence[Case] | CaseProducer,
        grader: Grader,
        title: str | None = None,
        aggregator: Aggregator | None = None,
        tools: Sequence[Tool] = (),
        max_tool_rounds: int | None = None,
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
        elif isinstance(cases, Sequence) and not isinstance(cases, (str, bytes)):
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
            "max_tool_rounds",
            _tool_rounds(max_tool_rounds, has_tools=bool(selected_tools)),
        )
        object.__setattr__(self, "_case_source", source)

    def _materialize_cases(self) -> tuple[Case, ...]:
        values = self._case_source() if callable(self._case_source) else self._case_source
        return _validate_cases(tuple(values))


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


def _tool_rounds(value: int | None, *, has_tools: bool) -> int | None:
    if not has_tools:
        if value is not None:
            raise ValueError("max_tool_rounds must be None for a tool-free benchmark")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_tool_rounds is required and must be a positive integer")
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
