"""Corrective IFEval exposes only sanitized retry feedback inside its Engine URL4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.ifeval.definition import CHECK_ROUTE, IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import IFEVAL_ITERATIVE_CORRECTION


def _assets(root: Path) -> None:
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


async def _feedback(node: Url4Node, record: str) -> str:
    @node.endpoint("/record")
    def emit(request: Request) -> str:
        return record

    expression = expr(
        src(RelExpr(path="/record", context="x", intent=Text("get")), name="record", weight=0.0),
        src(
            RelExpr(path=CHECK_ROUTE, context="$record", intent=Text("feedback")),
            name="feedback",
            weight=0.0,
        ),
        intent=Text("$feedback"),
    )
    return (await node.evaluate(render(expression))).text


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


def test_variants_share_family_assets_but_not_protocol_identity() -> None:
    assert IFEVAL_ITERATIVE_CORRECTION.family == IFEVAL.family == "ifeval"
    assert IFEVAL_ITERATIVE_CORRECTION.id != IFEVAL.id
    assert IFEVAL_ITERATIVE_CORRECTION.revision != IFEVAL.revision


@pytest.mark.asyncio
async def test_feedback_excludes_private_instruction_identifiers(tmp_path: Path) -> None:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    reply = await _feedback(
        node,
        _record([False], ["Refrain from the use of any commas in your response."]),
    )

    assert "Refrain from the use of any commas" in reply
    assert "punctuation:no_comma" not in reply
    assert "screamingface.ifeval-check.v1" not in reply


@pytest.mark.asyncio
async def test_feedback_is_passed_when_every_requirement_passes(tmp_path: Path) -> None:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    assert await _feedback(node, _record([True], [])) == "PASSED"
