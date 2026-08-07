"""IFEval verifier defects are execution failures, never Candidate noncompliance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchmark_support import install_benchmarks

from url4 import RelExpr, Text, render
from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.ifeval.definition import CHECK_ROUTE


def _assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Answer the request."}]',
        encoding="utf-8",
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1,
                "prompt": "Answer the request.",
                "instruction_id_list": ["missing:verifier"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_verifier_defect_is_benchmark_unavailable_not_a_failed_grade(tmp_path: Path) -> None:
    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    with pytest.raises(ResolutionError) as caught:
        await node.evaluate(
            render(
                RelExpr(
                    path=CHECK_ROUTE,
                    context="A Candidate answer.",
                    intent=Text("1"),
                )
            )
        )

    assert caught.value.code == "benchmark_unavailable"
    assert caught.value.permanent is True
