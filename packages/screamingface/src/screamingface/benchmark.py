"""Universal benchmark and case value objects."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from screamingface._tooling import tool_ids
from screamingface.aggregators import Aggregator, Mean
from screamingface.graders import Grader

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
    tools: tuple[str, ...]
    _case_source: tuple[Case, ...] | CaseProducer = field(repr=False)

    def __init__(
        self,
        id: str,
        *,
        cases: Sequence[Case] | CaseProducer,
        grader: Grader,
        title: str | None = None,
        aggregator: Aggregator | None = None,
        tools: Sequence[str] = (),
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
        object.__setattr__(self, "tools", _tools(tools))
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


def _tools(values: Sequence[str]) -> tuple[str, ...]:
    return tool_ids(values, label="benchmark tools")


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
