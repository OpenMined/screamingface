"""DRACO's judge preparation, verdict parsing, scoring, and aggregation."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from functools import partial
from statistics import fmean
from types import MappingProxyType
from typing import cast

from url4_cloud.benchmarks._types import BenchmarkAction, decode_wire

_METRIC_KEY = re.compile(r"[^a-z0-9]+")


def build_actions(
    *,
    benchmark_id: str,
    judge_passes: int,
    cases: tuple[dict[str, object], ...],
) -> Mapping[str, BenchmarkAction]:
    """Bind DRACO's pure actions to one installed benchmark definition."""

    return MappingProxyType(
        {
            "load": partial(load, cases=cases),
            "grading_inputs": partial(grading_inputs, judge_passes=judge_passes),
            "grade": grade,
            "aggregate": partial(
                aggregate,
                benchmark_id=benchmark_id,
            ),
        }
    )


def load(
    _context: str,
    _intent: str,
    *,
    cases: tuple[dict[str, object], ...],
) -> str:
    """Return the pinned cases exposed by this DRACO tier."""

    return _json(cases)


def grading_inputs(context: str, _intent: str, *, judge_passes: int) -> str:
    """Expand one Candidate answer into explicit per-criterion judge jobs."""

    value = _object(context, "judge input")
    case = _mapping(value.get("case"), "judge case")
    answer = _text(value.get("answer"), "candidate answer")
    question = _text(case.get("input"), "case input")
    criteria = _criteria(case.get("rubric"))
    return _json(
        [
            {
                "criterion_id": criterion["id"],
                "run": run,
                "context": _judge_context(
                    question,
                    cast(str, criterion["requirement"]),
                    "negative" if cast(float, criterion["weight"]) < 0 else "positive",
                    answer,
                ),
            }
            for run in range(judge_passes)
            for criterion in criteria
        ]
    )


def grade(context: str, _intent: str) -> str:
    """Parse judge replies and calculate one deterministic DRACO case grade."""

    value = _object(context, "grade input")
    case = _mapping(value.get("case"), "grade case")
    case_id = _text(case.get("id"), "case id")
    criteria = _criteria(case.get("rubric"))
    known = {cast(str, criterion["id"]): criterion for criterion in criteria}
    judgments = _list(value.get("judgments"), "judge results")
    verdicts: dict[str, list[tuple[bool, str]]] = defaultdict(list)
    for raw in judgments:
        judgment = _mapping(raw, "judge result")
        criterion_id = _text(judgment.get("criterion_id"), "judge criterion id")
        if criterion_id not in known:
            raise ValueError(f"judge result references unknown criterion {criterion_id!r}")
        parsed = _judge_output(_text(judgment.get("response"), "judge response"))
        if parsed is not None:
            verdicts[criterion_id].append(
                (parsed["criterion_status"] == "MET", parsed["explanation"])
            )
    selected = {
        criterion_id: _majority(samples) for criterion_id, samples in verdicts.items() if samples
    }
    if not selected:
        raise ValueError("DRACO judge returned no valid criterion verdicts")
    scored = tuple(known[criterion_id] for criterion_id in selected)
    flags = {criterion_id: result[0] for criterion_id, result in selected.items()}
    metrics = {
        "normalized_score": _normalized_score(scored, flags),
        "pass_rate": _pass_rate(scored, flags),
        "coverage": len(selected) / len(criteria),
    }
    for axis, axis_criteria in _by_axis(scored).items():
        metrics[f"{_metric(axis)}_score"] = _normalized_score(axis_criteria, flags)
    return _json(
        {
            "case_id": case_id,
            "score": metrics["normalized_score"],
            "metrics": metrics,
            "criteria": [
                {
                    "id": criterion_id,
                    "met": met,
                    "explanation": explanation,
                }
                for criterion_id, (met, explanation) in selected.items()
            ],
        }
    )


def aggregate(
    _context: str,
    intent: str,
    *,
    benchmark_id: str,
) -> str:
    """Aggregate DRACO case grades into the Candidate result consumed by the Client."""

    rows = tuple(_mapping(row, "case grade") for row in _list_json(intent, "case grades"))
    if not rows:
        raise ValueError("cannot aggregate an empty DRACO evaluation")
    metric_names = set.intersection(
        *(set(_mapping(row.get("metrics"), "case metrics")) for row in rows)
    )
    metrics = {
        name: fmean(
            _number(_mapping(row.get("metrics"), "case metrics").get(name), f"metric {name!r}")
            for row in rows
        )
        for name in sorted(metric_names)
    }
    return _json(
        {
            "schema": "screamingface.candidate-result.v1",
            "benchmark_id": benchmark_id,
            "case_count": len(rows),
            "score": metrics["normalized_score"],
            "metrics": metrics,
            "failures": [],
            "cases": rows,
        }
    )


def _criteria(value: object) -> tuple[dict[str, object], ...]:
    rubric = _mapping(value, "DRACO rubric")
    sections = _list(rubric.get("sections"), "rubric sections")
    values: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_section in sections:
        section = _mapping(raw_section, "rubric section")
        axis = _text(section.get("id") or section.get("title"), "rubric axis")
        for raw in _list(section.get("criteria"), f"criteria for {axis!r}"):
            criterion = _mapping(raw, "criterion")
            criterion_id = _text(criterion.get("id"), "criterion id")
            if criterion_id in seen:
                raise ValueError(f"duplicate criterion id {criterion_id!r}")
            seen.add(criterion_id)
            weight = _number(criterion.get("weight"), f"criterion {criterion_id!r} weight")
            if not math.isfinite(weight) or weight == 0:
                raise ValueError(f"criterion {criterion_id!r} weight must be finite and non-zero")
            values.append(
                {
                    "id": criterion_id,
                    "requirement": _text(criterion.get("requirement"), "criterion requirement"),
                    "weight": weight,
                    "axis": axis,
                }
            )
    if not values:
        raise ValueError("DRACO rubric contains no criteria")
    return tuple(values)


def _judge_context(question: str, requirement: str, criterion_type: str, answer: str) -> str:
    return (
        f"<criterion_type>\n{criterion_type}\n</criterion_type>\n\n"
        f"<criterion>\n{requirement}\n</criterion>\n\n"
        f"<query>{question}</query>\n\n"
        f"<response>\n{answer}\n</response>"
    )


def _judge_output(raw: str) -> dict[str, str] | None:
    text = "\n".join(
        line for line in raw.strip().splitlines() if not line.strip().startswith("```")
    ).strip()
    for candidate in (text, _first_json_object(text)):
        if candidate is None:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and set(value) == {"explanation", "criterion_status"}
            and isinstance(value["explanation"], str)
            and value["explanation"].strip()
            and value["criterion_status"] in {"MET", "UNMET"}
        ):
            return cast(dict[str, str], value)
    return None


def _first_json_object(text: str) -> str | None:
    decoder = json.JSONDecoder()
    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            _value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        return text[start : start + end]
    return None


def _majority(samples: list[tuple[bool, str]]) -> tuple[bool, str]:
    met = sum(value for value, _explanation in samples) * 2 >= len(samples)
    explanation = next(reason for value, reason in samples if value == met)
    return met, explanation


def _normalized_score(
    criteria: tuple[dict[str, object], ...], verdicts: Mapping[str, bool]
) -> float:
    achieved = 0.0
    possible = 0.0
    for criterion in criteria:
        weight = cast(float, criterion["weight"])
        met = verdicts[cast(str, criterion["id"])]
        if weight > 0:
            possible += weight
            if met:
                achieved += weight
        elif met:
            achieved += weight
    return 0.0 if possible <= 0 else max(0.0, min(1.0, achieved / possible))


def _pass_rate(criteria: tuple[dict[str, object], ...], verdicts: Mapping[str, bool]) -> float:
    correct = sum(
        1
        for criterion in criteria
        if (cast(float, criterion["weight"]) > 0) == verdicts[cast(str, criterion["id"])]
    )
    return correct / len(criteria)


def _by_axis(
    criteria: tuple[dict[str, object], ...],
) -> dict[str, tuple[dict[str, object], ...]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for criterion in criteria:
        grouped[cast(str, criterion["axis"])].append(criterion)
    return {axis: tuple(values) for axis, values in grouped.items()}


def _metric(value: str) -> str:
    return _METRIC_KEY.sub("_", value.casefold()).strip("_") or "unknown"


def _object(value: str, label: str) -> Mapping[str, object]:
    return _mapping(decode_wire(value, label), label)


def _list_json(value: str, label: str) -> list[object]:
    return _list(decode_wire(value, label), label)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, str):
        value = decode_wire(value, label)
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if isinstance(value, str):
        value = decode_wire(value, label)
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-blank text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _json(value: object) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


__all__ = ["aggregate", "build_actions", "grade", "grading_inputs", "load"]
