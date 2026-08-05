"""The dynamic-member IFEval Variant: one URL4, bounded members, verdict-aware select.

FEATURE: the verifying ensemble of Skurikhin et al. (LANL,
https://openreview.net/forum?id=XSIYfTm2h7) as the `ifeval/verifying-ensemble` Variant.
STORY: as a researcher, I hand the exam my (members + judge) system and it runs the
paper's protocol — the judge tie-breaks passers and coaches failures, never answers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, build, expr, render, src, text
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.ifeval.definition import CHECK_ROUTE
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_VERIFYING_ENSEMBLE,
    MAX_ATTEMPTS,
    MAX_MEMBERS,
    MIN_MEMBERS,
    PROSE_CONSTANTS,
    RESOLVE_CANDIDATE_ROUTE,
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


# --- the member-count-independent build ------------------------------------------


def test_one_url4_binds_a_runtime_member_collection_and_the_synthesizer() -> None:
    resource = IFEVAL_VERIFYING_ENSEMBLE.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert render(build(url4)) == url4
    assert "$candidate_members" in url4
    assert "$candidate_model_member_" not in url4
    assert RESOLVE_CANDIDATE_ROUTE in url4
    # The synthesizer binding is validated once before spend; the Judge then picks once per
    # attempt and authors feedback between attempts, preserving the unrolled behavior.
    assert url4.count("$candidate_synthesizer") == 1 + MAX_ATTEMPTS + (MAX_ATTEMPTS - 1)
    assert url4.count(SELECT_ROUTE) == MAX_ATTEMPTS
    # INVARIANT: no Engine-pinned Judge — the Judge belongs to the system under test
    # (the paper's [Ens-1] vs [Ens-2] differ only in the Judge).
    assert "openrouter/" not in url4


def test_member_rows_grade_from_attempt_tagged_selection_checks() -> None:
    resource = IFEVAL_VERIFYING_ENSEMBLE.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert f"$selection_check_{attempt}" in url4
    # Selections are re-checked with the attempt-tagged intent, so the shared
    # corrective aggregation scores both shapes identically (earliest strict pass).
    assert url4.count(CHECK_ROUTE) == 3 * MAX_ATTEMPTS


# --- verdict-aware selection ------------------------------------------------------


async def _select(tmp_path: Path, payload: dict[str, object]) -> str:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    result = await node.evaluate(
        render(
            expr(
                src(
                    text(json.dumps(payload["members"], ensure_ascii=False, separators=(",", ":"))),
                    name="members",
                    weight=0.0,
                ),
                RelExpr(
                    path=SELECT_ROUTE,
                    context="$members",
                    intent=Text(str(payload["pick"])),
                ),
                intent=Text(""),
            )
        )
    )
    return result.text


def _members(*values: tuple[str, str]) -> list[dict[str, str]]:
    return [
        {
            "key": chr(65 + index),
            "name": f"member-{index + 1}",
            "kind": "model",
            "expression": f"/provider/member-{index + 1}",
            "answer": answer,
            "feedback": feedback,
        }
        for index, (answer, feedback) in enumerate(values)
    ]


@pytest.mark.asyncio
async def test_a_lone_passer_wins_even_against_the_judges_letter(tmp_path: Path) -> None:
    # INVARIANT (paper judge scope): the judge only tie-breaks among COMPLIANT
    # answers — it can never discard the only passing draft.
    selected = await _select(
        tmp_path,
        {"pick": "A", "members": _members(("alpha", "failed"), ("beta", "PASSED"))},
    )
    assert selected == "beta"


@pytest.mark.asyncio
async def test_the_judges_letter_decides_between_passers(tmp_path: Path) -> None:
    selected = await _select(
        tmp_path,
        {
            "pick": "C",
            "members": _members(
                ("alpha", "PASSED"),
                ("beta", "PASSED"),
                ("gamma", "PASSED"),
            ),
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
            "members": _members(
                ("alpha", "failed"),
                ("beta", "PASSED"),
                ("gamma", "PASSED"),
            ),
        },
    )
    assert selected == "beta"


@pytest.mark.asyncio
async def test_with_no_passers_the_judges_letter_stands(tmp_path: Path) -> None:
    selected = await _select(
        tmp_path,
        {"pick": "B", "members": _members(("alpha", "failed"), ("beta", "failed"))},
    )
    assert selected == "beta"


@pytest.mark.asyncio
async def test_an_unparseable_judge_reply_falls_back_to_the_first_answer(
    tmp_path: Path,
) -> None:
    # "zzz" contains no member letter at all — the true fallback branch.
    selected = await _select(
        tmp_path,
        {"pick": "zzz", "members": _members(("alpha", "failed"), ("beta", "failed"))},
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
            "members": _members(("alpha", "failed"), ("beta", "failed")),
        },
    )
    assert selected == "alpha"


@pytest.mark.asyncio
async def test_a_punctuated_single_letter_reply_still_counts(tmp_path: Path) -> None:
    selected = await _select(
        tmp_path,
        {"pick": "(b)", "members": _members(("alpha", "failed"), ("beta", "failed"))},
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
    payload = json.dumps(_members(("alpha", "failed")), ensure_ascii=False, separators=(",", ":"))
    with pytest.raises(Exception, match=f"{MIN_MEMBERS}..{MAX_MEMBERS} member answers"):
        await node.evaluate(
            render(
                expr(
                    src(text(payload), name="members", weight=0.0),
                    RelExpr(path=SELECT_ROUTE, context="$members", intent=Text("A")),
                    intent=Text(""),
                )
            )
        )
