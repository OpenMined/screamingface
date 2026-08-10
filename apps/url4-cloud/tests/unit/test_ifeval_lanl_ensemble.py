"""The LANL early-exit ensemble Variant — gates decide, the engine skips.

FEATURE: `ifeval/lanl-ensemble`, a reproduction of Skurikhin et al. §2.
STORY: as a researcher, a case whose first attempt passes costs N member calls and
nothing else — the paper's tokenomics are reproducible, not just its accuracy.

The control flow lives in deterministic gate endpoints returning 0-or-1-item
collections; conditional work sits in `iterate` bodies over those collections. The
tests here pin, in order: (1) the engine semantics the design rests on — an empty
gate collection means the body NEVER executes; (2) each gate/select/envelope
handler's decision table (LANL_FLOW); (3) the built expression's structure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, build, expr, iterate, ref, render, src, text
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.contract import decode_candidate_invocation
from url4_cloud.benchmarks.ifeval.corrective_policy import (
    LANL_ENSEMBLE_REVISION,
    LANL_ENVELOPE_ROUTE,
    LANL_FLOW,
    LANL_GATE_ROUTE,
    LANL_SELECT_ROUTE,
    MAX_ATTEMPTS,
)
from url4_cloud.benchmarks.ifeval.iterative_correction import IFEVAL_LANL_ENSEMBLE

_CASE_PROMPT = "Describe tea without commas."


def _assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        json.dumps([{"id": 1, "input": _CASE_PROMPT}]), encoding="utf-8"
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1,
                "prompt": _CASE_PROMPT,
                # Two constraints so strict-satisfaction fractions can differ (1.0,
                # 0.5, 0.0) — the never-pass argmax fallback needs a middle ground.
                "instruction_id_list": ["punctuation:no_comma", "change_case:english_lowercase"],
                "kwargs": [{}, {}],
            }
        ),
        encoding="utf-8",
    )


def _node(tmp_path: Path) -> Url4Node:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    return node


def _member(key: str, answer: str, feedback: str) -> dict[str, str]:
    return {
        "key": key.upper(),
        "name": f"member-{key}",
        "kind": "model",
        "expression": f"/provider/{key}($input)",
        "answer": answer,
        "finish_reason": "stop",
        "feedback": feedback,
    }


# Answers graded against the two-constraint spec above:
_PASS = "tea is warm and calming"  # no comma + lowercase -> passes both (1.0)
_HALF = "Tea is warm and calming"  # no comma, has capitals -> 0.5
_FAIL = "Tea, warm, calming."  # comma + capitals -> 0.0


async def _call(node: Url4Node, path: str, payload: object, intent: str) -> str:
    result = await node.evaluate(
        render(
            expr(
                src(
                    text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
                    name="payload",
                    weight=0.0,
                ),
                RelExpr(path=path, context="$payload", intent=Text(intent)),
                intent=Text(""),
            )
        )
    )
    return result.text


# --- (1) the engine semantics the whole design rests on ---------------------------


def _probe_expression(members: list[dict[str, str]]) -> str:
    """A production-shaped case body: gate + gated iterate as SIBLINGS inside an
    iteration body — the only scope where a collection reference resolves."""

    body = expr(
        src(
            text(json.dumps(members, separators=(",", ":"))),
            name="round",
            weight=0.0,
        ),
        src(
            RelExpr(path=LANL_GATE_ROUTE, context="$round", intent=Text("continue:1:1")),
            name="gate",
            weight=0.0,
        ),
        src(
            iterate(
                ref("gate"),
                body=(
                    src(
                        RelExpr(path="/probe", context="$item", intent=Text("ran")),
                        name="probed",
                        weight=0.0,
                    ),
                ),
                intent=Text("$probed"),
            ),
            name="outcome",
            weight=0.0,
        ),
        intent=Text("$outcome"),
    )
    rows = iterate(
        "/probe-cases",
        body=(src(body, name="checked", weight=0.0),),
        intent=Text("$checked"),
    )
    return render(expr(src(rows, name="rows", weight=0.0), intent=Text("$rows")))


def _probe_node(tmp_path: Path, probes: list[str]) -> Url4Node:
    node = _node(tmp_path)

    @node.data("/probe-cases")
    def cases() -> str:
        return json.dumps([{"id": 1, "input": "one case"}])

    @node.endpoint("/probe")
    def probe(request) -> str:
        probes.append(request.intent)
        return json.dumps({"probed": True})

    return node


@pytest.mark.asyncio
async def test_an_empty_gate_collection_skips_the_iterate_body_entirely(
    tmp_path: Path,
) -> None:
    # INVARIANT: iterate over a gate that returned [] executes its body ZERO times —
    # this is what makes a round-1 pass cost N member calls and nothing else. If this
    # ever breaks, the lanl-ensemble silently degenerates into the unconditional
    # variant and its cost claims become false. Requires the url4 compiler to wire
    # collection-position references (dag/compiler.py::_lower_collection).
    probes: list[str] = []
    node = _probe_node(tmp_path, probes)
    passers = [_member("a", _PASS, "PASSED"), _member("b", _FAIL, "failed: comma")]
    result = await node.evaluate(_probe_expression(passers))
    assert probes == []
    assert json.loads(result.text) == [[]]


@pytest.mark.asyncio
async def test_a_no_pass_round_runs_the_gated_body_exactly_once(tmp_path: Path) -> None:
    probes: list[str] = []
    node = _probe_node(tmp_path, probes)
    failers = [_member("a", _FAIL, "failed: comma"), _member("b", _FAIL, "failed: comma")]
    result = await node.evaluate(_probe_expression(failers))
    assert probes == ["ran"]
    assert json.loads(result.text) == [[{"probed": True}]]


# --- (2) the gate decision table (LANL_FLOW) --------------------------------------


@pytest.mark.asyncio
async def test_continue_gate_stops_on_any_passer(tmp_path: Path) -> None:
    node = _node(tmp_path)
    members = [_member("a", _PASS, "PASSED"), _member("b", _FAIL, "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, "continue:1:1")
    assert json.loads(reply) == []


@pytest.mark.asyncio
async def test_continue_gate_proceeds_when_nobody_passed(tmp_path: Path) -> None:
    node = _node(tmp_path)
    members = [_member("a", _FAIL, "failed"), _member("b", _HALF, "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, "continue:1:1")
    assert json.loads(reply) == [{"case_id": 1, "attempt": 2}]


@pytest.mark.asyncio
async def test_continue_gate_never_exceeds_the_attempt_budget(tmp_path: Path) -> None:
    # Even with no passer, the final attempt has no continuation — bounded retries.
    node = _node(tmp_path)
    members = [_member("a", _FAIL, "failed"), _member("b", _FAIL, "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, f"continue:1:{MAX_ATTEMPTS}")
    assert json.loads(reply) == []


@pytest.mark.asyncio
async def test_tie_gate_is_empty_for_a_single_passer(tmp_path: Path) -> None:
    # A lone passer needs NO judge call — the paper's cheapest and commonest path.
    node = _node(tmp_path)
    members = [_member("a", _PASS, "PASSED"), _member("b", _FAIL, "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, "tie:1:1")
    assert json.loads(reply) == []


@pytest.mark.asyncio
async def test_tie_gate_names_the_passers_when_two_pass(tmp_path: Path) -> None:
    node = _node(tmp_path)
    members = [_member("a", _PASS, "PASSED"), _member("b", _PASS, "PASSED")]
    reply = await _call(node, LANL_GATE_ROUTE, members, "tie:1:1")
    (payload,) = json.loads(reply)
    assert [candidate["key"] for candidate in payload["candidates"]] == ["A", "B"]


@pytest.mark.asyncio
async def test_tie_gate_is_empty_for_a_unique_best_on_the_final_attempt(
    tmp_path: Path,
) -> None:
    # Never-pass fallback: argmax strict satisfaction is unique (0.5 beats 0.0) — no
    # judge call, deterministic selection.
    node = _node(tmp_path)
    members = [_member("a", _HALF, "failed"), _member("b", _FAIL, "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, f"tie:1:{MAX_ATTEMPTS}")
    assert json.loads(reply) == []


@pytest.mark.asyncio
async def test_tie_gate_fires_on_an_exact_never_pass_tie(tmp_path: Path) -> None:
    node = _node(tmp_path)
    members = [_member("a", _FAIL, "failed"), _member("b", _FAIL + " again", "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, f"tie:1:{MAX_ATTEMPTS}")
    (payload,) = json.loads(reply)
    assert [candidate["key"] for candidate in payload["candidates"]] == ["A", "B"]


@pytest.mark.asyncio
async def test_tie_gate_stays_quiet_on_a_non_final_no_pass_round(tmp_path: Path) -> None:
    # Mid-flow no-pass rounds continue instead of stopping, so a tie-break there
    # would be a wasted paid call — the judge speaks only at the stopping attempt.
    node = _node(tmp_path)
    members = [_member("a", _FAIL, "failed"), _member("b", _FAIL + " again", "failed")]
    reply = await _call(node, LANL_GATE_ROUTE, members, "tie:1:1")
    assert json.loads(reply) == []


# --- (2b) selection ----------------------------------------------------------------


async def _selected(tmp_path: Path, members: list[dict[str, str]], tie: list[str]) -> str:
    node = _node(tmp_path)
    reply = await _call(node, LANL_SELECT_ROUTE, {"round": members, "tie": tie}, "1:1")
    output, finish_reason = decode_candidate_invocation(reply)
    assert finish_reason == "stop"
    return output


def _judge_envelope(letter: str) -> str:
    return json.dumps(
        {
            "schema": "screamingface.candidate-invocation.v1",
            "output": letter,
            "finish_reason": "stop",
        }
    )


@pytest.mark.asyncio
async def test_a_lone_passer_is_selected_verbatim_with_no_judge(tmp_path: Path) -> None:
    members = [_member("a", _FAIL, "failed"), _member("b", _PASS, "PASSED")]
    assert await _selected(tmp_path, members, []) == _PASS


@pytest.mark.asyncio
async def test_the_judge_letter_decides_between_passers(tmp_path: Path) -> None:
    members = [_member("a", _PASS, "PASSED"), _member("b", _PASS + " indeed", "PASSED")]
    assert await _selected(tmp_path, members, [_judge_envelope("b")]) == _PASS + " indeed"


@pytest.mark.asyncio
async def test_a_judge_letter_naming_a_failer_falls_back_to_the_first_passer(
    tmp_path: Path,
) -> None:
    # INVARIANT: selection can choose but never rewrite or downgrade — the judge
    # cannot discard compliant output for a failing one.
    members = [
        _member("a", _PASS, "PASSED"),
        _member("b", _PASS + " too", "PASSED"),
        _member("c", _FAIL, "failed"),
    ]
    assert await _selected(tmp_path, members, [_judge_envelope("c")]) == _PASS


@pytest.mark.asyncio
async def test_never_pass_selects_the_maximal_satisfaction_answer(tmp_path: Path) -> None:
    # 0.5 (no comma, wrong case) beats 0.0 (comma + wrong case) — paper's Best-of-N.
    members = [_member("a", _FAIL, "failed"), _member("b", _HALF, "failed")]
    assert await _selected(tmp_path, members, []) == _HALF


@pytest.mark.asyncio
async def test_a_never_pass_exact_tie_defers_to_the_judge_letter(tmp_path: Path) -> None:
    members = [_member("a", _FAIL, "failed"), _member("b", _FAIL + " twice", "failed")]
    assert await _selected(tmp_path, members, [_judge_envelope("b")]) == _FAIL + " twice"


# --- (2c) the envelope -------------------------------------------------------------


def _check_record(attempt: int) -> dict[str, object]:
    return {
        "schema": "screamingface.ifeval-check.v1",
        "case_id": 1,
        "attempt": attempt,
        "valid": True,
        "answer": f"answer {attempt}",
        "finish_reason": "stop",
        "instruction_id_list": ["punctuation:no_comma"],
        "descriptions": ["no commas"],
        "strict": [True],
        "loose": [True],
        "violations": [],
    }


async def _envelope(tmp_path: Path, payload: dict[str, object]) -> dict[str, object]:
    node = _node(tmp_path)
    reply = await _call(node, LANL_ENVELOPE_ROUTE, payload, "1")
    return json.loads(reply)


@pytest.mark.asyncio
async def test_a_stopped_case_packs_exactly_one_attempt(tmp_path: Path) -> None:
    result = await _envelope(tmp_path, {"attempt_1": json.dumps(_check_record(1)), "next": []})
    assert [attempt["attempt"] for attempt in result["attempts"]] == [1]


@pytest.mark.asyncio
async def test_the_gated_chain_flattens_to_consecutive_attempts(tmp_path: Path) -> None:
    # A skipped attempt never APPEARS rather than appearing empty, so executed
    # attempts are always consecutive from 1 and the envelope contract holds.
    chain = {
        "attempt_1": json.dumps(_check_record(1)),
        "next": [
            {
                "check": json.dumps(_check_record(2)),
                "next": [{"check": json.dumps(_check_record(3))}],
            }
        ],
    }
    result = await _envelope(tmp_path, chain)
    assert [attempt["attempt"] for attempt in result["attempts"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_a_two_item_continuation_is_rejected(tmp_path: Path) -> None:
    from url4.core.errors import ResolutionError

    chain = {
        "attempt_1": json.dumps(_check_record(1)),
        "next": [
            {"check": json.dumps(_check_record(2))},
            {"check": json.dumps(_check_record(2))},
        ],
    }
    with pytest.raises(ResolutionError, match="at most one outcome"):
        await _envelope(tmp_path, chain)


# --- (3) the built expression ------------------------------------------------------


def test_the_expression_gates_every_attempt_after_the_first() -> None:
    resource = IFEVAL_LANL_ENSEMBLE.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)
    assert render(build(url4)) == url4
    # 2 continue-gates guard attempts 2..3; 3 tie-gates guard the judge tie-break.
    gate_uses = url4.count(LANL_GATE_ROUTE)
    assert gate_uses == (MAX_ATTEMPTS - 1) + MAX_ATTEMPTS
    assert url4.count("continue:$case_id") == MAX_ATTEMPTS - 1
    assert url4.count("tie:$case_id") == MAX_ATTEMPTS
    # The judge binding: 1 resolve + 3 gated tie-breaks + 2 gated feedbacks. Every
    # judge call sits INSIDE a gated iterate body — none is unconditional.
    assert url4.count("$candidate_synthesizer") == 1 + MAX_ATTEMPTS + (MAX_ATTEMPTS - 1)
    assert "openrouter/" not in url4


def test_the_flow_contract_is_hashed_into_the_revision() -> None:
    # INVARIANT: the gates' decision rules are invisible in the expression text, so
    # the revision hash must carry them — changing LANL_FLOW must change the revision.
    import hashlib

    assert LANL_ENSEMBLE_REVISION != hashlib.sha256(b"").hexdigest()[:16]
    assert IFEVAL_LANL_ENSEMBLE.revision == LANL_ENSEMBLE_REVISION
    assert "stop" in LANL_FLOW and "tie-break" in LANL_FLOW
    assert "reproduction" in IFEVAL_LANL_ENSEMBLE.description
    assert "verbatim" in IFEVAL_LANL_ENSEMBLE.description


# --- (4) persisted judge feedback --------------------------------------------------
# FEATURE: the correction loop's only model-authored step leaves a trace.
# STORY: as a researcher whose correction round failed, I read what the judge actually
# told the members — not just the deterministic verdicts before and after.


@pytest.mark.asyncio
async def test_the_envelope_stamps_judge_feedback_onto_the_judged_attempt(
    tmp_path: Path,
) -> None:
    # INVARIANT: judge feedback precedes the attempt it coached — attempt N's record
    # carries the feedback authored after attempt N-1 failed; attempt 1 has none.
    chain = {
        "attempt_1": json.dumps(_check_record(1)),
        "next": [
            {
                "check": json.dumps(_check_record(2)),
                "judge": "Add the missing exclamation marks!",
                "next": [],
            }
        ],
    }
    result = await _envelope(tmp_path, chain)
    attempts = result["attempts"]
    assert attempts[0].get("judge_feedback") is None
    assert attempts[1]["judge_feedback"] == "Add the missing exclamation marks!"


@pytest.mark.asyncio
async def test_a_non_text_judge_feedback_is_rejected(tmp_path: Path) -> None:
    from url4.core.errors import ResolutionError

    chain = {
        "attempt_1": json.dumps(_check_record(1)),
        "next": [{"check": json.dumps(_check_record(2)), "judge": 5}],
    }
    with pytest.raises(ResolutionError, match="judge"):
        await _envelope(tmp_path, chain)


def test_the_expression_persists_judge_feedback_in_every_gated_outcome() -> None:
    # WHY: judge_feedback_N used to be interpolated into the retry prompt and DROPPED —
    # the outcome struct must now carry it so the envelope can persist it per round.
    resource = IFEVAL_LANL_ENSEMBLE.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)
    assert url4.count("judge: '$judge_feedback_") == MAX_ATTEMPTS - 1
