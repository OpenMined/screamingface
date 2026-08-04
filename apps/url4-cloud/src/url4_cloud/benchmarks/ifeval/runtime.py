"""Install IFEval's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.ifeval import aggregate as scoring
from url4_cloud.benchmarks.ifeval import grading
from url4_cloud.benchmarks.ifeval.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASES_ROUTE,
    CHECK_ROUTE,
)
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    AGGREGATE_ROUTE as CORRECTIVE_AGGREGATE_ROUTE,
)
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MEMBER_LETTERS,
    MIN_MEMBERS,
    SELECT_ROUTE,
)


def install(node: Url4Node, root: Path) -> None:
    """Register the shared family runtime for both IFEval protocols."""

    node.data(CASES_ROUTE, _cases(root), media_type="application/json")
    node.endpoint(CHECK_ROUTE)(_check(root))
    node.endpoint(AGGREGATE_ROUTE)(_aggregate(root))
    node.endpoint(CORRECTIVE_AGGREGATE_ROUTE)(_aggregate_corrective(root))
    node.endpoint(SELECT_ROUTE)(_select)


def _cases(root: Path):
    def cases() -> str:
        return _read(root / "cases.json", "IFEval cases")

    return cases


def _check(root: Path):
    """Authoritative per-Case Grading record consumed only by Aggregation."""

    def check(request: Request) -> str:
        if request.intent == "feedback":
            return _feedback(request.context)
        try:
            case_id, attempt = _case_and_attempt(request.intent)
            spec, result, violations = _verification(root, case_id, request.context)
        except (KeyError, TypeError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        record = {
            "schema": scoring.SCHEMA,
            "case_id": case_id,
            "attempt": attempt,
            "valid": True,
            "instruction_id_list": spec["instruction_id_list"],
            "strict": result["strict"],
            "loose": result["loose"],
            # Keep this record flat: Aggregation deliberately harvests flat records.
            "violations": violations,
        }
        return _json(record)

    return check


def _feedback(record_json: str) -> str:
    """Return sanitized retry guidance without exposing private grading identifiers."""

    try:
        record = json.loads(record_json or "")
    except ValueError as exc:
        raise _unavailable(f"feedback input must be a check record: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != scoring.SCHEMA:
        raise _unavailable("feedback input must be an IFEval check record")
    strict = record.get("strict")
    violations = record.get("violations")
    if not isinstance(strict, list) or not isinstance(violations, list):
        raise _unavailable("feedback input record is missing strict/violations")
    if all(bool(value) for value in strict):
        return "PASSED"
    described = " | ".join(str(item) for item in violations) or "unspecified requirement"
    return f"The answer failed these requirements: {described}"


def _verification(
    root: Path,
    case_id: int,
    response: str,
) -> tuple[dict[str, Any], dict[str, list[bool]], list[str]]:
    spec = json.loads(
        _read(root / "instructions" / f"{case_id}.json", f"IFEval case {case_id} spec")
    )
    grading.configure_nltk(root / "nltk_data")
    result = grading.check_case(
        instruction_id_list=spec["instruction_id_list"],
        kwargs_list=spec["kwargs"],
        prompt=spec["prompt"],
        response=response,
    )
    violations = grading.describe_failures(
        instruction_id_list=spec["instruction_id_list"],
        kwargs_list=spec["kwargs"],
        prompt=spec["prompt"],
        strict=result["strict"],
    )
    return spec, result, violations


def _aggregate(root: Path):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise _unsupported("IFEval aggregation", request.intent)
        try:
            result = scoring.aggregate(
                request.context,
                scoring.load_specs(root / "instructions"),
                BENCHMARK_ID,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return _json(result)

    return aggregate


def _aggregate_corrective(root: Path):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise _unsupported("IFEval corrective aggregation", request.intent)
        try:
            result = scoring.aggregate_corrective(
                request.context,
                scoring.load_specs(root / "instructions"),
                "ifeval-iterative-correction",
                max_attempts=MAX_ATTEMPTS,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return _json(result)

    return aggregate


def _select(request: Request) -> str:
    """Deterministically select one member answer, verbatim.

    The payload carries each member's answer (keys a..d), each answer's checker verdict
    (keys fa..fd, the literal PASSED or a failure text), and the judge's reply (pick).

    Selection rules, in order:
    1. Exactly one answer PASSED the checker -> that answer wins. The judge cannot
       discard the only compliant draft.
    2. Two or more answers PASSED -> the judge's letter chooses among them; a letter
       naming a failing answer (or no valid letter) falls back to the first passer.
    3. No answer PASSED -> the judge's letter stands, so this attempt's grading record
       reflects the judged pick; without a valid letter the first answer stands.

    INVARIANT: the returned text is always a member's exact answer — selection can
    choose but never rewrite, so it cannot break a requirement a member satisfied.
    """

    if request.intent != "select":
        raise _unsupported("IFEval corrective selection", request.intent)
    payload = _json_payload(request.context, "selection")
    answers = [
        (letter, value)
        for letter in MEMBER_LETTERS
        if isinstance((value := payload.get(letter)), str)
    ]
    if not MIN_MEMBERS <= len(answers) <= MAX_MEMBERS:
        raise _unavailable(
            f"selection input must carry {MIN_MEMBERS}..{MAX_MEMBERS} member answers"
        )
    selected = {letter.upper(): answer for letter, answer in answers}
    passers = [
        letter for letter, _ in answers if str(payload.get(f"f{letter}", "")).strip() == "PASSED"
    ]
    pick = _judge_letter(payload.get("pick"), selected)
    if passers:
        judged = pick if pick is not None and pick.lower() in passers else passers[0].upper()
        return selected[judged]
    return selected[pick] if pick is not None else answers[0][1]


def _judge_letter(reply: object, selected: dict[str, str]) -> str | None:
    """Accept only an unambiguous single-letter judge reply; prose gets no vote.

    A letter names a member answer (``a`` = member 1's answer, ``b`` = member 2's,
    and so on). Anything else — prose, an empty reply, a letter outside the answer
    set — returns None so ``_select``'s deterministic fallbacks apply.
    """

    raw = str(reply or "").strip().upper()
    if not raw:
        return None
    token = raw.split()[0].strip(".,:;!()[]'\"")
    return token if len(token) == 1 and token in selected else None


def _json_payload(context: str, label: str) -> dict[str, object]:
    try:
        payload = json.loads(context or "")
    except ValueError as exc:
        raise _unavailable(f"{label} input must be JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise _unavailable(f"{label} input must be a JSON object")
    return payload


def _case_and_attempt(value: str) -> tuple[int, int]:
    case_part, _, attempt_part = (value or "").partition(":")
    case_id = _positive_int(case_part, "case id")
    attempt = _positive_int(attempt_part, "attempt") if attempt_part else 1
    return case_id, attempt


def _positive_int(value: object, label: str) -> int:
    try:
        selected = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"IFEval {label} must be an integer, got {value!r}") from None
    if selected < 1:
        raise ValueError(f"IFEval {label} must be positive, got {selected}")
    return selected


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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


def _unavailable(detail: str) -> ResolutionError:
    return ResolutionError(detail, code="benchmark_unavailable", permanent=True)


__all__ = ["install"]
