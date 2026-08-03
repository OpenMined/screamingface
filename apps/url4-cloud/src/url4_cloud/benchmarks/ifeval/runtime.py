"""Install IFEval's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from pathlib import Path

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.ifeval import aggregate as scoring
from url4_cloud.benchmarks.ifeval import grading
from url4_cloud.benchmarks.ifeval.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASES_ROUTE,
    CHECK_ROUTE,
    CORRECTIVE_AGGREGATE_ROUTE,
    FINALIZE_ROUTE,
    MAX_ATTEMPTS,
    SELECT_ROUTE,
)


def install(node: Url4Node, root: Path) -> None:
    """Register every route referenced by either IFEval method's expression.

    Providers read lazily so a general-purpose Runner can carry the installed definition
    without requiring IFEval's private assets until an expression actually selects it.
    Both methods share cases/check/assets; each method has its own reducer route. The
    select/finalize actions serve candidate-side verifier loops (OME-727).
    """

    node.data(CASES_ROUTE, _cases(root), media_type="application/json")
    node.endpoint(CHECK_ROUTE)(_check(root))
    node.endpoint(AGGREGATE_ROUTE)(_aggregate(root))
    node.endpoint(CORRECTIVE_AGGREGATE_ROUTE)(_aggregate_corrective(root))
    node.endpoint(SELECT_ROUTE)(_select)
    node.endpoint(FINALIZE_ROUTE)(_finalize)


def _cases(root: Path):
    def cases() -> str:
        return _read(root / "cases.json", "IFEval cases")

    return cases


def _check(root: Path):
    def check(request: Request) -> str:
        if request.intent == "feedback":
            return _feedback(request.context)
        try:
            case_id, attempt = _case_and_attempt(request.intent)
            spec = json.loads(
                _read(root / "instructions" / f"{case_id}.json", f"IFEval case {case_id} spec")
            )
            grading.configure_nltk(root / "nltk_data")
            result = grading.check_case(
                instruction_id_list=spec["instruction_id_list"],
                kwargs_list=spec["kwargs"],
                prompt=spec["prompt"],
                response=request.context,
            )
            violations = grading.describe_failures(
                instruction_id_list=spec["instruction_id_list"],
                kwargs_list=spec["kwargs"],
                prompt=spec["prompt"],
                strict=result["strict"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        record = {
            "schema": scoring.SCHEMA,
            "case_id": case_id,
            # WHY attempt rides in the record: the corrective reducer groups a case's
            # records by attempt to compute pass@attempt; the plain reducer ignores it.
            "attempt": attempt,
            "valid": True,
            "instruction_id_list": spec["instruction_id_list"],
            "strict": result["strict"],
            "loose": result["loose"],
            # AIDEV-NOTE: keep this record FLAT (no nested objects, no free candidate
            # text) — the reducers harvest it with a non-nested {...} span regex.
            "violations": violations,
        }
        return json.dumps(record, ensure_ascii=False, separators=(",", ":"))

    return check


def _aggregate(root: Path):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise ResolutionError(
                f"unsupported IFEval operation {request.intent!r}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        try:
            result = scoring.aggregate(
                request.context,
                scoring.load_specs(root / "instructions"),
                BENCHMARK_ID,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return aggregate


def _feedback(record_json: str) -> str:
    """One check record in → the text a candidate MEMBER may see.

    INVARIANT: members only ever receive the checker's violation DESCRIPTIONS (or
    ``PASSED``) — never raw records or instruction ids. The anti-forgery gate in the
    reducers assumes candidates cannot know the private instruction id list; leaking
    a record here would hand them the forgery template.
    """

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


def _select(request: Request) -> str:
    """Judge letter + member answers in → the picked answer VERBATIM.

    INVARIANT: the judge only ever chooses; this deterministic route returns the
    winning text untouched, so a judge cannot mutate the answer (IFEval punishes
    exactly that kind of mutation). Unparseable pick → the first answer.
    """

    if request.intent != "select":
        raise _unsupported("IFEval select", request.intent)
    payload = _json_payload(request.context, "select")
    answers: list[tuple[str, str]] = []
    for name in ("a", "b", "c", "d"):
        value = payload.get(name)
        if isinstance(value, str):
            answers.append((name, value))
    if not answers:
        raise _unavailable("select input carries no member answers")
    pick = str(payload.get("pick", ""))
    chosen = next(
        (letter for letter in pick.upper() if letter in {name.upper() for name, _ in answers}),
        None,
    )
    by_name = dict(answers)
    return by_name[chosen.lower()] if chosen else answers[0][1]


def _finalize(request: Request) -> str:
    """Per-attempt selections + verdicts in → the earliest PASSED selection, else last."""

    if request.intent != "finalize":
        raise _unsupported("IFEval finalize", request.intent)
    payload = _json_payload(request.context, "finalize")
    last: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        selection = payload.get(f"s{attempt}")
        if not isinstance(selection, str):
            continue
        last = selection
        if str(payload.get(f"f{attempt}", "")).strip() == "PASSED":
            return selection
    if last is None:
        raise _unavailable("finalize input carries no selections")
    return last


def _json_payload(context: str, label: str) -> dict[str, object]:
    try:
        payload = json.loads(context or "")
    except ValueError as exc:
        raise _unavailable(f"{label} input must be JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise _unavailable(f"{label} input must be a JSON object")
    return payload


def _unsupported(label: str, intent: str) -> ResolutionError:
    return ResolutionError(
        f"unsupported {label} operation {intent!r}",
        code="benchmark_operation_unsupported",
        permanent=True,
    )


def _case_and_attempt(value: str) -> tuple[int, int]:
    """Parse ``<case>`` (plain exam) or ``<case>:<attempt>`` (corrective chain)."""

    case_part, _, attempt_part = (value or "").partition(":")
    case_id = _positive_int(case_part, "case id")
    attempt = _positive_int(attempt_part, "attempt") if attempt_part else 1
    return case_id, attempt


def _positive_int(value: str, label: str) -> int:
    try:
        selected = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"IFEval check intent {label} must be an integer, got {value!r}") from None
    if selected < 1:
        raise ValueError(f"IFEval check intent {label} must be positive, got {selected}")
    return selected


def _aggregate_corrective(root: Path):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise ResolutionError(
                f"unsupported IFEval corrective operation {request.intent!r}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        try:
            result = scoring.aggregate_corrective(
                request.context,
                scoring.load_specs(root / "instructions"),
                BENCHMARK_ID,
                max_attempts=MAX_ATTEMPTS,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return aggregate


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _unavailable(f"could not read {label} at {str(path)!r}: {exc}") from exc


def _unavailable(detail: str) -> ResolutionError:
    return ResolutionError(
        detail,
        code="benchmark_unavailable",
        permanent=True,
    )


__all__ = ["install"]
