"""DRACO's check-surface adapter — the corrective loop's first PAID port.

FEATURE: benchmark-independent corrective loop on a rubric benchmark (OME-829).
STORY: as a client-compiled `sf.CorrectiveLoop` candidate, I ask DRACO mid-run
whether a draft is good enough to submit, and get back the same closed record
every benchmark answers with — so the loop needs zero DRACO-specific code.

Mental model: a marker with the rubric in hand and a stopwatch. Per check, in
execution order:

1. **Resolve the case** from the exact question text — a black-box `$candidate`
   only ever sees `$input`, so the check is input-addressed (never a case id).
2. **Select the criteria this variant grades with** (canonical: all; lite: 10
   axis-balanced; smoke: 1). Checking against criteria the variant never grades
   would make mid-run satisfaction and the final score incomparable.
3. **One judge pass** over those requirements, weight-blind, salted with the
   answer hash so a provider cache cannot serve one draft's verdict for another.
   An unusable reply is retried on a fresh cache slot, then fails the check.
4. **Score with the canonical math** (`normalized_score`) — already in [0, 1], so
   `satisfaction` needs no remapping; `passed` applies `draco-pass.v1`.
5. **Sanitize** the shortfall into rubric AREA names only. Feedback rides back
   into the next round's member prompt, and rubric requirement text IS the answer
   key — naming a failed requirement would hand the panel the marking scheme.

Worked example (rubric: c1 w=3, c2 w=1, c3 w=1, c4 w=-2; positives sum to 5):
a draft meeting c1 and c2 scores 4/5 = 0.8 -> passed, because 0.8 >= 0.7. The
same draft that also trips the c4 penalty scores (4-2)/5 = 0.4 -> not passed,
and its feedback names the two areas that fell short, never the requirements.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4 import RelExpr, Text, expr, render, src
from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.draco import scoring as rubric_scoring
from url4_cloud.benchmarks.draco.check_policy import (
    CHECK_ATTEMPTS,
    CHECK_CRITERION,
    CHECK_INSTRUCTIONS,
    CHECK_THRESHOLD,
    answer_salt,
    build_check_prompt,
)
from url4_cloud.benchmarks.draco.definition import JUDGE_MODEL, JUDGE_PARAMS
from url4_cloud.benchmarks.ensemble.policy import CHECK_SURFACE_SCHEMA
from url4_cloud.benchmarks.evaluation import benchmark_unavailable as _unavailable
from url4_cloud.benchmarks.evaluation import candidate_answer, compact_json, json_object

_JUDGE_ROUTE = "/" + JUDGE_MODEL.removeprefix("/")


def check_surface(
    node: Url4Node,
    root: Path,
    *,
    criterion_count: int | None,
    selection: rubric_scoring.CriterionSelection,
):
    """Build one variant's check endpoint over the shared pinned assets.

    Closes over ``node`` so the judge route resolves at REQUEST time: benchmark
    installation must keep working in worlds that hold no model routes at all.
    """

    async def check(request: Request) -> str:
        if request.intent == "feedback":
            return _surface_feedback(request.context)
        if request.intent != "check":
            raise _unsupported("DRACO check surface", request.intent)
        question, invocation, answer = _payload(request.context)
        case_id = _case_by_input(root, question)
        rubric = _rubric(root, case_id)
        try:
            criteria = rubric_scoring.select_criteria(rubric, criterion_count, selection)
        except ValueError as exc:
            raise _unavailable(f"DRACO check surface cannot select criteria: {exc}") from exc
        verdicts = await _judged(node, question=question, answer=answer, criteria=criteria)
        # Score over the JUDGED criteria only — the same subset this variant grades.
        satisfaction = rubric_scoring.normalized_score(_rubric_view(criteria), verdicts)
        record = {
            "schema": CHECK_SURFACE_SCHEMA,
            "passed": satisfaction >= CHECK_THRESHOLD,
            "satisfaction": satisfaction,
            "feedback": _area_feedback(criteria, verdicts),
            "answer": answer,
            "invocation": invocation,
        }
        return compact_json(record)

    return check


def _payload(value: object) -> tuple[str, str, str]:
    payload = json_object(value, "DRACO check surface")
    if set(payload) != {"input", "invocation"}:
        raise _unavailable("DRACO check surface context must carry exactly input and invocation")
    question = payload["input"]
    invocation = payload["invocation"]
    if not isinstance(question, str) or not isinstance(invocation, str):
        raise _unavailable("DRACO check surface input and invocation must be text")
    try:
        answer = candidate_answer(invocation).text
    except (TypeError, ValueError) as exc:
        raise _unavailable(f"DRACO check surface Candidate Invocation is invalid: {exc}") from exc
    return question, invocation, answer


def _case_by_input(root: Path, question: str) -> int:
    """Resolve the case whose pinned question is exactly ``question``.

    INVARIANT: the check is input-addressed because a black-box Candidate never
    learns a case id. Ambiguity is a bounded failure rather than a guess — a
    silently mismatched case would grade a draft against the wrong rubric.
    """

    cases = json.loads(_read(root / "cases.json", "DRACO cases"))
    if not isinstance(cases, list):
        raise _unavailable("DRACO cases must be a JSON array")
    matches = [
        case.get("id") for case in cases if isinstance(case, dict) and case.get("input") == question
    ]
    if not matches:
        raise _unavailable("no DRACO case matches the check surface input")
    if len(matches) > 1:
        raise _unavailable("the check surface input matches more than one DRACO case")
    case_id = matches[0]
    if isinstance(case_id, bool) or not isinstance(case_id, int):
        raise _unavailable("DRACO case id must be an integer")
    return case_id


def _rubric(root: Path, case_id: int) -> dict[str, Any]:
    decoded = json.loads(_read(root / "rubrics" / f"{case_id}.json", f"DRACO rubric {case_id}"))
    if not isinstance(decoded, dict):
        raise _unavailable(f"DRACO rubric {case_id} must be a JSON object")
    return decoded


def _rubric_view(criteria: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Re-frame the selected criteria as a rubric so canonical scoring applies."""

    sections: dict[str, list[Mapping[str, Any]]] = {}
    for criterion in criteria:
        sections.setdefault(str(criterion.get("axis", "unknown")), []).append(criterion)
    return {"sections": [{"id": axis, "criteria": rows} for axis, rows in sections.items()]}


async def _judged(
    node: Url4Node,
    *,
    question: str,
    answer: str,
    criteria: Sequence[Mapping[str, Any]],
) -> dict[str, bool]:
    """One judge pass, retried on a fresh cache slot while the reply is unusable."""

    prompt = build_check_prompt(question, answer, criteria)
    salt = answer_salt(answer)
    for attempt in range(1, CHECK_ATTEMPTS + 1):
        reply = await node.evaluate(
            _judge_expression(salt=salt, attempt=attempt), env={"prompt": prompt}
        )
        verdicts = _verdicts(reply.text, criteria)
        if verdicts is not None:
            return verdicts
    raise _unavailable(
        f"the DRACO check judge returned no usable verdict in {CHECK_ATTEMPTS} attempts"
    )


def _judge_expression(*, salt: str, attempt: int) -> str:
    # WHY the prompt is an env binding, not inlined: it carries the Candidate's own
    # answer, and a quote or comma in that text would corrupt the rendered
    # expression. WHY the salt/attempt params: the gateway's exact-response cache
    # keys on the request, so a per-draft salt stops one draft's verdict serving
    # another, and the attempt counter keeps a retry from replaying a cached
    # unusable reply.
    return render(
        expr(
            src(
                RelExpr(
                    path=_JUDGE_ROUTE,
                    context="$prompt",
                    intent=Text(CHECK_INSTRUCTIONS),
                    params=(
                        *JUDGE_PARAMS,
                        ("check_salt", salt),
                        ("check_attempt", str(attempt)),
                    ),
                ),
                name="verdict",
                weight=0.0,
            ),
            intent=Text("$verdict"),
        )
    )


def _verdicts(
    reply: str,
    criteria: Sequence[Mapping[str, Any]],
) -> dict[str, bool] | None:
    """Map an ordinal-keyed judge reply onto criterion ids, or None if unusable.

    Every selected requirement must carry exactly one MET/UNMET verdict: a partial
    reply would silently score unjudged criteria as failed. A repeated ordinal
    collapses in the mapping and so fails the same completeness check.
    """

    decoded = _decoded_array(reply)
    if decoded is None or len(decoded) != len(criteria):
        return None
    verdicts: dict[str, bool] = {}
    for row in decoded:
        judged = _verdict_row(row, len(criteria))
        if judged is None:
            break
        ordinal, met = judged
        verdicts[str(criteria[ordinal - 1]["id"])] = met
    return verdicts if len(verdicts) == len(criteria) else None


def _verdict_row(row: object, count: int) -> tuple[int, bool] | None:
    """One `{id, status}` reply row, validated against the requirement ordinals."""

    if not isinstance(row, dict):
        return None
    ordinal = row.get("id")
    status = row.get("status")
    numbered = not isinstance(ordinal, bool) and isinstance(ordinal, int) and 1 <= ordinal <= count
    decided = isinstance(status, str) and status.strip().upper() in {"MET", "UNMET"}
    if not (numbered and decided):
        return None
    assert isinstance(ordinal, int) and isinstance(status, str)
    return ordinal, status.strip().upper() == "MET"


def _decoded_array(reply: str) -> list[object] | None:
    text = _without_fences(reply)
    start = text.find("[")
    if start < 0:
        return None
    try:
        decoded, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return decoded if isinstance(decoded, list) else None


def _without_fences(reply: str) -> str:
    return "\n".join(line for line in (reply or "").splitlines() if not line.startswith("```"))


def _area_feedback(
    criteria: Sequence[Mapping[str, Any]],
    verdicts: Mapping[str, bool],
) -> str:
    """Name the rubric AREAS that fell short — never a requirement.

    INVARIANT (sealed envelope): this text is the only thing the check sends back
    toward the Candidate, and rubric requirements are the answer key. Axis names
    are categories the panel could infer from the question anyway; requirement
    text is the marking scheme itself.
    """

    areas: list[str] = []
    for criterion in criteria:
        weight = float(criterion.get("weight", 0))
        met = bool(verdicts.get(str(criterion["id"]), False))
        shortfall = (weight >= 0 and not met) or (weight < 0 and met)
        area = str(criterion.get("axis", "unknown"))
        if shortfall and area not in areas:
            areas.append(area)
    if not areas:
        return ""
    return "The answer did not satisfy these rubric areas: " + " | ".join(areas)


def _surface_feedback(value: object) -> str:
    record = json_object(value, "DRACO check-surface feedback")
    if record.get("schema") != CHECK_SURFACE_SCHEMA:
        raise _unavailable(f"feedback input must be a {CHECK_SURFACE_SCHEMA} check-surface record")
    feedback = record.get("feedback")
    if not isinstance(feedback, str):
        raise _unavailable("check-surface record feedback must be text")
    return feedback


def _unsupported(label: str, intent: str) -> ResolutionError:
    return ResolutionError(
        f"unsupported {label} operation {intent!r}",
        code="benchmark_operation_unsupported",
        permanent=True,
    )


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _unavailable(f"could not read {label} at {str(path)!r}: {exc}") from exc


__all__ = [
    "CHECK_CRITERION",
    "CHECK_INSTRUCTIONS",
    "CHECK_THRESHOLD",
    "check_surface",
]
