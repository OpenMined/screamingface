"""The corrective loop's generic runtime — three pure data->data endpoints.

FEATURE: OME-796 — benchmark-independent corrective loop (engine half).
STORY: as a client-compiled `sf.CorrectiveLoop` candidate, my rounds fan out as
ordinary model calls and check-surface calls; these endpoints are the only
control flow I cannot express in URL4 myself — a conditional (gate), a verbatim
pick (select), and a chain collapse (answer).

Mental model: an exam room's clockwork. Drafts and their check records flow in
as data; these endpoints decide STOP/RETRY, pick the submitted draft word-for-
word, and hand the final answer back up the gated chain. They know NOTHING
about any benchmark: `passed` and `satisfaction` were computed behind the
benchmark's check-surface adapter, so the same three routes serve IFEval today
and every rubric benchmark tomorrow. In execution order per round k:

1. The client-compiled expression calls `GATE_ROUTE` with `tie:k:max` — a
   0-or-1-item collection naming the drafts a judge must pick among (>=2
   passers, or a final-round exact satisfaction tie). Empty = no judge call.
2. `SELECT_ROUTE` picks round k's representative answer VERBATIM.
3. `GATE_ROUTE` with `continue:k:max` — one payload iff nobody passed and the
   round budget is not spent; the retry subtree iterates over it (empty = the
   subtree never executes — that is the whole cost story).
4. `ANSWER_ROUTE` collapses `{selected, next}` bottom-up: the deepest executed
   round's selection wins, because a continuation only exists when its round
   was bought by a no-pass gate.

Worked example (3 members, max_rounds=3): round 1 has one passer -> tie gate
[], select returns the passer, continue gate [], answer returns it. Total: 3
model calls, 3 checks, zero judge calls, zero retries.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.ensemble.policy import (
    ANSWER_ROUTE,
    CHECK_SURFACE_SCHEMA,
    GATE_ROUTE,
    MAX_MEMBERS,
    MEMBER_LETTERS,
    SELECT_ROUTE,
)
from url4_cloud.benchmarks.evaluation import benchmark_unavailable as _unavailable
from url4_cloud.benchmarks.evaluation import compact_json, json_array, json_object


def install_corrective_runtime(node: Url4Node) -> None:
    """Register the corrective loop's generic endpoints once per URL4 world."""

    routes = frozenset(node.processor_routes())
    endpoints = (
        (GATE_ROUTE, _gate),
        (SELECT_ROUTE, _select),
        (ANSWER_ROUTE, _answer),
    )
    for route, handler in endpoints:
        if route not in routes:
            node.endpoint(route)(handler)


def _gate(request: Request) -> str:
    """The loop's deterministic control flow, as 0-or-1-item collections.

    `continue:<attempt>:<max_rounds>` — one payload iff the attempt had NO
    passing check and the round budget is not spent; empty means the case
    STOPPED (early exit). `tie:<attempt>:<max_rounds>` — one payload naming the
    drafts a judge must pick among: the passers when two or more passed, or
    (final attempt only) the never-pass drafts tied on maximal satisfaction.

    INVARIANT: this endpoint is pure data -> data. The semantics of its
    decisions are CORRECTIVE_FLOW, hashed into the protocol revision; the
    expression can only show THAT a gate sits here, not what it decides.
    """

    kind, attempt, max_rounds = _gate_intent(request.intent)
    members = _round_records(request.context, "gate round")
    passers = [member for member in members if member["passed"]]
    if kind == "continue":
        proceed = not passers and attempt < max_rounds
        payload = [{"attempt": attempt + 1}] if proceed else []
        return compact_json(payload)
    if len(passers) >= 2:
        pool = passers
    elif not passers and attempt == max_rounds:
        best = max(member["satisfaction"] for member in members)
        tied = [member for member in members if member["satisfaction"] == best]
        pool = tied if len(tied) >= 2 else []
    else:
        pool = []
    if not pool:
        return compact_json([])
    return compact_json(
        [
            {
                "attempt": attempt,
                "candidates": [
                    {"key": member["key"], "answer": member["answer"]} for member in pool
                ],
            }
        ]
    )


def _select(request: Request) -> str:
    """Select the round's representative answer, verbatim, per CORRECTIVE_FLOW.

    Rules, in order:
    1. Exactly one passer -> that answer; no judge involved.
    2. Two or more passers -> the tie-break judge's letter chooses among the
       PASSERS; an invalid or missing letter falls back to the first passer.
    3. No passer -> maximal satisfaction; an exact tie defers to the judge's
       letter among the tied, else the first tied answer stands.

    INVARIANT: the returned text is always a member's exact answer — selection
    can choose but never rewrite, so it cannot break a requirement a member
    satisfied.
    """

    payload = json_object(request.context, "corrective selection")
    if set(payload) != {"round", "tie"}:
        raise _unavailable("corrective selection payload must carry exactly round and tie")
    members = _round_records(payload["round"], "selection round")
    letter = _tie_letter(payload["tie"], members)
    passers = [member for member in members if member["passed"]]
    if len(passers) == 1:
        chosen = passers[0]
    elif passers:
        chosen = _by_letter(passers, letter) or passers[0]
    else:
        best = max(member["satisfaction"] for member in members)
        tied = [member for member in members if member["satisfaction"] == best]
        chosen = tied[0] if len(tied) == 1 else (_by_letter(tied, letter) or tied[0])
    answer = chosen["answer"]
    assert isinstance(answer, str)
    return answer


def _answer(request: Request) -> str:
    """Collapse `{selected, next}` into the loop's single verbatim output.

    `next` is the gated continuation's collection: empty (this round's
    selection stands — someone passed, or the budget is spent) or one deeper
    outcome text (a later round ran, and later rounds only run when this one
    had no passer, so the deeper answer wins).
    """

    payload = json_object(request.context, "corrective answer")
    if set(payload) != {"selected", "next"}:
        raise _unavailable("corrective answer payload must carry exactly selected and next")
    selected = payload["selected"]
    if not isinstance(selected, str):
        raise _unavailable("corrective answer selected must be text")
    next_value = payload["next"]
    items = json_array(next_value, "corrective continuation") if next_value != "" else []
    if len(items) > 1:
        raise _unavailable("corrective continuation must carry at most one outcome")
    if not items:
        return selected
    outcome = items[0]
    if not isinstance(outcome, str):
        raise _unavailable("corrective continuation outcome must be text")
    return outcome


def _gate_intent(intent: str) -> tuple[str, int, int]:
    kind, sep, rest = (intent or "").partition(":")
    if not sep or kind not in {"continue", "tie"}:
        raise _unsupported("corrective gate", intent)
    attempt_part, sep, max_part = rest.partition(":")
    if not sep:
        raise _unsupported("corrective gate", intent)
    attempt = _positive_int(attempt_part, "attempt")
    max_rounds = _positive_int(max_part, "max_rounds")
    if attempt > max_rounds:
        raise _unavailable(f"corrective attempt {attempt} exceeds max_rounds {max_rounds}")
    return kind, attempt, max_rounds


def _round_records(value: object, label: str) -> list[dict[str, Any]]:
    """Decode one round: an object mapping consecutive member letters to records."""

    payload = json_object(value, label)
    if not 1 <= len(payload) <= MAX_MEMBERS:
        raise _unavailable(f"{label} must carry 1..{MAX_MEMBERS} member records")
    expected = tuple(MEMBER_LETTERS[: len(payload)])
    if tuple(payload) != expected:
        raise _unavailable(f"{label} member letters must be consecutive from {MEMBER_LETTERS[0]!r}")
    return [
        _surface_record(payload[letter], f"{label} member {letter!r}", key=letter.upper())
        for letter in expected
    ]


def _surface_record(value: object, label: str, *, key: str) -> dict[str, Any]:
    """Validate one check-surface port record (accepted as JSON text or object)."""

    record = _decoded_record(value, label)
    passed = record["passed"]
    if not isinstance(passed, bool):
        raise _unavailable(f"{label} passed must be a boolean")
    satisfaction = record["satisfaction"]
    if (
        isinstance(satisfaction, bool)
        or not isinstance(satisfaction, int | float)
        or not 0.0 <= satisfaction <= 1.0
    ):
        raise _unavailable(f"{label} satisfaction must be a number in [0, 1]")
    feedback = record["feedback"]
    if not isinstance(feedback, str):
        raise _unavailable(f"{label} feedback must be text")
    answer = record["answer"]
    if not isinstance(answer, str):
        raise _unavailable(f"{label} answer must be text")
    return {
        "key": key,
        "passed": passed,
        "satisfaction": float(satisfaction),
        "feedback": feedback,
        "answer": answer,
    }


def _decoded_record(value: object, label: str) -> dict[str, Any]:
    """Decode the record envelope and pin its closed key set.

    The closed key set is deliberate: this record flows inside a client-compiled
    expression, so an adapter smuggling extra fields through it would widen the
    sealed-envelope surface for every benchmark at once.
    """

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise _unavailable(f"{label} must be a JSON check-surface record: {exc}") from None
    if not isinstance(value, dict) or value.get("schema") != CHECK_SURFACE_SCHEMA:
        raise _unavailable(f"{label} must be a {CHECK_SURFACE_SCHEMA} check-surface record")
    if set(value) != {"schema", "passed", "satisfaction", "feedback", "answer"}:
        raise _unavailable(
            f"{label} must carry exactly schema, passed, satisfaction, feedback, and answer"
        )
    return value


def _tie_letter(value: object, members: list[dict[str, Any]]) -> str | None:
    """The judge's letter from the 0-or-1-item tie-pick collection, if any."""

    items = json_array(value, "tie picks") if value not in (None, "") else []
    if not items:
        return None
    selected = {member["key"]: member for member in members}
    return _judge_letter(items[0], selected)


def _by_letter(pool: list[dict[str, Any]], letter: str | None) -> dict[str, Any] | None:
    if letter is None:
        return None
    for member in pool:
        if member["key"] == letter:
            return member
    return None


def _judge_letter(reply: object, selected: Mapping[str, object]) -> str | None:
    """Accept only an unambiguous single-letter judge reply; prose gets no vote.

    A letter names a member answer (``a`` = member 1's answer, ``b`` = member
    2's, and so on). Anything else — prose, an empty reply, a letter outside
    the answer set — returns None so `_select`'s deterministic fallbacks apply.
    """

    raw = str(reply or "").strip().upper()
    if not raw:
        return None
    token = raw.split()[0].strip(".,:;!()[]'\"")
    return token if len(token) == 1 and token in selected else None


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise _unavailable(f"corrective {label} must be an integer, got {value!r}")
    try:
        selected = int(value)
    except ValueError:
        raise _unavailable(f"corrective {label} must be an integer, got {value!r}") from None
    if selected < 1:
        raise _unavailable(f"corrective {label} must be positive, got {selected}")
    return selected


def _unsupported(label: str, intent: str) -> ResolutionError:
    return ResolutionError(
        f"unsupported {label} operation {intent!r}",
        code="benchmark_operation_unsupported",
        permanent=True,
    )


__all__ = ["install_corrective_runtime"]
