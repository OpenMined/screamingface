"""Install IFEval's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from url4 import Expression, RelExpr, Source, Text, build, render
from url4.core.errors import ParseError, RenderError, ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.contract import (
    decode_candidate_invocation,
    encode_candidate_invocation,
)
from url4_cloud.benchmarks.evaluation import (
    aggregate_endpoint,
    candidate_answer,
    compact_json,
    json_array,
    json_object,
)
from url4_cloud.benchmarks.evaluation import benchmark_unavailable as _unavailable
from url4_cloud.benchmarks.ifeval import aggregate as scoring
from url4_cloud.benchmarks.ifeval import grading
from url4_cloud.benchmarks.ifeval.case_evaluation import bind_case_evaluation
from url4_cloud.benchmarks.ifeval.corrective_policy import (
    LANL_AGGREGATE_ROUTE,
    LANL_ENSEMBLE_ID,
    LANL_ENSEMBLE_REVISION,
    LANL_ENVELOPE_ROUTE,
    LANL_GATE_ROUTE,
    LANL_SELECT_ROUTE,
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MEMBER_ANSWER_ROUTE,
    MEMBER_LETTERS,
    MEMBER_RECORD_ROUTE,
    MIN_MEMBERS,
    RESOLVE_CANDIDATE_ROUTE,
    SELF_AGGREGATE_ROUTE,
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
)
from url4_cloud.benchmarks.ifeval.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASE_COUNT,
    CASE_EVALUATION_ROUTE,
    CASES_ROUTE,
    CHECK_ROUTE,
)


def install(node: Url4Node, root: Path) -> None:
    """Register the shared runtime for all installed IFEval Variants."""

    if CASES_ROUTE not in getattr(node, "_data", {}):
        node.data(CASES_ROUTE, _cases(root), media_type="application/json")
    routes = frozenset(node.processor_routes())
    endpoints = (
        (CHECK_ROUTE, _check(root)),
        (CASE_EVALUATION_ROUTE, _case_evaluation),
        (
            AGGREGATE_ROUTE,
            aggregate_endpoint(
                label="IFEval aggregation",
                available_case_count=CASE_COUNT,
                aggregate=_aggregate(root),
            ),
        ),
        (
            SELF_AGGREGATE_ROUTE,
            aggregate_endpoint(
                label="IFEval corrective aggregation",
                available_case_count=CASE_COUNT,
                aggregate=_aggregate_corrective(root, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION),
            ),
        ),
        (RESOLVE_CANDIDATE_ROUTE, _resolve_candidate),
        (MEMBER_RECORD_ROUTE, _member_record),
        (MEMBER_ANSWER_ROUTE, _member_answer),
        (
            LANL_AGGREGATE_ROUTE,
            aggregate_endpoint(
                label="IFEval corrective aggregation",
                available_case_count=CASE_COUNT,
                aggregate=_aggregate_corrective(root, LANL_ENSEMBLE_ID, LANL_ENSEMBLE_REVISION),
            ),
        ),
        (LANL_GATE_ROUTE, _lanl_gate(root)),
        (LANL_SELECT_ROUTE, _lanl_select(root)),
        (LANL_ENVELOPE_ROUTE, _lanl_envelope),
    )
    for route, handler in endpoints:
        if route not in routes:
            node.endpoint(route)(handler)


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
            candidate = candidate_answer(request.context)
            spec, result, violations = _verification(root, case_id, candidate.text)
        except (KeyError, TypeError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        record = {
            "schema": scoring.SCHEMA,
            "case_id": case_id,
            "attempt": attempt,
            "valid": True,
            "answer": candidate.text,
            "refusal": candidate.refusal,
            "finish_reason": candidate.finish_reason,
            "instruction_id_list": spec["instruction_id_list"],
            "descriptions": grading.describe_instructions(
                instruction_id_list=spec["instruction_id_list"],
                kwargs_list=spec["kwargs"],
                prompt=spec["prompt"],
            ),
            "strict": result["strict"],
            "loose": result["loose"],
            # Violations remain ordinary fields inside the exact Case Evaluation.
            "violations": violations,
        }
        return compact_json(record)

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


def _case_evaluation(request: Request) -> str:
    """Pack exact attempt records into one authoritative per-Case envelope."""

    try:
        case_id = _positive_int(request.intent, "case id")
        payload = json_object(request.context, "Case evaluation")
        expected = tuple(f"attempt_{index}" for index in range(1, len(payload) + 1))
        if not expected or tuple(payload) != expected:
            raise ValueError(
                "IFEval Case evaluation fields must be consecutive attempt_1..attempt_N"
            )
        attempts: list[dict[str, Any]] = []
        for field in expected:
            raw = payload[field]
            if not isinstance(raw, str):
                raise ValueError(f"IFEval Case evaluation {field} must be JSON text")
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError(f"IFEval Case evaluation {field} must decode to an object")
            attempts.append(decoded)
        result = bind_case_evaluation(case_id, attempts)
    except (TypeError, ValueError) as exc:
        raise _unavailable(str(exc)) from exc
    return compact_json(result)


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
    def aggregate(case_evaluations: str, selected_case_count: int) -> dict[str, Any]:
        case_order = scoring.load_case_order(root)
        return scoring.aggregate(
            case_evaluations,
            scoring.load_specs(root / "instructions"),
            BENCHMARK_ID,
            case_order,
            selected_case_count=selected_case_count,
        )

    return aggregate


def _aggregate_corrective(root: Path, benchmark_id: str, benchmark_revision: str):
    def aggregate(case_evaluations: str, selected_case_count: int) -> dict[str, Any]:
        case_order = scoring.load_case_order(root)
        return scoring.aggregate_corrective(
            case_evaluations,
            scoring.load_specs(root / "instructions"),
            benchmark_id,
            benchmark_revision,
            case_order,
            selected_case_count=selected_case_count,
            max_attempts=MAX_ATTEMPTS,
        )

    return aggregate


def _lanl_intent(intent: str) -> tuple[str, int, int]:
    kind, sep, rest = (intent or "").partition(":")
    if not sep or kind not in {"continue", "tie"}:
        raise _unsupported("lanl-ensemble gate", intent)
    case_id, attempt = _case_and_attempt(rest)
    return kind, case_id, attempt


def _lanl_members(value: object, label: str) -> list[dict[str, Any]]:
    raw = json_array(value, label)
    members = [_attempt_member(_member(item, index), index) for index, item in enumerate(raw)]
    if not MIN_MEMBERS <= len(members) <= MAX_MEMBERS:
        raise _unavailable(f"{label} must carry {MIN_MEMBERS}..{MAX_MEMBERS} member answers")
    return members


def _strict_satisfaction(root: Path, case_id: int, answer: str) -> float:
    """The fraction of a case's strict checks the answer satisfies — the paper's
    Best-of-N fallback metric for a case that never fully passes."""

    spec = json.loads(
        _read(root / "instructions" / f"{case_id}.json", f"IFEval case {case_id} spec")
    )
    grading.configure_nltk(root / "nltk_data")
    result = grading.check_case(
        instruction_id_list=spec["instruction_id_list"],
        kwargs_list=spec["kwargs"],
        prompt=spec["prompt"],
        response=answer,
    )
    strict = result["strict"]
    return sum(1 for value in strict if value) / len(strict)


def _lanl_gate(root: Path):
    """The lanl-ensemble's deterministic control flow, as 0-or-1-item collections.

    `continue:<case>:<attempt>` — one payload iff the attempt had NO strict passer
    and the attempt budget is not spent; empty means the case STOPPED (early exit).
    `tie:<case>:<attempt>` — one payload naming the candidates a judge must pick
    among: the passers when two or more passed, or (final attempt only) the
    never-pass candidates tied on maximal strict satisfaction. Empty means no judge
    call happens — a single passer, or a unique best, needs no tie-break.

    INVARIANT: this endpoint is pure data → data. The semantics of its decisions are
    LANL_FLOW, hashed into the Variant revision; the expression can only show THAT a
    gate sits here, not what it decides.
    """

    def gate(request: Request) -> str:
        kind, case_id, attempt = _lanl_intent(request.intent)
        members = _lanl_members(request.context, "gate round")
        passers = [member for member in members if member["feedback"] == "PASSED"]
        if kind == "continue":
            proceed = not passers and attempt < MAX_ATTEMPTS
            payload = [{"case_id": case_id, "attempt": attempt + 1}] if proceed else []
            return compact_json(payload)
        if len(passers) >= 2:
            pool = passers
        elif not passers and attempt == MAX_ATTEMPTS:
            scored = [
                (member, _strict_satisfaction(root, case_id, member["answer"]))
                for member in members
            ]
            best = max(score for _, score in scored)
            tied = [member for member, score in scored if score == best]
            pool = tied if len(tied) >= 2 else []
        else:
            pool = []
        if not pool:
            return compact_json([])
        return compact_json(
            [
                {
                    "case_id": case_id,
                    "attempt": attempt,
                    "candidates": [
                        {"key": member["key"], "answer": member["answer"]} for member in pool
                    ],
                }
            ]
        )

    return gate


def _lanl_select(root: Path):
    """Select the attempt's representative answer, verbatim, per LANL_FLOW.

    Rules, in order:
    1. Exactly one passer -> that answer; no judge involved.
    2. Two or more passers -> the tie-break judge's letter chooses among the PASSERS;
       an invalid or missing letter falls back to the first passer.
    3. No passer -> maximal strict-satisfaction fraction; an exact tie defers to the
       judge's letter among the tied, else the first tied answer stands.

    INVARIANT: the returned text is always a member's exact answer — selection can
    choose but never rewrite, so it cannot break a requirement a member satisfied.
    The chosen member's refusal marking travels with it: a refused member's answer IS
    its refusal text, so selection re-encodes it as a refusal, never as an output —
    otherwise an all-refuse Case would publish refusal prose as a scored answer.
    """

    def select(request: Request) -> str:
        case_id, _attempt = _case_and_attempt(request.intent)
        payload = json_object(request.context, "lanl selection")
        if set(payload) != {"round", "tie"}:
            raise _unavailable("lanl selection payload must carry exactly round and tie")
        members = _lanl_members(payload["round"], "selection round")
        letter = _tie_letter(payload["tie"], members)
        passers = [member for member in members if member["feedback"] == "PASSED"]
        if len(passers) == 1:
            chosen = passers[0]
        elif passers:
            chosen = _by_letter(passers, letter) or passers[0]
        else:
            scored = [
                (member, _strict_satisfaction(root, case_id, member["answer"]))
                for member in members
            ]
            best = max(score for _, score in scored)
            tied = [member for member, score in scored if score == best]
            chosen = tied[0] if len(tied) == 1 else (_by_letter(tied, letter) or tied[0])
        refusal = chosen["refusal"]
        return encode_candidate_invocation(
            "" if refusal is not None else chosen["answer"],
            chosen["finish_reason"],
            refusal,
        )

    return select


def _tie_letter(value: object, members: list[dict[str, Any]]) -> str | None:
    """The judge's letter from the 0-or-1-item tie-pick collection, if any."""

    items = json_array(value, "tie picks") if value not in (None, "") else []
    if not items:
        return None
    reply = items[0]
    if isinstance(reply, str):
        try:
            reply, _finish, _refusal = decode_candidate_invocation(reply)
        except ValueError:
            pass  # a bare text reply is still a judge reply
    selected = {member["key"].upper(): member for member in members}
    return _judge_letter(reply, selected)


def _by_letter(pool: list[dict[str, Any]], letter: str | None) -> dict[str, Any] | None:
    if letter is None:
        return None
    for member in pool:
        if member["key"].upper() == letter:
            return member
    return None


def _lanl_envelope(request: Request) -> str:
    """Pack the gated attempt chain into one authoritative per-Case envelope.

    The expression hands over `{attempt_1: <check record>, next: <continuation>}`
    where the continuation is an EMPTY array (the case stopped after attempt 1) or a
    single `{check, next}` outcome — recursively. Skipping is structural: a skipped
    attempt simply never appears, so executed attempts are always consecutive from 1
    and `bind_case_evaluation`'s ordering contract holds unchanged.
    """

    try:
        case_id = _positive_int(request.intent, "case id")
        payload = json_object(request.context, "lanl case evaluation")
        if set(payload) != {"attempt_1", "next"}:
            raise ValueError("lanl case evaluation must carry exactly attempt_1 and next")
        attempts = [_decoded_check(payload["attempt_1"], "attempt_1")]
        next_value: object = payload["next"]
        while True:
            items = json_array(next_value, "lanl continuation") if next_value != "" else []
            if not items:
                break
            if len(items) != 1:
                raise ValueError("lanl continuation must carry at most one outcome")
            record, next_value = _continuation_outcome(items[0])
            attempts.append(record)
        result = bind_case_evaluation(case_id, attempts)
    except (TypeError, ValueError) as exc:
        raise _unavailable(str(exc)) from exc
    return compact_json(result)


def _continuation_outcome(outcome: object) -> tuple[dict[str, Any], object]:
    """Decode one gated outcome into (stamped check record, next continuation)."""

    if isinstance(outcome, str):
        outcome = json.loads(outcome)
    if not isinstance(outcome, dict) or not {"check"} <= set(outcome) <= {
        "check",
        "judge",
        "next",
    }:
        raise ValueError("lanl continuation outcome must carry check (and judge/next)")
    record = _decoded_check(outcome["check"], "continuation check")
    if "judge" in outcome:
        judge = outcome["judge"]
        if not isinstance(judge, str):
            raise ValueError("lanl continuation judge feedback must be text")
        # WHY stamped here: the judge's words are shared by the whole round, and this
        # envelope is the only place that sees both the feedback and the attempt it
        # coached — persisting it closes the correction loop's one blind spot.
        record["judge_feedback"] = judge
    return record, outcome.get("next", [])


def _decoded_check(value: object, label: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ValueError(f"lanl {label} must be a JSON check record: {exc}") from None
    if not isinstance(value, dict):
        raise ValueError(f"lanl {label} must decode to an object")
    return value


def _resolve_candidate(request: Request) -> str:
    """Validate raw Fusion bindings before any LANL member invocation."""

    value = _bound_members(request)
    return compact_json(_resolved_members(value))


def _bound_members(request: Request) -> dict[str, object]:
    _direct_model_expression(request.intent, "Candidate synthesizer")
    try:
        decoded = json.loads(request.context or "")
    except ValueError as exc:
        raise _candidate_invalid(f"Candidate member bindings must be a URL4 struct: {exc}") from exc
    if not isinstance(decoded, dict):
        raise _candidate_invalid("Candidate member bindings must be a URL4 struct")
    return decoded


def _resolved_members(value: dict[str, object]) -> list[dict[str, str]]:
    if not MIN_MEMBERS <= len(value) <= MAX_MEMBERS:
        raise _candidate_invalid(
            f"lanl-ensemble requires {MIN_MEMBERS}..{MAX_MEMBERS} direct Model members"
        )
    expected = tuple(f"member_{index}" for index in range(1, len(value) + 1))
    if tuple(value) != expected:
        raise _candidate_invalid(
            "Candidate member fields must be ordered member_1 through member_4"
        )
    return [_resolved_member(value[field], index) for index, field in enumerate(expected)]


def _resolved_member(value: object, index: int) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"name", "url4"}:
        raise _candidate_invalid(
            f"Candidate member {index + 1} must contain exactly name and url4 fields"
        )
    name = value["name"]
    if not isinstance(name, str) or not name.strip():
        raise _candidate_invalid(f"Candidate member {index + 1} name must be non-blank text")
    expression = _direct_model_expression(value["url4"], f"Candidate member {index + 1}")
    return {
        "key": MEMBER_LETTERS[index].upper(),
        "name": name.strip(),
        "kind": "model",
        "expression": expression,
    }


def _direct_model_expression(
    value: object,
    label: str,
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


def _member_record(request: Request) -> str:
    """Return one validated attempt record for the next URL4 round."""

    if request.intent != "record":
        raise _unsupported("IFEval member record", request.intent)
    return compact_json(_attempt_member(json_object(request.context, "member record"), 0))


def _member_answer(request: Request) -> str:
    """Return one member's previous answer by its stable collection key."""

    members = [
        _member(value, index)
        for index, value in enumerate(json_array(request.context, "Candidate member round"))
    ]
    for member in members:
        if member["key"] == request.intent:
            return _attempt_member(member, 0)["answer"]
    raise _unavailable(f"Candidate member round has no key {request.intent!r}")


def _member(value: object, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _unavailable(f"Candidate member {index + 1} must be an object")
    selected: dict[str, Any] = _required_member_fields(value, index)
    selected.update(_optional_member_text(value, index))
    if "finish_reason" in value:
        selected["finish_reason"] = _finish_reason(value["finish_reason"], index)
    if "refusal" in value:
        selected["refusal"] = _member_refusal(value["refusal"], index)
    return selected


def _required_member_fields(value: dict[Any, Any], index: int) -> dict[str, str]:
    selected: dict[str, str] = {}
    for name in ("key", "name", "kind", "expression"):
        field = value.get(name)
        if not isinstance(field, str) or not field.strip():
            raise _unavailable(f"Candidate member {index + 1} {name} must be non-blank text")
        selected[name] = field.strip()
    return selected


def _optional_member_text(value: dict[Any, Any], index: int) -> dict[str, str]:
    selected: dict[str, str] = {}
    for name in ("answer", "feedback"):
        field = value.get(name)
        if field is not None:
            if not isinstance(field, str):
                raise _unavailable(f"Candidate member {index + 1} {name} must be text")
            selected[name] = field
    return selected


def _finish_reason(value: object, index: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _unavailable(
            f"Candidate member {index + 1} finish_reason must be non-blank text or null"
        )
    return value


def _member_refusal(value: object, index: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _unavailable(f"Candidate member {index + 1} refusal must be non-blank text or null")
    return value


def _attempt_member(value: object, index: int) -> dict[str, Any]:
    """Require the complete output contract for one checked member attempt."""

    member = _member(value, index)
    for name in ("answer", "feedback", "finish_reason", "refusal"):
        if name not in member:
            raise _unavailable(f"Candidate member {index + 1} has no {name}")
    refusal = member["refusal"]
    if refusal is not None and member["answer"] != refusal:
        raise _unavailable(f"Candidate member {index + 1} refusal must equal its checked answer")
    return member


def _judge_letter(reply: object, selected: Mapping[str, object]) -> str | None:
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


def _case_and_attempt(value: str) -> tuple[int, int]:
    case_part, _, attempt_part = (value or "").partition(":")
    case_id = _positive_int(case_part, "case id")
    attempt = _positive_int(attempt_part, "attempt") if attempt_part else 1
    return case_id, attempt


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"IFEval {label} must be an integer, got {value!r}")
    try:
        selected = int(value)
    except ValueError:
        raise ValueError(f"IFEval {label} must be an integer, got {value!r}") from None
    if selected < 1:
        raise ValueError(f"IFEval {label} must be positive, got {selected}")
    return selected


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


def _candidate_invalid(detail: str) -> ResolutionError:
    return ResolutionError(detail, code="benchmark_candidate_invalid", permanent=True)


__all__ = ["install"]
