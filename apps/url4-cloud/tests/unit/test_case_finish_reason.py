"""A Case Result retains how its selected Candidate output ended.

FEATURE: OME-319 — an exported Evaluation remains auditable after live spans disappear.
STORY: as a researcher, I can distinguish a substantively weak answer from one truncated by its
completion limit without replaying the Evaluation event stream.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from benchmark_support import install_benchmarks

from url4 import Node, RelExpr, build, expr, render, src, text
from url4_cloud.benchmarks.draco.definition import DRACO_SMOKE, JUDGE_MODEL
from url4_cloud.runner.config import ModelSpec
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world


def _assets(root: Path) -> None:
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text('[{"id":1,"input":"Explain the result."}]', encoding="utf-8")
    (root / "criteria" / "1.json").write_text(
        json.dumps(
            [
                {
                    "id": "explains-result",
                    "requirement": "Explains the result.",
                    "criterion_type": "positive",
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(
        '{"sections":[{"id":"correctness","criteria":[{"id":"explains-result","weight":1}]}]}',
        encoding="utf-8",
    )


def _link(candidate: Node, benchmark: Node) -> str:
    return render(
        expr(
            src(text(render(candidate)), name="candidate", weight=0.0),
            benchmark,
            intent=text(""),
        )
    )


@pytest.mark.asyncio
async def test_truncated_candidate_output_is_visible_on_the_case_result(tmp_path: Path) -> None:
    """Content remains gradeable; `length` remains visible instead of becoming a poor answer."""

    _assets(tmp_path / "draco")

    def respond(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        if model == "provider/candidate":
            content = "The result follows because"
            finish_reason = "length"
        else:
            content = '{"explanation":"The partial answer explains it.","criterion_status":"MET"}'
            finish_reason = "stop"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    candidate = RelExpr(
        path="/provider/candidate",
        context="$input",
        intent=text("Answer accurately."),
    )
    benchmark = DRACO_SMOKE.resource(1)["url4"]
    assert isinstance(benchmark, str)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model="provider/candidate",
                models=(
                    ModelSpec(id="provider/candidate", native_web_search=True),
                    ModelSpec(id=JUDGE_MODEL),
                ),
            ),
            client=client,
        )
        install_benchmarks(world.node, tmp_path)
        try:
            result = await world.node.evaluate(_link(candidate, build(benchmark)))
        finally:
            await world.aclose()

    case = json.loads(result.text)["cases"][0]
    assert case["output"] == "The result follows because"
    assert case["finish_reason"] == "length"
