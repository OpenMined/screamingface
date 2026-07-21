from __future__ import annotations

import hashlib
import json
import sys
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

import screamingface as sf
from screamingface._benchmarks import draco
from screamingface._benchmarks._draco_prompt import (
    DRACO_JUDGE_PROMPT,
    DRACO_JUDGE_PROMPT_BYTES,
    DRACO_JUDGE_PROMPT_SHA256,
)


def _criterion(index: int) -> dict[str, object]:
    return {
        "id": f"criterion-{index}",
        "requirement": f"Requirement {index}",
        "weight": -10 if index % 11 == 0 else 10,
    }


def _rubric(row_index: int, criterion_count: int) -> dict[str, object]:
    section_sizes = [criterion_count // 4] * 4
    for index in range(criterion_count % 4):
        section_sizes[index] += 1
    cursor = 0
    sections: list[dict[str, object]] = []
    for section_index, size in enumerate(section_sizes):
        criteria = [_criterion(index) for index in range(cursor, cursor + size)]
        cursor += size
        sections.append(
            {
                "id": f"section-{section_index}",
                "title": f"Section {section_index}",
                "criteria": criteria,
            }
        )
    return {"id": f"rubric-{row_index}", "sections": sections}


def _draco_rows() -> list[dict[str, object]]:
    domains = tuple(sorted(draco.EXPECTED_DOMAINS))
    return [
        {
            "id": str(UUID(int=index + 1)),
            "problem": f"Research problem {index}",
            "answer": json.dumps(_rubric(index, 40 if index < 34 else 39)),
            "domain": domains[index % len(domains)],
        }
        for index in range(draco.EXPECTED_CASES)
    ]


@pytest.fixture(autouse=True)
def clear_draco_cache():
    draco.draco_cases.cache_clear()
    yield
    draco.draco_cases.cache_clear()


def _install_dataset(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]
) -> list[object]:
    calls: list[object] = []

    def load_dataset(*args: object, **kwargs: object):
        calls.append((args, kwargs))
        return rows

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=load_dataset))
    return calls


def test_engine_draco_definition_is_pinned_cached_and_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _draco_rows()
    calls = _install_dataset(monkeypatch, rows)

    first = draco.benchmark()
    second = draco.benchmark()
    first_cases = first._materialize_cases()
    second_cases = second._materialize_cases()

    assert first.id == "draco@1"
    assert first.title == "DRACO"
    assert first.tools == (
        sf.tools.TavilySearch(
            max_results=5,
            exclude_domains=draco.EXCLUDED_RESEARCH_DOMAINS,
        ),
        sf.tools.TavilyExtract(),
    )
    assert first.max_tool_rounds == 12
    assert isinstance(first.grader, sf.graders.Rubric)
    assert first.grader.model == "gemini/3.1-pro-preview"
    assert first.grader.prompt == DRACO_JUDGE_PROMPT
    assert first.grader.passes == 3
    assert first.grader.params == {
        "temperature": 0.2,
        "reasoning": "low",
        "max_tokens": 4096,
    }
    assert first_cases is second_cases
    assert len(first_cases) == draco.EXPECTED_CASES
    assert first_cases[0].id == rows[0]["id"]
    assert first_cases[0].input == rows[0]["problem"]
    assert first_cases[0].reference == json.loads(str(rows[0]["answer"]))
    assert first_cases[0].metadata == {"domain": rows[0]["domain"]}
    assert calls == [((draco.DATASET,), {"split": draco.SPLIT, "revision": draco.REVISION})]


def test_draco_prompt_is_byte_pinned() -> None:
    encoded = DRACO_JUDGE_PROMPT.encode()

    assert len(encoded) == DRACO_JUDGE_PROMPT_BYTES == 5_196
    assert hashlib.sha256(encoded).hexdigest() == DRACO_JUDGE_PROMPT_SHA256


def test_draco_source_requires_the_canonical_row_count() -> None:
    with pytest.raises(sf.InvalidBenchmarkError, match="expected 100 rows, got 99"):
        draco._validate_source(tuple(_draco_rows()[:-1]))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: rows.__setitem__(-1, "not a row"), "row 99 must be a mapping"),
        (lambda rows: rows[0].pop("problem"), "missing field.*problem"),
        (lambda rows: rows[0].update(extra=True), "unknown field.*extra"),
        (lambda rows: rows[0].update(id="not-a-uuid"), "id must be a canonical UUID"),
        (lambda rows: rows[-1].update(id=rows[0]["id"]), "duplicate case ID"),
        (lambda rows: rows[0].update(problem="  "), "problem must be a non-blank string"),
        (lambda rows: rows[0].update(domain="Unknown"), "unknown domain"),
        (
            lambda rows: rows.__setitem__(
                slice(None),
                [dict(row, domain="Academic") for row in rows],
            ),
            "expected domains",
        ),
        (lambda rows: rows[0].update(answer="not json"), "unique-key JSON"),
        (
            lambda rows: rows[0].update(answer='{"id":"one","id":"two","sections":[]}'),
            "duplicate JSON field",
        ),
    ],
)
def test_draco_source_rejects_invalid_rows(mutate, message: str) -> None:
    rows = cast(list[object], _draco_rows())
    mutate(rows)

    with pytest.raises(sf.InvalidBenchmarkError, match=message):
        draco._validate_source(tuple(rows))


def _mutate_rubric(rows: list[dict[str, object]], mutate) -> None:
    rubric = json.loads(str(rows[0]["answer"]))
    mutate(rubric)
    rows[0]["answer"] = json.dumps(rubric)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rubric: rubric.pop("id"), "rubric.*missing field.*id"),
        (lambda rubric: rubric.update(extra=True), "rubric.*unknown field.*extra"),
        (lambda rubric: rubric.update(id=" "), "rubric ID must be a non-blank string"),
        (lambda rubric: rubric.update(sections=[]), "expected 4 sections, got 0"),
        (
            lambda rubric: rubric["sections"][0].pop("title"),
            "section 0.*missing field.*title",
        ),
        (
            lambda rubric: rubric["sections"][1].update(id=rubric["sections"][0]["id"]),
            "duplicate section ID",
        ),
        (
            lambda rubric: rubric["sections"][1].update(id="section 0"),
            "duplicate section metric",
        ),
        (
            lambda rubric: rubric["sections"][0].update(criteria=[]),
            "must contain criteria",
        ),
        (
            lambda rubric: rubric["sections"][0]["criteria"][0].pop("requirement"),
            "criterion.*missing field.*requirement",
        ),
        (
            lambda rubric: rubric["sections"][0]["criteria"][1].update(
                id=rubric["sections"][0]["criteria"][0]["id"]
            ),
            "duplicate criterion ID",
        ),
        (
            lambda rubric: rubric["sections"][0]["criteria"][0].update(requirement=""),
            "requirement must be a non-blank string",
        ),
        (
            lambda rubric: rubric["sections"][0]["criteria"][0].update(weight=True),
            "weight must be numeric",
        ),
        (
            lambda rubric: rubric["sections"][0]["criteria"][0].update(weight=0),
            "weight must be finite and non-zero",
        ),
        (
            lambda rubric: [item.update(weight=-10) for item in rubric["sections"][0]["criteria"]],
            "must contain a positive-weight criterion",
        ),
    ],
)
def test_draco_source_rejects_invalid_rubrics(mutate, message: str) -> None:
    rows = _draco_rows()
    _mutate_rubric(rows, mutate)

    with pytest.raises(sf.InvalidBenchmarkError, match=message):
        draco._validate_source(tuple(rows))


def test_draco_source_requires_unique_rubric_ids_and_canonical_totals() -> None:
    rows = _draco_rows()
    first = json.loads(str(rows[0]["answer"]))
    second = json.loads(str(rows[1]["answer"]))
    second["id"] = first["id"]
    rows[1]["answer"] = json.dumps(second)

    with pytest.raises(sf.InvalidBenchmarkError, match="duplicate rubric ID"):
        draco._validate_source(tuple(rows))

    rows = _draco_rows()
    rubric = json.loads(str(rows[-1]["answer"]))
    rubric["sections"][-1]["criteria"].pop()
    rows[-1]["answer"] = json.dumps(rubric)

    with pytest.raises(sf.InvalidBenchmarkError, match="expected 3934 criteria, got 3933"):
        draco._validate_source(tuple(rows))
