"""The Engine-owned member-level corrective IFEval protocol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, build, render, struct
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.ifeval.definition import CHECK_ROUTE, IFEVAL
from url4_cloud.benchmarks.ifeval.ensemble import (
    FINALIZE_ROUTE,
    IFEVAL_CORRECTIVE_ENSEMBLE,
    JUDGE_MODEL,
    MAX_ATTEMPTS,
    MEMBER_COUNT,
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


def test_ensemble_is_a_distinct_fixed_protocol_in_the_ifeval_family() -> None:
    benchmark = IFEVAL_CORRECTIVE_ENSEMBLE

    assert benchmark.id == "ifeval-corrective-ensemble"
    assert benchmark.family == IFEVAL.family == "ifeval"
    assert benchmark.variant == "corrective-ensemble"
    assert benchmark.revision != IFEVAL.revision
    assert benchmark.required_models == (JUDGE_MODEL,)
    assert MEMBER_COUNT == 3
    assert MAX_ATTEMPTS == 3


def test_resource_contains_one_complete_member_level_url4() -> None:
    resource = IFEVAL_CORRECTIVE_ENSEMBLE.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert render(build(url4)) == url4
    assert url4.count("/candidate") == MEMBER_COUNT * MAX_ATTEMPTS
    assert url4.count("$candidate_model_member_") == MEMBER_COUNT * MAX_ATTEMPTS
    assert url4.count("/" + JUDGE_MODEL) == MAX_ATTEMPTS
    assert url4.count(SELECT_ROUTE) == MAX_ATTEMPTS
    assert url4.count(FINALIZE_ROUTE) == 1
    assert url4.count(CHECK_ROUTE) == (MEMBER_COUNT + 1) * MAX_ATTEMPTS * 2 + 1
    assert "methods" not in resource
    assert "actions" not in resource


@pytest.mark.asyncio
async def test_selection_returns_the_judges_member_answer_verbatim(tmp_path: Path) -> None:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    payload = render(struct({"pick": "B", "a": "alpha", "b": "beta", "c": "gamma"}))

    result = await node.evaluate(
        render(RelExpr(path=SELECT_ROUTE, context=payload, intent=Text("select")))
    )

    assert result.text == "beta"


@pytest.mark.asyncio
async def test_finalization_returns_the_earliest_passing_selection(tmp_path: Path) -> None:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    payload = render(
        struct(
            {
                "s1": "first",
                "f1": "failed",
                "s2": "second",
                "f2": "PASSED",
                "s3": "third",
                "f3": "PASSED",
            }
        )
    )

    result = await node.evaluate(
        render(RelExpr(path=FINALIZE_ROUTE, context=payload, intent=Text("finalize")))
    )

    assert result.text == "second"
