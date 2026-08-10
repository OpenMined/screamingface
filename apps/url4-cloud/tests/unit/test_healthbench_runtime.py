"""HealthBench runtime routes — preflight, task building, and the grading chain.

INVARIANT under test: the judge prompt is rendered Engine-side with the reference's
exact assembly, identities are bound by the Engine (never model-supplied), and unusable
assets fail LOUDLY before any paid call (S-DR3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.contract import CANDIDATE_ROUTE, encode_candidate_invocation
from url4_cloud.benchmarks.healthbench.case_evaluation import (
    CASE_EVALUATION_SCHEMA,
    RUBRIC_EVALUATION_SCHEMA,
)
from url4_cloud.benchmarks.healthbench.definition import (
    CASES_ROUTE,
    JUDGE_MODEL,
    SMOKE_AGGREGATE_ROUTE,
    SMOKE_CASE_EVALUATION_ROUTE,
    SMOKE_CASE_ID,
    SMOKE_CASES_ROUTE,
    SMOKE_RUBRIC_EVALUATION_ROUTE,
    SMOKE_TASKS_ROUTE,
    SMOKE_VERDICT_ROUTE,
)
from url4_cloud.benchmarks.healthbench.prepare import envelope
from url4_cloud.benchmarks.healthbench.prompts import GRADER_TEMPLATE
from url4_cloud.benchmarks.healthbench.runtime import install, preflight
from url4_cloud.benchmarks.healthbench.verdict import call as verdict_call

_MESSAGES = [
    {"role": "user", "content": "STOP-DAPt trial"},
]
_ANSWER = "STOPDAPT-2 studied 1-month DAPT after PCI; which variant do you mean?"


def _write_assets(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "cases.json").write_text(
        json.dumps([{"id": SMOKE_CASE_ID, "input": envelope(_MESSAGES)}]),
        encoding="utf-8",
    )
    rubric_dir = root / "rubrics"
    rubric_dir.mkdir(exist_ok=True)
    (rubric_dir / f"{SMOKE_CASE_ID}.json").write_text(
        json.dumps(
            {
                "hf_id": "hf-smoke",
                "items": [
                    {"rubric_id": 1, "criterion": "seeks context for the study", "points": 8}
                ],
            }
        ),
        encoding="utf-8",
    )


async def _call(node: Url4Node, path: str, context: object, intent: str) -> object:
    payload = context if isinstance(context, str) else json.dumps(context)
    expression = expr(
        src(Text(payload), name="payload", weight=0.0),
        src(
            RelExpr(path=path, context="$payload", intent=Text(intent)),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )
    return json.loads((await node.evaluate(render(expression))).text)


def test_preflight_fails_loudly_on_missing_assets(tmp_path: Path) -> None:
    with pytest.raises(ResolutionError, match="failed preflight"):
        preflight(tmp_path, (SMOKE_CASE_ID,))


def test_preflight_names_a_missing_rubric(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    (tmp_path / "rubrics" / f"{SMOKE_CASE_ID}.json").unlink()
    with pytest.raises(ResolutionError, match="rubric asset"):
        preflight(tmp_path, (SMOKE_CASE_ID,))


@pytest.mark.asyncio
async def test_the_worst30_cases_route_preflights_all_157(tmp_path: Path) -> None:
    # Smoke assets alone cannot serve the worst30 exam — the data route must refuse
    # BEFORE any Candidate call instead of iterating over a partial subset.
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    with pytest.raises(ResolutionError, match="failed preflight"):
        await node.fetch(CASES_ROUTE, relative=True)


@pytest.mark.asyncio
async def test_the_smoke_cases_route_serves_the_pinned_case(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    cases = json.loads(await node.fetch(SMOKE_CASES_ROUTE, relative=True))
    assert [case["id"] for case in cases] == [SMOKE_CASE_ID]
    # Privacy: the public row carries the chat envelope and NOTHING of the rubric.
    assert "rubric" not in json.dumps(cases)
    assert "seeks context" not in json.dumps(cases)


@pytest.mark.asyncio
async def test_rubric_tasks_render_the_reference_prompt_bytes(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    rows = await _call(
        node,
        SMOKE_TASKS_ROUTE,
        encode_candidate_invocation(_ANSWER, "stop", None),
        str(SMOKE_CASE_ID),
    )
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]
    assert row["case_id"] == str(SMOKE_CASE_ID)
    assert row["rubric_id"] == "1"
    # The reference `grade_sample` assembly, byte for byte: flattened "role: content"
    # transcript, the answer appended as the final assistant turn, `[points] criterion`.
    transcript = "user: STOP-DAPt trial"
    expected = GRADER_TEMPLATE.replace(
        "<<conversation>>", f"{transcript}\n\nassistant: {_ANSWER}"
    ).replace("<<rubric_item>>", "[8] seeks context for the study")
    assert row["grader_prompt"] == expected
    # The Case record (with the full output) rides the first row only.
    case_record = json.loads(row["case_record"])
    assert case_record["case_id"] == SMOKE_CASE_ID
    assert case_record["output"] == _ANSWER
    assert case_record["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_the_grading_chain_binds_engine_identities(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    tasks = await _call(
        node,
        SMOKE_TASKS_ROUTE,
        encode_candidate_invocation(_ANSWER, None, None),
        str(SMOKE_CASE_ID),
    )
    assert isinstance(tasks, list)
    task = tasks[0]
    verdict = await _call(
        node,
        SMOKE_VERDICT_ROUTE,
        '{"explanation": "asks which study", "criteria_met": true}',
        f"{SMOKE_CASE_ID}:1",
    )
    assert isinstance(verdict, dict)
    assert verdict["valid"] is True
    assert verdict["case_id"] == SMOKE_CASE_ID
    rubric_evaluation = await _call(
        node,
        SMOKE_RUBRIC_EVALUATION_ROUTE,
        {
            "case": task["case_record"],
            "rubric": task["rubric_record"],
            "evidence": json.dumps(verdict),
        },
        str(SMOKE_CASE_ID),
    )
    assert isinstance(rubric_evaluation, dict)
    assert rubric_evaluation["schema"] == RUBRIC_EVALUATION_SCHEMA
    case_evaluation = await _call(
        node,
        SMOKE_CASE_EVALUATION_ROUTE,
        [json.dumps(rubric_evaluation)],
        str(SMOKE_CASE_ID),
    )
    assert isinstance(case_evaluation, dict)
    assert case_evaluation["schema"] == CASE_EVALUATION_SCHEMA
    result = await _call(
        node,
        SMOKE_AGGREGATE_ROUTE,
        json.dumps([case_evaluation]),
        # v2 intent: "aggregate:<selected>" — the count of Cases this run selected
        # (how a limit=N run tells the reducer to score only the first N).
        "aggregate:1",
    )
    assert isinstance(result, dict)
    # The single +8 item was met — the smoke Case scores 1.0 and the mean follows.
    assert result["score"] == 1.0
    assert result["metrics"]["verdict_coverage"] == 1.0


@pytest.mark.asyncio
async def test_a_malformed_judge_reply_retries_with_a_fresh_sample(tmp_path: Path) -> None:
    # INVARIANT (the reference's retry condition, healthbench_eval.py:415-423): a
    # malformed reply is a SUCCESSFUL model call, so the retry must live on the
    # verdict route and re-resolve the NESTED judge call — each re-ask is a fresh
    # sample. Sibling wiring would deterministically re-deliver the same bad reply.
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    calls = {"judge": 0}

    @node.endpoint(f"/{JUDGE_MODEL}")
    def judge(request: Request) -> str:
        calls["judge"] += 1
        if calls["judge"] < 3:
            return "I think the answer is fine"  # prose — no verdict
        return '{"explanation": "ok", "criteria_met": true}'

    judge_call = RelExpr(path=f"/{JUDGE_MODEL}", context="prompt", intent=Text(""))
    expression = expr(
        verdict_call(
            judge_call,
            case_id=str(SMOKE_CASE_ID),
            rubric_id="1",
            route=SMOKE_VERDICT_ROUTE,
            retry=2,
        ),
        intent=Text("$verdict"),
    )
    record = json.loads((await node.evaluate(render(expression))).text)
    assert calls["judge"] == 3  # two fresh re-asks, third sample parsed
    assert record["valid"] is True
    assert record["criteria_met"] is True


@pytest.mark.asyncio
async def test_exhausted_judge_retries_fail_loudly(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    calls = {"judge": 0}

    @node.endpoint(f"/{JUDGE_MODEL}")
    def judge(request: Request) -> str:
        calls["judge"] += 1
        return "never json"

    judge_call = RelExpr(path=f"/{JUDGE_MODEL}", context="prompt", intent=Text(""))
    expression = expr(
        verdict_call(
            judge_call,
            case_id=str(SMOKE_CASE_ID),
            rubric_id="1",
            route=SMOKE_VERDICT_ROUTE,
            retry=2,
        ),
        intent=Text("$verdict"),
    )
    with pytest.raises(ResolutionError, match="invalid judge reply"):
        await node.evaluate(render(expression))
    assert calls["judge"] == 3  # 1 initial + 2 bounded re-asks, then loud failure


@pytest.mark.asyncio
async def test_the_aggregate_route_rejects_other_operations(tmp_path: Path) -> None:
    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    with pytest.raises(ResolutionError, match="unsupported HealthBench operation"):
        await _call(node, SMOKE_AGGREGATE_ROUTE, "[]", "score")


@pytest.mark.asyncio
async def test_the_full_smoke_expression_resolves_end_to_end(tmp_path: Path) -> None:
    # WHY this test exists: every route handler passed its direct-call unit tests
    # while the LIVE run still died between routes — the url4 resolver's rendering
    # of iterate collections is part of the protocol, and only resolving the real
    # built expression exercises it. Guards the expression↔runtime seam.
    from url4_cloud.benchmarks.healthbench.definition import _build_smoke

    _write_assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)

    @node.endpoint(CANDIDATE_ROUTE)
    def candidate(request: Request) -> str:
        return encode_candidate_invocation(_ANSWER, "stop", None)

    @node.endpoint(f"/{JUDGE_MODEL}")
    def judge(request: Request) -> str:
        assert GRADER_TEMPLATE.splitlines()[0] in request.context
        return '{"explanation": "asks which study", "criteria_met": true}'

    expression = expr(
        src(Text("unused-candidate-recipe"), name="candidate", weight=0.0),
        src(_build_smoke(1), name="exam", weight=0.0),
        intent=Text("$exam"),
    )
    result = json.loads((await node.evaluate(render(expression))).text)
    assert result["score"] == 1.0, result["cases"]
    assert result["case_count"] == 1
    assert result["metrics"]["verdict_coverage"] == 1.0
    assert result["cases"][0]["failures"] == []
