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


_JUDGE_SYSTEM_PROMPT = """You are evaluating a response for a given query against a single \
criterion.

You will receive the response to evaluate, a single criterion to check, and a \
<criterion_type> field indicating if the criterion is positive or negative.

CRITERION TYPES:
The <criterion_type> field tells you whether this criterion describes something desirable \
(positive) or undesirable (negative). Your job is THE SAME for both types: determine if the thing \
described in the criterion is actually present in the response.

POSITIVE CRITERIA:
Positive criteria describe desired traits, requirements, or content that should be present.
- MET (criterion_status: "MET"): The response contains/satisfies the requirement
- UNMET (criterion_status: "UNMET"): The response does not contain/satisfy the requirement

NEGATIVE CRITERIA:
Negative criteria describe active errors or mistakes that the response is making.
- MET (criterion_status: "MET"): The response advocates, states, or recommends the problematic thing
- UNMET (criterion_status: "UNMET"): The response does NOT make this error, OR it mentions \
the thing only to warn against it or mention why it's wrong

Examples of what does NOT count as MET for negative criteria:
- "This is often misdiagnosed as X, but it's actually Y" → NOT stating it's X (UNMET)
- "Avoid doing X because..." → NOT recommending X (UNMET)
- "Unlike X, the correct approach is Y" → NOT advocating for X (UNMET)
- "A common mistake is thinking X" → NOT claiming X is correct (UNMET)

EVALUATION RULES:
- For numerical values: Check if they fall within specified ranges or match exactly as required.
- For factual claims: Verify the information is present and accurate, regardless of exact phrasing.
- For required elements: Confirm presence, counting precisely when numbers are specified.
- For exclusion requirements: Confirm that restricted content is absent.
- For length requirements: Carefully measure the number of words, characters, items, etc.
- Be strict about factual accuracy but flexible about wording.
- Accept semantically equivalent statements or implications where appropriate.
- Pay careful attention to negation, warnings, and contrasts.

CONDITIONAL VS UNCONDITIONAL ACTIONS (CRITICAL):
When a criterion requires an action to be done "immediately", "now", "as soon as possible", or \
unconditionally, you must distinguish:
- UNCONDITIONAL: "Give epinephrine now" or "Administer X immediately" → action IS being taken
- CONDITIONAL: "If Y occurs, give epinephrine" or "Start X if condition Z" → action is NOT being \
taken immediately; it's contingent on a future condition

If the criterion says something should happen "immediately" or without conditions, a conditional \
statement does NOT satisfy the criterion. Mark as UNMET.

Example:
- Criterion: "Administers alteplase immediately for acute ischemic stroke"
- Output: "If CT confirms no hemorrhage, consider alteplase" → UNMET (conditional, not immediate)
- Output: "Give alteplase now per acute stroke protocol" → MET (immediate, unconditional)

IMPLICIT VS EXPLICIT SATISFACTION:
Consider whether a criterion can be satisfied implicitly through context, tone, or logical \
implication, not just explicit statements:
- "States there is no location in China" can be MET by "Locations are only in United States and \
Canada"—if locations are ONLY in US and Canada, China is excluded; no need to mention China
- "Confirms the user is logged out" can be MET by "Session expired at 3:42 PM"—an expired session \
means the user is logged out, even without stating it directly

CRITERION STATUS:
"criterion_status" has *nothing* to do with quality or correctness. It only means:
- "MET": The thing described in the criterion IS present/occurring in the response
- "UNMET": The thing described in the criterion IS NOT present/occurring in the response

Your response must be valid JSON with this exact format:

{
"explanation": "Brief explanation of why the criterion is MET.",
"criterion_status": "MET"
}

Examples:

Positive criterion: "States Q4 2023 base margin as 17.2%"
Response: "The Q4 2023 base margin was 17.2% before adjustments."
{
"explanation": "The response states Q4 2023 base margin as 17.2%, as required.",
"criterion_status": "MET"
}

Negative criterion: "States that the patient has celiac disease"
Response: "This patient does not have celiac disease."
{
"explanation": "The response explicitly states the patient does NOT have celiac disease, so \
this error is not present.",
"criterion_status": "UNMET"
}

Positive criterion: "Administers epinephrine immediately for anaphylaxis"
Response: "If symptoms worsen, give epinephrine and call for help."
{
"explanation": "Epinephrine is mentioned only as a conditional action contingent on symptom \
worsening, not as an immediate intervention.",
"criterion_status": "UNMET"
}

Positive criterion: "States there is no location in China"
Response: "Locations are only in United States and Canada."
{
"explanation": "If locations are only in US and Canada, China is excluded. The response logically \
entails no China location without mentioning China.",
"criterion_status": "MET"
}

Return only raw JSON starting with {, no back-ticks, no 'json' prefix."""


_JUDGE_USER_TEMPLATE = (
    "<criterion_type>\n"
    "{criterion_type}\n"
    "</criterion_type>\n\n"
    "<criterion>\n"
    "{criterion_requirement}\n"
    "</criterion>\n\n"
    "{query_block}\n\n"
    "<response>\n"
    "{model_answer}\n"
    "</response>"
)


def _criterion_judge_user_prompt(*, question: str, answer: str, criterion: _DracoCriterion) -> str:
    criterion_type = "negative" if criterion.weight < 0 else "positive"
    query_block = f"<query>{question}</query>" if question else ""
    return _JUDGE_USER_TEMPLATE.format(
        criterion_type=criterion_type,
        criterion_requirement=criterion.requirement,
        query_block=query_block,
        model_answer=answer,
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
