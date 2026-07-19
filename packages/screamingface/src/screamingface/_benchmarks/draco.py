"""Canonical, pinned DRACO definition loaded with the researcher's HF access."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import cast
from uuid import UUID

from screamingface._benchmarks._draco_prompt import DRACO_JUDGE_PROMPT
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import InvalidBenchmarkError
from screamingface.graders import Rubric

DATASET = "perplexity-ai/draco"
SPLIT = "test"
REVISION = "ce076749809027649ebd331bcb70f42bf720d387"
EXPECTED_CASES = 100
EXPECTED_SECTIONS = 400
EXPECTED_SECTIONS_PER_CASE = 4
EXPECTED_CRITERIA = 3_934
EXPECTED_DOMAINS = frozenset(
    {
        "Academic",
        "Finance",
        "General Knowledge",
        "Law",
        "Medicine",
        "Needle in a Haystack",
        "Personalized Assistant",
        "Shopping/Product Comparison",
        "Technology",
        "UX Design",
    }
)

_SOURCE_FIELDS = {"id", "problem", "answer", "domain"}
_RUBRIC_FIELDS = {"id", "sections"}
_SECTION_FIELDS = {"id", "title", "criteria"}
_CRITERION_FIELDS = {"id", "requirement", "weight"}
_METRIC_KEY_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class _SourceRow:
    id: str
    problem: str
    rubric: dict[str, object]
    rubric_id: str
    domain: str
    sections: int
    criteria: int


def benchmark() -> Benchmark:
    """Build the public DRACO definition around the process-cached local cases."""

    return Benchmark(
        "draco@1",
        title="DRACO",
        cases=draco_cases(),
        grader=Rubric(
            model="gemini/3.1-pro-preview",
            prompt=DRACO_JUDGE_PROMPT,
            passes=3,
            params={
                "temperature": 0.2,
                "reasoning": "low",
                "max_tokens": 4096,
            },
        ),
        aggregator=Mean(),
        tools=("web_search",),
    )


@cache
def draco_cases() -> tuple[Case, ...]:
    """Load and fully validate DRACO through the caller's Hugging Face session."""

    from datasets import load_dataset

    raw_rows = tuple(load_dataset(DATASET, split=SPLIT, revision=REVISION))
    source_rows = _validate_source(raw_rows)
    return tuple(
        Case(
            row.id,
            row.problem,
            reference=row.rubric,
            metadata={"domain": row.domain},
        )
        for row in source_rows
    )


def _validate_source(raw_rows: tuple[object, ...]) -> tuple[_SourceRow, ...]:
    if len(raw_rows) != EXPECTED_CASES:
        raise InvalidBenchmarkError(f"draco@1 expected {EXPECTED_CASES} rows, got {len(raw_rows)}")

    rows = tuple(_source_row(raw_row, position) for position, raw_row in enumerate(raw_rows))
    case_ids: set[str] = set()
    rubric_ids: set[str] = set()
    domains: set[str] = set()
    for row in rows:
        _add_unique(case_ids, row.id, "case ID")
        _add_unique(rubric_ids, row.rubric_id, "rubric ID")
        domains.add(row.domain)

    _canonical_totals(rows, domains)
    return rows


def _source_row(raw_row: object, position: int) -> _SourceRow:
    row = _source_mapping(raw_row, position)
    case_id = _case_id(row["id"], position)
    problem = _text(row["problem"], position, "problem")
    domain = _text(row["domain"], position, "domain")
    if domain not in EXPECTED_DOMAINS:
        raise InvalidBenchmarkError(f"draco@1 row {position} has unknown domain {domain!r}")
    rubric, rubric_id, sections, criteria = _rubric(row["answer"], position)
    return _SourceRow(case_id, problem, rubric, rubric_id, domain, sections, criteria)


def _canonical_totals(rows: tuple[_SourceRow, ...], domains: set[str]) -> None:
    if domains != EXPECTED_DOMAINS:
        raise InvalidBenchmarkError(
            f"draco@1 expected domains {sorted(EXPECTED_DOMAINS)}, got {sorted(domains)}"
        )
    section_count = sum(row.sections for row in rows)
    if section_count != EXPECTED_SECTIONS:
        raise InvalidBenchmarkError(
            f"draco@1 expected {EXPECTED_SECTIONS} sections, got {section_count}"
        )
    criterion_count = sum(row.criteria for row in rows)
    if criterion_count != EXPECTED_CRITERIA:
        raise InvalidBenchmarkError(
            f"draco@1 expected {EXPECTED_CRITERIA} criteria, got {criterion_count}"
        )


def _source_mapping(value: object, position: int) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidBenchmarkError(f"draco@1 row {position} must be a mapping")
    row = cast(Mapping[str, object], value)
    _exact_fields(row, _SOURCE_FIELDS, f"row {position}")
    return row


def _case_id(value: object, position: int) -> str:
    case_id = _text(value, position, "id")
    try:
        parsed = UUID(case_id)
    except ValueError as exc:
        raise InvalidBenchmarkError(f"draco@1 row {position} id must be a canonical UUID") from exc
    if str(parsed) != case_id:
        raise InvalidBenchmarkError(f"draco@1 row {position} id must be a canonical UUID")
    return case_id


def _rubric(value: object, position: int) -> tuple[dict[str, object], str, int, int]:
    source = _text(value, position, "answer")
    rubric = _decode_rubric_json(source, position)
    _exact_fields(rubric, _RUBRIC_FIELDS, f"row {position} rubric")
    rubric_id = _identifier(rubric["id"], position, "rubric ID")
    sections = _list(rubric["sections"], position, "rubric sections")
    if len(sections) != EXPECTED_SECTIONS_PER_CASE:
        raise InvalidBenchmarkError(
            f"draco@1 row {position} expected {EXPECTED_SECTIONS_PER_CASE} sections, "
            f"got {len(sections)}"
        )
    criterion_count = _validate_sections(sections, position)
    return rubric, rubric_id, len(sections), criterion_count


def _decode_rubric_json(source: str, position: int) -> dict[str, object]:
    try:
        decoded = json.loads(
            source,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidBenchmarkError(
            f"draco@1 row {position} answer must be unique-key JSON: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise InvalidBenchmarkError(f"draco@1 row {position} rubric must be an object")
    return cast(dict[str, object], decoded)


def _validate_sections(sections: list[object], position: int) -> int:
    section_ids: set[str] = set()
    metric_keys: set[str] = {"pass_rate"}
    criterion_ids: set[str] = set()
    criterion_count = 0
    for section_position, raw_section in enumerate(sections):
        criterion_count += _validate_section(
            raw_section,
            position,
            section_position,
            section_ids,
            metric_keys,
            criterion_ids,
        )
    return criterion_count


def _validate_section(
    raw_section: object,
    position: int,
    section_position: int,
    section_ids: set[str],
    metric_keys: set[str],
    criterion_ids: set[str],
) -> int:
    section = _object(raw_section, position, f"section {section_position}")
    _exact_fields(section, _SECTION_FIELDS, f"row {position} section {section_position}")
    section_id = _identifier(section["id"], position, f"section {section_position} ID")
    _add_unique(section_ids, section_id, "section ID", row=position)
    _text(section["title"], position, f"section {section_id!r} title")
    _add_unique(metric_keys, _metric_key(section_id, position), "section metric", row=position)
    criteria = _list(section["criteria"], position, f"section {section_id!r} criteria")
    if not criteria:
        raise InvalidBenchmarkError(
            f"draco@1 row {position} section {section_id!r} must contain criteria"
        )
    weights = tuple(
        _validate_criterion(raw, position, section_id, criterion_ids) for raw in criteria
    )
    if not any(weight > 0 for weight in weights):
        raise InvalidBenchmarkError(
            f"draco@1 row {position} section {section_id!r} "
            "must contain a positive-weight criterion"
        )
    return len(criteria)


def _validate_criterion(
    raw_criterion: object,
    position: int,
    section_id: str,
    criterion_ids: set[str],
) -> float:
    criterion = _object(raw_criterion, position, f"section {section_id!r} criterion")
    _exact_fields(
        criterion,
        _CRITERION_FIELDS,
        f"row {position} section {section_id!r} criterion",
    )
    criterion_id = _identifier(criterion["id"], position, f"section {section_id!r} criterion ID")
    _add_unique(criterion_ids, criterion_id, "criterion ID", row=position)
    _text(criterion["requirement"], position, f"criterion {criterion_id!r} requirement")
    return _weight(criterion["weight"], position, criterion_id)


def _object(value: object, position: int, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidBenchmarkError(f"draco@1 row {position} {label} must be an object")
    return value


def _list(value: object, position: int, label: str) -> list[object]:
    if not isinstance(value, list):
        raise InvalidBenchmarkError(f"draco@1 row {position} {label} must be a list")
    return value


def _text(value: object, position: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidBenchmarkError(f"draco@1 row {position} {label} must be a non-blank string")
    return value


def _identifier(value: object, position: int, label: str) -> str:
    identifier = _text(value, position, label)
    if identifier != identifier.strip():
        raise InvalidBenchmarkError(
            f"draco@1 row {position} {label} must not have outer whitespace"
        )
    return identifier


def _weight(value: object, position: int, criterion_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidBenchmarkError(
            f"draco@1 row {position} criterion {criterion_id!r} weight must be numeric"
        )
    normalized = float(value)
    if not math.isfinite(normalized) or normalized == 0:
        raise InvalidBenchmarkError(
            f"draco@1 row {position} criterion {criterion_id!r} weight must be finite and non-zero"
        )
    return normalized


def _metric_key(section_id: str, position: int) -> str:
    key = _METRIC_KEY_RE.sub("_", section_id.strip().lower()).strip("_")
    if not key:
        raise InvalidBenchmarkError(
            f"draco@1 row {position} section ID {section_id!r} cannot form a metric key"
        )
    return key


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise InvalidBenchmarkError(
            f"draco@1 {label} is missing field(s): {', '.join(sorted(missing))}"
        )
    if unknown:
        raise InvalidBenchmarkError(
            f"draco@1 {label} has unknown field(s): {', '.join(sorted(unknown))}"
        )


def _add_unique(seen: set[str], value: str, label: str, *, row: int | None = None) -> None:
    if value in seen:
        prefix = "draco@1" if row is None else f"draco@1 row {row}"
        raise InvalidBenchmarkError(f"{prefix} has duplicate {label}: {value}")
    seen.add(value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant {value!r}")
