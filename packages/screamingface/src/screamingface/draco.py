"""Private DRACO dataset, rubric, and paper-aligned judge-prompt helpers."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from importlib import import_module
from importlib.resources import files
from typing import Any

from screamingface.errors import DatasetUnavailable

_DATASET = "perplexity-ai/draco"
_SPLIT = "test"


@dataclass(frozen=True, slots=True)
class _DracoCriterion:
    id: str
    weight: float
    requirement: str
    axis: str


@dataclass(frozen=True, slots=True)
class _DracoRow:
    id: str
    problem: str
    criteria: tuple[_DracoCriterion, ...]
    domain: str


def _load_mock_draco_rows(first: int, seed: int) -> tuple[_DracoRow, ...]:
    raw = files("screamingface._data").joinpath("draco_shaped_synthetic.json").read_text()
    return _select_draco_rows(json.loads(raw), first, seed)


def _load_live_draco_rows(first: int, seed: int) -> tuple[_DracoRow, ...]:
    try:
        load_dataset = import_module("datasets").load_dataset
    except ImportError as exc:
        raise DatasetUnavailable(
            "Live DRACO requires the 'datasets' extra: uv sync --extra datasets"
        ) from exc
    dataset = load_dataset(_DATASET, split=_SPLIT)
    return _select_draco_rows(dataset, first, seed)


def _select_draco_rows(rows: Any, first: int, seed: int) -> tuple[_DracoRow, ...]:
    if first < 1:
        raise ValueError("first must be positive")
    if first > len(rows):
        raise ValueError(f"DRACO contains {len(rows)} rows; requested {first}")
    indices = list(range(len(rows)))
    random.Random(f"screamingface-draco:{seed}").shuffle(indices)
    return tuple(_draco_row(rows[index]) for index in indices[:first])


def _draco_row(raw: Any) -> _DracoRow:
    if not isinstance(raw, dict):
        raw = dict(raw)
    return _DracoRow(
        id=_required_row_text(raw, "id"),
        problem=_required_row_text(raw, "problem"),
        criteria=_parse_draco_rubric(raw.get("answer")),
        domain=_required_row_text(raw, "domain"),
    )


def _required_row_text(raw: dict, name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("DRACO rows require non-empty id, problem, and domain fields")
    return value


def _parse_draco_rubric(raw: object) -> tuple[_DracoCriterion, ...]:
    document = _rubric_document(raw)
    criteria = _rubric_criteria(document["sections"])
    if not criteria:
        raise ValueError("DRACO rubric must contain at least one criterion")
    if len({criterion.id for criterion in criteria}) != len(criteria):
        raise ValueError("DRACO rubric criterion IDs must be unique")
    if not any(criterion.weight > 0 for criterion in criteria):
        raise ValueError("DRACO rubric must contain a positive-weight criterion")
    return tuple(criteria)


def _rubric_document(raw: object) -> dict:
    try:
        document = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ValueError("DRACO answer is not valid rubric JSON") from exc
    if not isinstance(document, dict) or not isinstance(document.get("sections"), list):
        raise ValueError("DRACO rubric must be an object containing sections")
    return document


def _rubric_criteria(sections: list) -> list[_DracoCriterion]:
    criteria: list[_DracoCriterion] = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("DRACO rubric sections must be objects")
        axis = section.get("id") or section.get("title")
        rows = section.get("criteria")
        if not isinstance(axis, str) or not axis.strip() or not isinstance(rows, list):
            raise ValueError("DRACO rubric sections require an id and criteria list")
        for criterion in rows:
            criteria.append(_parse_criterion(criterion, axis))
    return criteria


def _parse_criterion(raw: object, axis: str) -> _DracoCriterion:
    if not isinstance(raw, dict):
        raise ValueError("DRACO rubric criteria must be objects")
    criterion_id = raw.get("id")
    requirement = raw.get("requirement")
    weight = raw.get("weight")
    if not isinstance(criterion_id, str) or not criterion_id.strip():
        raise ValueError("DRACO criteria require a non-empty id")
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("DRACO criteria require a non-empty requirement")
    if not isinstance(weight, (int, float)) or isinstance(weight, bool):
        raise ValueError("DRACO criterion weights must be numeric")
    return _DracoCriterion(criterion_id, float(weight), requirement, axis)


def _normalized_score(criteria: tuple[_DracoCriterion, ...], verdicts: dict[str, bool]) -> float:
    judged = tuple(criterion for criterion in criteria if criterion.id in verdicts)
    denominator = sum(criterion.weight for criterion in judged if criterion.weight > 0)
    if denominator <= 0:
        return 0.0
    numerator = sum(criterion.weight for criterion in judged if verdicts[criterion.id])
    return max(0.0, min(1.0, numerator / denominator))


def _pass_rate(criteria: tuple[_DracoCriterion, ...], verdicts: dict[str, bool]) -> float:
    judged = tuple(criterion for criterion in criteria if criterion.id in verdicts)
    if not judged:
        return 0.0
    correct = sum(
        (criterion.weight >= 0 and verdicts[criterion.id])
        or (criterion.weight < 0 and not verdicts[criterion.id])
        for criterion in judged
    )
    return correct / len(judged)


def _axis_score(
    criteria: tuple[_DracoCriterion, ...], verdicts: dict[str, bool], axis: str
) -> float:
    return _normalized_score(
        tuple(criterion for criterion in criteria if criterion.axis == axis), verdicts
    )


_JUDGE_INSTRUCTIONS = """You are evaluating a response for a given query against a single criterion.

You will receive the response to evaluate, a single criterion to check, and a
<criterion_type> field indicating if the criterion is positive or negative.

For positive criteria, MET means the response satisfies the desirable requirement. For negative
criteria, MET means the response actually contains the described error. Mentioning an error only
to reject, warn against, or contrast with it is UNMET.

Be strict about factual accuracy but flexible about semantically equivalent wording. Pay careful
attention to negation, conditional versus unconditional actions, numerical ranges, and requirements
that may be satisfied implicitly by the response.

Return only raw JSON with exactly these fields:
{"explanation": "Brief explanation", "criterion_status": "MET"}
criterion_status must be either MET or UNMET. Do not use Markdown fences or add a preamble."""


def _criterion_judge_prompt(*, question: str, answer: str, criterion: _DracoCriterion) -> str:
    criterion_type = "negative" if criterion.weight < 0 else "positive"
    return (
        f"{_JUDGE_INSTRUCTIONS}\n\n"
        f"<criterion_type>\n{criterion_type}\n</criterion_type>\n\n"
        f"<criterion>\n{criterion.requirement}\n</criterion>\n\n"
        f"<query>\n{question}\n</query>\n\n"
        f"<response>\n{answer}\n</response>"
    )


def _parse_criterion_verdict(raw: str) -> bool | None:
    text = raw.strip()
    if "```" in text:
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    start, end = text.find("{"), text.rfind("}")
    document = None
    if start >= 0 and end >= start:
        try:
            document = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    status = document.get("criterion_status") if isinstance(document, dict) else None
    valid = isinstance(document, dict) and isinstance(document.get("explanation"), str)
    return status == "MET" if valid and status in {"MET", "UNMET"} else None
