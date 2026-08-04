"""The member-shaped corrective IFEval protocol: builds, bounds, and verdict-aware select.

FEATURE: the verifying ensemble of Skurikhin et al. (LANL,
https://openreview.net/forum?id=XSIYfTm2h7) as the Fusion shape of `ifeval-iterative-correction`.
STORY: as a researcher, I hand the exam my (members + judge) system and it runs the
paper's protocol — the judge tie-breaks passers and coaches failures, never answers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, build, render, struct
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.ifeval.definition import CHECK_ROUTE
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_ITERATIVE_CORRECTION,
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MIN_MEMBERS,
    PROSE_CONSTANTS,
    SELECT_ROUTE,
)


def _assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Describe tea without commas."}]', encoding="utf-8"
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1000,
                "prompt": "Describe tea without commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )


# --- the shape-adaptive builds ----------------------------------------------------


@pytest.mark.parametrize("members", [2, 3, 4])
def test_member_build_binds_every_member_and_the_synthesizer(members: int) -> None:
    resource = IFEVAL_ITERATIVE_CORRECTION.resource(1, members=members)
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert render(build(url4)) == url4
    # Every member answers on every attempt; the judge (synthesizer binding) picks
    # once per attempt and authors feedback between attempts.
    assert url4.count("$candidate_model_member_") == members * MAX_ATTEMPTS
    assert url4.count("$candidate_synthesizer") == MAX_ATTEMPTS + (MAX_ATTEMPTS - 1)
    assert url4.count(SELECT_ROUTE) == MAX_ATTEMPTS
    # INVARIANT: no engine-pinned judge — the judge belongs to the system under test
    # (the paper's [Ens-1] vs [Ens-2] differ only in the judge).
    assert resource["required_models"] == []
    assert "openrouter/" not in url4


def test_the_paper_winning_two_member_shape_is_expressible() -> None:
    # [Ens-1] is TWO members with the judge doubling as a member — a hardcoded
    # three-member protocol could never reproduce the paper's headline system.
    resource = IFEVAL_ITERATIVE_CORRECTION.resource(1, members=MIN_MEMBERS)
    url4 = resource["url4"]
    assert isinstance(url4, str)
    assert url4.count("$candidate_model_member_") == MIN_MEMBERS * MAX_ATTEMPTS


@pytest.mark.parametrize("members", [1, 5])
def test_member_counts_outside_the_protocol_bounds_are_rejected(members: int) -> None:
    with pytest.raises(ValueError, match="direct members"):
        IFEVAL_ITERATIVE_CORRECTION.resource(1, members=members)


def test_solo_and_member_shapes_share_one_identity() -> None:
    solo = IFEVAL_ITERATIVE_CORRECTION.resource(1)
    ensemble = IFEVAL_ITERATIVE_CORRECTION.resource(1, members=3)
    # One exam: same id and revision — the shape is a candidate property, like it is
    # on canonical ifeval. The url4 differs; the protocol definition does not.
    assert solo["id"] == ensemble["id"] == "ifeval-iterative-correction"
    assert solo["revision"] == ensemble["revision"]
    assert solo["url4"] != ensemble["url4"]


def test_member_rows_grade_from_attempt_tagged_selection_checks() -> None:
    resource = IFEVAL_ITERATIVE_CORRECTION.resource(1, members=2)
    url4 = resource["url4"]
    assert isinstance(url4, str)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert f"$selection_check_{attempt}" in url4
    # Selections are re-checked with the attempt-tagged intent, so the shared
    # corrective aggregation scores both shapes identically (earliest strict pass).
    assert url4.count(CHECK_ROUTE) == (2 * 2 + 1) * MAX_ATTEMPTS


def test_benchmarks_without_a_member_build_ignore_the_member_count() -> None:
    from url4_cloud.benchmarks.draco.definition import DRACO

    assert DRACO.member_build is None
    shaped = DRACO.resource(1, members=3)
    plain = DRACO.resource(1)
    assert shaped["url4"] == plain["url4"]


# --- verdict-aware selection ------------------------------------------------------


async def _select(tmp_path: Path, payload: dict[str, object]) -> str:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    result = await node.evaluate(
        render(RelExpr(path=SELECT_ROUTE, context=render(struct(payload)), intent=Text("select")))
    )
    return result.text


@pytest.mark.asyncio
async def test_a_lone_passer_wins_even_against_the_judges_letter(tmp_path: Path) -> None:
    # INVARIANT (paper judge scope): the judge only tie-breaks among COMPLIANT
    # answers — it can never discard the only passing draft.
    selected = await _select(
        tmp_path,
        {"pick": "A", "a": "alpha", "b": "beta", "fa": "failed", "fb": "PASSED"},
    )
    assert selected == "beta"


@pytest.mark.asyncio
async def test_the_judges_letter_decides_between_passers(tmp_path: Path) -> None:
    selected = await _select(
        tmp_path,
        {
            "pick": "C",
            "a": "alpha",
            "b": "beta",
            "c": "gamma",
            "fa": "PASSED",
            "fb": "PASSED",
            "fc": "PASSED",
        },
    )
    assert selected == "gamma"


@pytest.mark.asyncio
async def test_a_judge_pick_of_a_failing_answer_falls_back_to_a_passer(
    tmp_path: Path,
) -> None:
    selected = await _select(
        tmp_path,
        {
            "pick": "A",
            "a": "alpha",
            "b": "beta",
            "c": "gamma",
            "fa": "failed",
            "fb": "PASSED",
            "fc": "PASSED",
        },
    )
    assert selected == "beta"


@pytest.mark.asyncio
async def test_with_no_passers_the_judges_letter_stands(tmp_path: Path) -> None:
    selected = await _select(
        tmp_path,
        {"pick": "B", "a": "alpha", "b": "beta", "fa": "failed", "fb": "failed"},
    )
    assert selected == "beta"


@pytest.mark.asyncio
async def test_an_unparseable_judge_reply_falls_back_to_the_first_answer(
    tmp_path: Path,
) -> None:
    # "zzz" contains no member letter at all — the true fallback branch.
    selected = await _select(
        tmp_path,
        {"pick": "zzz", "a": "alpha", "b": "beta", "fa": "failed", "fb": "failed"},
    )
    assert selected == "alpha"


@pytest.mark.asyncio
async def test_a_prose_judge_reply_gets_no_vote(tmp_path: Path) -> None:
    # INVARIANT: only an unambiguous letter counts. Scanning prose would turn
    # "Based on the constraints..." into a pick of B via the first word.
    selected = await _select(
        tmp_path,
        {
            "pick": "Based on the constraints I would choose b",
            "a": "alpha",
            "b": "beta",
            "fa": "failed",
            "fb": "failed",
        },
    )
    assert selected == "alpha"


@pytest.mark.asyncio
async def test_a_punctuated_single_letter_reply_still_counts(tmp_path: Path) -> None:
    selected = await _select(
        tmp_path,
        {"pick": "(b)", "a": "alpha", "b": "beta", "fa": "failed", "fb": "failed"},
    )
    assert selected == "beta"


def test_prose_constants_stay_quote_and_comma_free() -> None:
    # INVARIANT: URL4 context prose ships unescaped — a quote corrupts the rendered
    # expression's re-parse and a top-level comma splits the context into slots
    # (edge_probe5, 2026-08-03). The exam's fixed prose must never contain either.
    for prose in PROSE_CONSTANTS:
        assert "'" not in prose
        assert "," not in prose


@pytest.mark.asyncio
async def test_selection_rejects_member_counts_outside_bounds(tmp_path: Path) -> None:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    payload = render(struct({"pick": "A", "a": "alpha"}))
    with pytest.raises(Exception, match=f"{MIN_MEMBERS}..{MAX_MEMBERS} member answers"):
        await node.evaluate(
            render(RelExpr(path=SELECT_ROUTE, context=payload, intent=Text("select")))
        )
