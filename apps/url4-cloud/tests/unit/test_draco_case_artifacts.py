"""Complete DRACO Case evidence survives the public Candidate-result seam.

FEATURE: OME-319 — a completed Evaluation remains auditable after its live stream ends.
STORY: as a researcher, I can read exactly what was asked, what the Candidate answered, what the
Judge returned, and why that reply produced its normalized criterion status.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from benchmark_support import install_benchmarks

from url4 import Node, RelExpr, build, expr, render, src, text
from url4_cloud.benchmarks.draco.definition import DRACO_SMOKE, JUDGE_MODEL
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world
from url4_cloud.world_config import ModelSpec

_QUESTION = "What is two plus two?"
_ANSWER = "Four."
_EXPLANATION = "The response states that two plus two is four."
_RAW_JUDGE_REPLY = json.dumps(
    {"explanation": _EXPLANATION, "criterion_status": "MET"},
    indent=2,
)


def _assets(root: Path) -> None:
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text(
        json.dumps([{"id": 1, "input": _QUESTION, "domain": "Arithmetic"}]),
        encoding="utf-8",
    )
    (root / "criteria" / "1.json").write_text(
        json.dumps(
            [
                {
                    "id": "answer-is-four",
                    "requirement": "States that two plus two equals four.",
                    "criterion_type": "positive",
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "id": "correctness",
                        "criteria": [{"id": "answer-is-four", "weight": 3}],
                    }
                ]
            }
        ),
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
async def test_draco_smoke_retains_complete_case_evidence(tmp_path: Path) -> None:
    _assets(tmp_path / "draco")

    def respond(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        content = _ANSWER if model == "provider/candidate" else _RAW_JUDGE_REPLY
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    candidate = RelExpr(
        path="/provider/candidate",
        context="$input",
        intent=text("Answer exactly."),
    )
    benchmark = DRACO_SMOKE.resource(1)["url4"]
    assert isinstance(benchmark, str)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url="http://aigateway.test",
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
        install_benchmarks(world.node, tmp_path, benchmarks=(DRACO_SMOKE,))
        try:
            result = await world.node.evaluate(_link(candidate, build(benchmark)))
        finally:
            await world.aclose()

    decoded = json.loads(result.text)
    assert decoded["cases"] == [
        {
            "case_id": 1,
            "input": _QUESTION,
            "output": _ANSWER,
            "finish_reason": "stop",
            "grade": {
                "method": "rubric",
                "score": 1.0,
                "metrics": {
                    "normalized_score_sd": 0.0,
                    "pass_rate": 1.0,
                    "pass_rate_sd": 0.0,
                    # This rubric has no Factual Accuracy axis, so accuracy is unknown rather
                    # than zero — a scored-1.0 Case must not report "0% factually accurate".
                    "accuracy": None,
                    "accuracy_pass_rate": None,
                    "axis_scores": {"correctness": 1.0},
                    "axis_pass_rates": {"correctness": 1.0},
                    "coverage": 1.0,
                    "coverage_sd": 0.0,
                    "n_runs": 1,
                    "verdicts_expected": 1,
                    "verdicts_accepted": 1,
                    "verdicts_rejected": 0,
                    "verdicts_invalid": 0,
                    "verdicts_missing": 0,
                },
                "checks": [
                    {
                        "type": "criterion",
                        "id": "answer-is-four",
                        "label": "States that two plus two equals four.",
                        "evidence": [
                            {
                                "sequence": 1,
                                "producer": {"type": "model", "id": JUDGE_MODEL},
                                "valid": True,
                                "outcome": "MET",
                                "explanation": _EXPLANATION,
                                "raw_output": _RAW_JUDGE_REPLY,
                                "metadata": {},
                            }
                        ],
                        "metadata": {
                            "criterion_type": "positive",
                            "weight": 3,
                            "axis": "correctness",
                        },
                    }
                ],
            },
            "failures": [],
            "metadata": {"domain": "Arithmetic"},
        }
    ]
