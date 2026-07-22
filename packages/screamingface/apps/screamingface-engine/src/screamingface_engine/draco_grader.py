"""Versioned engine-side implementation of DRACO's per-criterion judge protocol."""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from statistics import fmean, stdev
from typing import NoReturn

from url4 import Request, ResolutionError

from screamingface_engine.benchmark_definitions._draco_prompt import DRACO_JUDGE_PROMPT
from screamingface_engine.catalog import ModelRoute
from screamingface_engine.evaluation_events import emit_progress
from screamingface_engine.executor import ModelExecutor

DRACO_RUBRIC_ROUTE = "/graders/draco-rubric/1"
DRACO_LITE_RUBRIC_ROUTE = "/graders/draco-lite-rubric/1"
DRACO_PREVIEW_RUBRIC_ROUTE = "/graders/draco-preview-rubric/1"
DRACO_JUDGE_MODEL = "openrouter/google/gemini-3.1-pro-preview"
DRACO_JUDGE_PASSES = 5
DRACO_LITE_JUDGE_PASSES = 1
DRACO_PREVIEW_JUDGE_PASSES = 1
DRACO_JUDGE_PARAMS = {
    "temperature": "0.2",
    "reasoning": "low",
    "max_tokens": "4096",
}
VALIDATION_RETRIES = 2
DEFAULT_JUDGE_CONCURRENCY = 32
RECIPE_RESULT_SCHEMA = "screamingface.recipe-result.v1"
CASE_GRADE_SCHEMA = "screamingface.case-grade.v1"

_METRIC_KEY_RE = re.compile(r"[^a-z0-9]+")


class DracoRubricGrader:
    """Grade a resolved Recipe and its members without exposing rubric weights to the judge."""

    def __init__(
        self,
        executor: ModelExecutor,
        judge: ModelRoute,
        *,
        passes: int,
        concurrency: int = DEFAULT_JUDGE_CONCURRENCY,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._executor = executor
        self._judge = judge
        self._passes = passes
        # The composition root supplies one shared gate to every registered DRACO grader.
        # A directly constructed grader still owns a stable gate across all of its calls.
        self._semaphore = semaphore or asyncio.Semaphore(concurrency)

    async def __call__(self, request: Request) -> str:
        if request.params:
            _invalid(f"DRACO rubric grader does not accept parameters: {sorted(request.params)}")
        recipe = _object(request.context, "DRACO Recipe result")
        case = _object(request.intent, "DRACO case payload")
        _exact_fields(recipe, {"schema", "members", "answer"}, "DRACO Recipe result")
        _exact_fields(
            case,
            {"benchmark_id", "case_id", "question", "reference"},
            "DRACO case payload",
        )
        if recipe["schema"] != RECIPE_RESULT_SCHEMA:
            _invalid(f"expected Recipe schema {RECIPE_RESULT_SCHEMA!r}")

        benchmark_id = _nonblank(case["benchmark_id"], "benchmark ID")
        case_id = _nonblank(case["case_id"], "case ID")
        operation_id = f"grading:{benchmark_id}:{case_id}"
        emit_progress(
            "grading",
            "started",
            f"Grading DRACO case {case_id}",
            operation_id=operation_id,
        )
        question = _nonblank(case["question"], "case question", strip=False)
        rubric = _rubric(case["reference"])
        answer = _nonblank(recipe["answer"], "Recipe answer", strip=False)
        raw_members = recipe["members"]
        if not isinstance(raw_members, Mapping) or not raw_members:
            _invalid("Recipe members must be a non-empty object")

        targets: list[tuple[str, str, str]] = []
        for position, (member_id, raw_member) in enumerate(raw_members.items(), 1):
            if member_id != f"member_{position}" or not isinstance(raw_member, Mapping):
                _invalid("Recipe members must be contiguous member_1 through member_n objects")
            _exact_fields(raw_member, {"model", "answer"}, f"member {member_id!r}")
            targets.append(
                (
                    member_id,
                    _nonblank(raw_member["model"], f"member {member_id!r} model"),
                    _nonblank(raw_member["answer"], f"member {member_id!r} answer", strip=False),
                )
            )

        # Identical answer text is graded once. This keeps an atomic Model's Recipe and member
        # scores identical and avoids paying twice for the same judging work.
        cache: dict[str, dict[str, object]] = {}

        async def grade(value: str) -> dict[str, object]:
            existing = cache.get(value)
            if existing is None:
                existing = await self._grade_answer(question, rubric, value)
                cache[value] = existing
            return existing

        recipe_grade = await grade(answer)
        member_grades: dict[str, object] = {}
        for member_id, model, member_answer in targets:
            member_grades[member_id] = {"model": model, **await grade(member_answer)}

        payload = {
            "schema": CASE_GRADE_SCHEMA,
            "benchmark_id": benchmark_id,
            "case_id": case_id,
            "recipe": recipe_grade,
            "members": member_grades,
        }
        emit_progress(
            "grading",
            "completed",
            f"Graded DRACO case {case_id}",
            operation_id=operation_id,
        )
        return json.dumps(payload, allow_nan=False, separators=(",", ":"))

    async def grade_answer(
        self,
        question: str,
        reference: object,
        answer: str,
    ) -> dict[str, object]:
        """Grade one final candidate answer without recursively grading its members."""

        return await self._grade_answer(
            _nonblank(question, "case question", strip=False),
            _rubric(reference),
            _nonblank(answer, "candidate answer", strip=False),
        )

    async def _grade_answer(  # noqa: C901
        self,
        question: str,
        rubric: dict[str, object],
        answer: str,
    ) -> dict[str, object]:
        criteria = _criteria(rubric)

        async def judge(run: int, position: int) -> tuple[int, int, dict[str, str] | None]:
            criterion = criteria[position]
            weight = _stored_weight(criterion)
            context = _judge_context(
                question,
                _nonblank(criterion["requirement"], "criterion requirement", strip=False),
                "negative" if weight < 0 else "positive",
                answer,
            )
            for _attempt in range(VALIDATION_RETRIES + 1):
                async with self._semaphore:
                    raw = await self._executor.complete(
                        self._judge,
                        Request(
                            self._judge.route,
                            context,
                            DRACO_JUDGE_PROMPT,
                            DRACO_JUDGE_PARAMS,
                        ),
                    )
                parsed = _judge_output(raw)
                if parsed is not None:
                    return run, position, parsed
            return run, position, None

        tasks = [
            asyncio.create_task(judge(run, position))
            for run in range(self._passes)
            for position in range(len(criteria))
        ]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        by_run: list[dict[str, bool]] = [dict() for _ in range(self._passes)]
        for run, position, verdict in results:
            if verdict is not None:
                by_run[run][str(criteria[position]["id"])] = verdict["criterion_status"] == "MET"

        run_scores: list[float] = []
        run_pass_rates: list[float] = []
        run_coverages: list[float] = []
        run_axes: list[dict[str, float]] = []
        run_axis_pass_rates: list[dict[str, float]] = []
        for verdicts in by_run:
            if not verdicts:
                continue
            selected = tuple(item for item in criteria if str(item["id"]) in verdicts)
            run_scores.append(_normalized_score(selected, verdicts))
            run_pass_rates.append(_pass_rate(selected, verdicts))
            run_coverages.append(len(verdicts) / len(criteria))
            run_axes.append(_axis_scores(selected, verdicts))
            run_axis_pass_rates.append(_axis_pass_rates(selected, verdicts))

        if not run_scores:
            raise ResolutionError(
                "DRACO judge returned no valid per-criterion verdicts",
                code="invalid_judge_response",
            )
        score = fmean(run_scores)
        coverage = fmean(run_coverages)
        metrics: dict[str, float] = {
            "normalized_score": score,
            "normalized_score_std": stdev(run_scores) if len(run_scores) > 1 else 0.0,
            "pass_rate": fmean(run_pass_rates),
            "pass_rate_std": stdev(run_pass_rates) if len(run_pass_rates) > 1 else 0.0,
            "verdict_coverage": coverage,
            "verdict_coverage_std": (stdev(run_coverages) if len(run_coverages) > 1 else 0.0),
            "judge_run_coverage": len(run_scores) / self._passes,
        }
        axes = sorted({axis for values in run_axes for axis in values})
        for axis in axes:
            key = _metric_key(axis)
            metrics[f"axis_{key}"] = fmean(values.get(axis, 0.0) for values in run_axes)
            metrics[f"axis_{key}_pass_rate"] = fmean(
                values.get(axis, 0.0) for values in run_axis_pass_rates
            )
        return {"score": score, "metrics": metrics, "coverage": coverage}


def _judge_context(question: str, requirement: str, criterion_type: str, answer: str) -> str:
    return (
        f"<criterion_type>\n{criterion_type}\n</criterion_type>\n\n"
        f"<criterion>\n{requirement}\n</criterion>\n\n"
        f"<query>{question}</query>\n\n"
        f"<response>\n{answer}\n</response>"
    )


def _rubric(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _invalid("DRACO reference must be a rubric object")
    _criteria(value)
    return value


def _criteria(rubric: Mapping[str, object]) -> tuple[dict[str, object], ...]:  # noqa: C901
    sections = rubric.get("sections")
    if not isinstance(sections, list) or not sections:
        _invalid("DRACO rubric must contain sections")
    values: list[dict[str, object]] = []
    ids: set[str] = set()
    for raw_section in sections:
        if not isinstance(raw_section, Mapping):
            _invalid("DRACO rubric sections must be objects")
        axis = raw_section.get("id") or raw_section.get("title")
        axis_name = _nonblank(axis, "rubric section axis")
        raw_criteria = raw_section.get("criteria")
        if not isinstance(raw_criteria, list) or not raw_criteria:
            _invalid("DRACO rubric sections must contain criteria")
        for raw in raw_criteria:
            if not isinstance(raw, Mapping):
                _invalid("DRACO rubric criteria must be objects")
            criterion_id = _nonblank(raw.get("id"), "criterion ID")
            if criterion_id in ids:
                _invalid(f"duplicate criterion ID {criterion_id!r}")
            ids.add(criterion_id)
            requirement = _nonblank(raw.get("requirement"), "criterion requirement", strip=False)
            weight = raw.get("weight")
            if isinstance(weight, bool) or not isinstance(weight, int | float):
                _invalid(f"criterion {criterion_id!r} weight must be numeric")
            normalized = float(weight)
            if not math.isfinite(normalized) or normalized == 0:
                _invalid(f"criterion {criterion_id!r} weight must be finite and non-zero")
            values.append(
                {
                    "id": criterion_id,
                    "requirement": requirement,
                    "weight": normalized,
                    "axis": axis_name,
                }
            )
    if not values:
        _invalid("DRACO rubric must contain criteria")
    return tuple(values)


def _judge_output(raw: str) -> dict[str, str] | None:
    text = raw.strip()
    if "```" in text:
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    candidates = (text, _first_json_object(text))
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            value = json.loads(candidate, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(value, dict)
            and set(value) == {"explanation", "criterion_status"}
            and isinstance(value["explanation"], str)
            and value["explanation"].strip()
            and value["criterion_status"] in {"MET", "UNMET"}
        ):
            return {
                "explanation": value["explanation"],
                "criterion_status": value["criterion_status"],
            }
    return None


def _first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    quoted = False
    escaped = False
    for position, character in enumerate(text[start:], start):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quoted:
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : position + 1]
    return None


def _normalized_score(
    criteria: tuple[dict[str, object], ...], verdicts: Mapping[str, bool]
) -> float:
    achieved = 0.0
    possible = 0.0
    for criterion in criteria:
        weight = _stored_weight(criterion)
        met = verdicts[str(criterion["id"])]
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
        if (_stored_weight(criterion) > 0) == verdicts[str(criterion["id"])]
    )
    return correct / len(criteria)


def _axis_scores(
    criteria: tuple[dict[str, object], ...], verdicts: Mapping[str, bool]
) -> dict[str, float]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for criterion in criteria:
        grouped[str(criterion["axis"])].append(criterion)
    return {axis: _normalized_score(tuple(values), verdicts) for axis, values in grouped.items()}


def _axis_pass_rates(
    criteria: tuple[dict[str, object], ...], verdicts: Mapping[str, bool]
) -> dict[str, float]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for criterion in criteria:
        grouped[str(criterion["axis"])].append(criterion)
    return {axis: _pass_rate(tuple(values), verdicts) for axis, values in grouped.items()}


def _metric_key(value: str) -> str:
    return _METRIC_KEY_RE.sub("_", value.casefold()).strip("_") or "unknown"


def _stored_weight(criterion: Mapping[str, object]) -> float:
    value = criterion["weight"]
    if not isinstance(value, float):
        _invalid("normalized criterion weight must be a float")
    return value


def _object(text: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, ValueError):
        _invalid(f"{label} must be a unique-key JSON object")
    if not isinstance(value, dict):
        _invalid(f"{label} must be a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field {key!r}")
        value[key] = item
    return value


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        _invalid(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        _invalid(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def _nonblank(value: object, label: str, *, strip: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} must be a non-blank string")
    return value.strip() if strip else value


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = [
    "DRACO_JUDGE_MODEL",
    "DRACO_JUDGE_PARAMS",
    "DRACO_JUDGE_PASSES",
    "DRACO_LITE_JUDGE_PASSES",
    "DRACO_LITE_RUBRIC_ROUTE",
    "DRACO_PREVIEW_JUDGE_PASSES",
    "DRACO_PREVIEW_RUBRIC_ROUTE",
    "DRACO_RUBRIC_ROUTE",
    "DracoRubricGrader",
]
