"""Install IFEval's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from url4 import Expression, RelExpr, Source, Text, build, render
from url4.core.errors import ParseError, RenderError, ResolutionError
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
    ENSEMBLE_AGGREGATE_ROUTE,
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MEMBER_ANSWER_ROUTE,
    MEMBER_LETTERS,
    MEMBER_RECORD_ROUTE,
    MIN_MEMBERS,
    RESOLVE_CANDIDATE_ROUTE,
    SELECT_ROUTE,
    SELF_AGGREGATE_ROUTE,
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
    VERIFYING_ENSEMBLE_ID,
    VERIFYING_ENSEMBLE_REVISION,
)


def install(node: Url4Node, root: Path, model_routes: frozenset[str]) -> None:
    """Register the shared runtime for all installed IFEval Variants."""

    node.data(CASES_ROUTE, _cases(root), media_type="application/json")
    node.endpoint(CHECK_ROUTE)(_check(root))
    node.endpoint(AGGREGATE_ROUTE)(_aggregate(root))
    node.endpoint(SELF_AGGREGATE_ROUTE)(
        _aggregate_corrective(root, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION)
    )
    node.endpoint(ENSEMBLE_AGGREGATE_ROUTE)(
        _aggregate_corrective(root, VERIFYING_ENSEMBLE_ID, VERIFYING_ENSEMBLE_REVISION)
    )
    node.endpoint(SELECT_ROUTE)(_select)
    node.endpoint(RESOLVE_CANDIDATE_ROUTE)(_resolve_candidate(model_routes))
    node.endpoint(MEMBER_RECORD_ROUTE)(_member_record)
    node.endpoint(MEMBER_ANSWER_ROUTE)(_member_answer)


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


def _aggregate_corrective(root: Path, benchmark_id: str, benchmark_revision: str):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise _unsupported("IFEval corrective aggregation", request.intent)
        try:
            result = scoring.aggregate_corrective(
                request.context,
                scoring.load_specs(root / "instructions"),
                benchmark_id,
                benchmark_revision,
                max_attempts=MAX_ATTEMPTS,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return _json(result)

    return aggregate


def _select(request: Request) -> str:
    """Deterministically select one member answer, verbatim.

    The payload carries the runtime-sized member record array and the judge's reply.

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

    raw_members = _json_array(request.context, "selection members")
    members = [_member(value, index) for index, value in enumerate(raw_members)]
    answers = [(member["key"], member["answer"]) for member in members]
    if not MIN_MEMBERS <= len(answers) <= MAX_MEMBERS:
        raise _unavailable(
            f"selection input must carry {MIN_MEMBERS}..{MAX_MEMBERS} member answers"
        )
    selected = {letter.upper(): answer for letter, answer in answers}
    passers = [member["key"].lower() for member in members if member["feedback"] == "PASSED"]
    pick = _judge_letter(request.intent, selected)
    if passers:
        judged = pick if pick is not None and pick.lower() in passers else passers[0].upper()
        return selected[judged]
    return selected[pick] if pick is not None else answers[0][1]


def _resolve_candidate(model_routes: frozenset[str]):
    """Validate raw Fusion bindings against this Runner's declared Model routes."""

    def resolve_candidate(request: Request) -> str:
        value = _bound_members(request, model_routes)
        return _json(_resolved_members(value, model_routes))

    return resolve_candidate


def _bound_members(request: Request, model_routes: frozenset[str]) -> dict[str, object]:
    _direct_model_expression(request.intent, "Candidate synthesizer", model_routes)
    try:
        decoded = json.loads(request.context or "")
    except ValueError as exc:
        raise _candidate_invalid(f"Candidate member bindings must be a URL4 struct: {exc}") from exc
    if not isinstance(decoded, dict):
        raise _candidate_invalid("Candidate member bindings must be a URL4 struct")
    return decoded


def _resolved_members(
    value: dict[str, object], model_routes: frozenset[str]
) -> list[dict[str, str]]:
    if not MIN_MEMBERS <= len(value) <= MAX_MEMBERS:
        raise _candidate_invalid(
            f"verifying-ensemble requires {MIN_MEMBERS}..{MAX_MEMBERS} direct Model members"
        )
    expected = tuple(f"member_{index}" for index in range(1, len(value) + 1))
    if tuple(value) != expected:
        raise _candidate_invalid(
            "Candidate member fields must be ordered member_1 through member_4"
        )
    return [
        _resolved_member(value[field], index, model_routes) for index, field in enumerate(expected)
    ]


def _resolved_member(value: object, index: int, model_routes: frozenset[str]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"name", "url4"}:
        raise _candidate_invalid(
            f"Candidate member {index + 1} must contain exactly name and url4 fields"
        )
    name = value["name"]
    if not isinstance(name, str) or not name.strip():
        raise _candidate_invalid(f"Candidate member {index + 1} name must be non-blank text")
    expression = _direct_model_expression(
        value["url4"], f"Candidate member {index + 1}", model_routes
    )
    return {
        "key": MEMBER_LETTERS[index].upper(),
        "name": name.strip(),
        "kind": "model",
        "expression": expression,
    }


def _direct_model_expression(
    value: object,
    label: str,
    model_routes: frozenset[str],
) -> str:
    """Return canonical URL4 only when `value` is one input-consuming model call."""

    if not isinstance(value, str) or not value.strip() or value.lstrip().startswith("$"):
        raise _candidate_invalid(f"{label} must be one direct Model URL4 expression")
    try:
        parsed = build(value)
    except ParseError as exc:
        raise _candidate_invalid(f"{label} URL4 is invalid: {exc}") from exc
    if not isinstance(parsed, Expression):
        raise _candidate_invalid(f"{label} must be one direct Model URL4 expression")
    call = _direct_model_call(parsed, label)
    if call.path not in model_routes:
        raise _candidate_invalid(f"{label} must call a declared Model route; got {call.path!r}")
    if call.context != "$input":
        raise _candidate_invalid(f"{label} must consume the Candidate $input binding")
    try:
        return render(parsed.sources[0] if parsed.intent is None else parsed)
    except RenderError as exc:  # pragma: no cover - build already seals supported shapes
        raise _candidate_invalid(f"{label} URL4 is invalid: {exc}") from exc


def _direct_model_call(parsed: Expression, label: str) -> RelExpr:
    if len(parsed.sources) != 1:
        raise _candidate_invalid(f"{label} must be one direct Model URL4 expression")
    source = parsed.sources[0]
    if isinstance(source, RelExpr) and parsed.intent is None:
        call = source
    elif (
        isinstance(source, Source)
        and isinstance(source.value, RelExpr)
        and source.name is not None
        and isinstance(parsed.intent, Text)
        and parsed.intent.value == f"${source.name}"
    ):
        call = source.value
    else:
        raise _candidate_invalid(f"{label} must be one direct Model URL4 expression")
    return call


def _json_array(value: object, label: str) -> list[object]:
    """Decode arrays carried as JSON text through URL4's scalar struct fields."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise _unavailable(f"{label} must be JSON: {exc}") from exc
    if not isinstance(value, list):
        raise _unavailable(f"{label} must be an array")
    return value


def _member_record(request: Request) -> str:
    """Return one validated attempt record for the next URL4 round."""

    if request.intent != "record":
        raise _unsupported("IFEval member record", request.intent)
    return _json(_member(_json_payload(request.context, "member record"), 0))


def _member_answer(request: Request) -> str:
    """Return one member's previous answer by its stable collection key."""

    members = [
        _member(value, index)
        for index, value in enumerate(_json_array(request.context, "Candidate member round"))
    ]
    for member in members:
        if member["key"] == request.intent:
            return member.get("answer", "")
    raise _unavailable(f"Candidate member round has no key {request.intent!r}")


def _member(value: object, index: int) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _unavailable(f"Candidate member {index + 1} must be an object")
    required = ("key", "name", "kind", "expression")
    selected: dict[str, str] = {}
    for name in required:
        field = value.get(name)
        if not isinstance(field, str) or not field.strip():
            raise _unavailable(f"Candidate member {index + 1} {name} must be non-blank text")
        selected[name] = field.strip()
    for name in ("answer", "feedback"):
        field = value.get(name)
        if field is not None:
            if not isinstance(field, str):
                raise _unavailable(f"Candidate member {index + 1} {name} must be text")
            selected[name] = field
    return selected


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
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"IFEval {label} must be an integer, got {value!r}")
    try:
        selected = int(value)
    except ValueError:
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


def _candidate_invalid(detail: str) -> ResolutionError:
    return ResolutionError(detail, code="benchmark_candidate_invalid", permanent=True)


__all__ = ["install"]
