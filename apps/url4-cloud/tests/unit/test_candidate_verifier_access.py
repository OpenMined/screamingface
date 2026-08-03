"""Candidate-side verifier access — the case slot and ifeval's action routes.

FEATURE: candidate blobs can check their own drafts mid-flight (the Skurikhin et al.
verifying-ensemble shape) while the exam definition stays frozen.
STORY: as a researcher, my ensemble retries against the real checker, and the exam
I'm scored on is the unmodified single-pass IFEval.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.definition import candidate
from url4_cloud.benchmarks.draco.definition import DRACO
from url4_cloud.benchmarks.ifeval.definition import (
    CHECK_ROUTE,
    FINALIZE_ROUTE,
    IFEVAL,
    SELECT_ROUTE,
)
from url4_cloud.runner.config import ModelSpec
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world


async def _via_ref(node: Url4Node, payload: str, route: str, intent: str) -> str:
    """Deliver a payload to an action route the way production does — as a resolved
    reference, never as raw parse-time context (raw JSON would split on commas)."""

    @node.endpoint("/probe-payload")
    def emit(request: Request) -> str:
        return payload

    chain = expr(
        src(RelExpr(path="/probe-payload", context="x", intent=Text("go")), name="p", weight=0.0),
        src(RelExpr(path=route, context="$p", intent=Text(intent)), name="out", weight=0.0),
        intent=Text("$out"),
    )
    return (await node.evaluate(render(chain))).text


def _ifeval_assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Describe tea without using any commas."}]', encoding="utf-8"
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1000,
                "prompt": "Describe tea without using any commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )


# --- the candidate() builder and the $case slot -----------------------------------


def test_candidate_builder_emits_the_case_slot_when_given() -> None:
    plain = candidate("$item.input")
    with_case = candidate("$item.input", case="$item.id")

    assert plain.context == "$item.input"
    assert with_case.context == "case: $item.id, input: $item.input"


def test_both_methods_pass_the_case_into_every_candidate_slot() -> None:
    # INVARIANT: the candidate contract is uniform — $case binds under EITHER method,
    # so a candidate-side verifier loop never silently loses checker access.
    single = IFEVAL.resource(1, method="single_pass")["url4"]
    corrective = IFEVAL.resource(1, method="corrective")["url4"]
    assert isinstance(single, str) and isinstance(corrective, str)

    assert single.count("case: $item.id") == 1
    assert corrective.count("case: $item.id") == 3


@pytest.mark.asyncio
async def test_a_blob_can_reference_the_bound_case(tmp_path: Path) -> None:
    # INVARIANT: `$case` joins `$input` in the Candidate's lexical scope when the
    # invocation carries the case slot; blobs that ignore it are unaffected.
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(json.dumps(json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Tea is warm and nice"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    _ifeval_assets(tmp_path / "ifeval")
    blob = "(m:0.0:/provider/m(got $input for case number $case)!'answer')!'$m'"
    invocation = RelExpr(
        path="/candidate",
        context="case: 7, input: hello there",
        intent=Text(blob),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model="provider/m", models=(ModelSpec(id="provider/m"),)),
            client=client,
            benchmark_assets=tmp_path,
        )
        try:
            result = await world.node.evaluate(render(invocation))
        finally:
            await world.aclose()

    assert result.text == "Tea is warm and nice"
    assert "got hello there for case number 7" in seen[0]


# --- the feedback intent -----------------------------------------------------------


def _record(strict: list[bool], violations: list[str]) -> str:
    return json.dumps(
        {
            "schema": "screamingface.ifeval-check.v1",
            "case_id": 1,
            "attempt": 1,
            "valid": True,
            "instruction_id_list": ["punctuation:no_comma"],
            "strict": strict,
            "loose": strict,
            "violations": violations,
        }
    )


@pytest.mark.asyncio
async def test_feedback_intent_returns_violations_text_without_instruction_ids(
    tmp_path: Path,
) -> None:
    # INVARIANT: members only ever see the checker's DESCRIPTIONS — never raw records
    # or instruction ids, which the anti-forgery gate assumes candidates cannot know.
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    record = _record([False], ["Refrain from the use of any commas in your response."])
    reply = await _via_ref(node, record, CHECK_ROUTE, "feedback")

    assert "Refrain from the use of any commas" in reply
    assert "punctuation:no_comma" not in reply
    assert "screamingface.ifeval-check.v1" not in reply


@pytest.mark.asyncio
async def test_feedback_intent_says_passed_when_everything_passed(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    reply = await _via_ref(node, _record([True], []), CHECK_ROUTE, "feedback")

    assert reply == "PASSED"


# --- select and finalize -----------------------------------------------------------


@pytest.mark.asyncio
async def test_select_returns_the_picked_answer_verbatim(tmp_path: Path) -> None:
    # INVARIANT: the judge only ever picks a LETTER — the winning text is returned
    # verbatim by this deterministic route, so a judge cannot mutate the answer
    # (IFEval punishes exactly that kind of mutation).
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    hostile = 'Tricky, "quoted"\ntext with b: colon'
    payload = json.dumps({"pick": "I choose B because it is best", "a": "answer a", "b": hostile})
    reply = await _via_ref(node, payload, SELECT_ROUTE, "select")

    assert reply == hostile


@pytest.mark.asyncio
async def test_select_falls_back_to_the_first_answer_on_an_unparseable_pick(
    tmp_path: Path,
) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    payload = json.dumps({"pick": "no letter here 123", "a": "first", "b": "second"})
    reply = await _via_ref(node, payload, SELECT_ROUTE, "select")

    assert reply == "first"


@pytest.mark.asyncio
async def test_finalize_picks_the_earliest_passed_selection(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    payload = json.dumps(
        {
            "s1": "attempt one",
            "f1": "violation: commas",
            "s2": "attempt two",
            "f2": "PASSED",
            "s3": "attempt three",
            "f3": "PASSED",
        }
    )
    reply = await _via_ref(node, payload, FINALIZE_ROUTE, "finalize")

    assert reply == "attempt two"


@pytest.mark.asyncio
async def test_finalize_returns_the_last_selection_when_none_passed(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    payload = json.dumps(
        {
            "s1": "one",
            "f1": "violation",
            "s2": "two",
            "f2": "violation",
            "s3": "three",
            "f3": "violation",
        }
    )
    reply = await _via_ref(node, payload, FINALIZE_ROUTE, "finalize")

    assert reply == "three"


# --- the manifest actions map ------------------------------------------------------


def test_ifeval_resources_advertise_the_action_routes() -> None:
    for method in ("corrective", "single_pass"):
        resource = IFEVAL.resource(1, method=method)
        actions = resource.get("actions")
        assert actions == {
            "check": CHECK_ROUTE,
            "select": SELECT_ROUTE,
            "finalize": FINALIZE_ROUTE,
        }


def test_draco_resource_has_no_actions_field() -> None:
    assert "actions" not in DRACO.resource(1)
