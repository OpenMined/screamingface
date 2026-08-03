"""Benchmark-owned runtime installation and wide-payload execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, render
from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import BENCHMARKS, install_benchmarks
from url4_cloud.benchmarks.draco.definition import (
    AGGREGATE_ROUTE,
    CASES_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
)
from url4_cloud.benchmarks.ifeval.definition import (
    CASES_ROUTE as IFEVAL_CASES_ROUTE,
)
from url4_cloud.benchmarks.ifeval.definition import (
    CHECK_ROUTE as IFEVAL_CHECK_ROUTE,
)


def _assets(root: Path) -> None:
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text('[{"id":1,"input":"Question"}]', encoding="utf-8")
    (root / "criteria" / "1.json").write_text(
        '[{"id":"c1","requirement":"Correct","criterion_type":"positive"}]',
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(
        json.dumps({"sections": [{"id": "correctness", "criteria": [{"id": "c1", "weight": 1}]}]}),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_registry_installs_all_versioned_draco_routes(tmp_path: Path) -> None:
    _assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    assert {TASKS_ROUTE, VERDICT_ROUTE, AGGREGATE_ROUTE} <= set(node.processor_routes())
    assert json.loads(await node.fetch(CASES_ROUTE, relative=True))[0]["input"] == "Question"
    # WHY per-registry prefixes: the original draco-only assertion was structurally
    # incompatible with a second installed family (surfaced + relaxed in OME-719).
    prefixes = tuple(f"/benchmarks/{benchmark_id}/" for benchmark_id in BENCHMARKS)
    assert all(route.startswith(prefixes) for route in node.processor_routes())


def _ifeval_assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Write one sentence without commas."},'
        '{"id":2,"input":"Write at least 50 words without commas."}]',
        encoding="utf-8",
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1000,
                "prompt": "Write one sentence without commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )
    (root / "instructions" / "2.json").write_text(
        json.dumps(
            {
                "key": 1001,
                "prompt": "Write at least 50 words without commas.",
                "instruction_id_list": [
                    "punctuation:no_comma",
                    "length_constraints:number_words",
                ],
                "kwargs": [{}, {"relation": "at least", "num_words": 50}],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_ifeval_check_route_grades_a_response(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    record = json.loads(
        (
            await node.evaluate(
                render(
                    RelExpr(
                        path=IFEVAL_CHECK_ROUTE,
                        context="A sentence with no comma at all.",
                        intent=Text("1"),
                    )
                )
            )
        ).text
    )

    assert record["schema"] == "screamingface.ifeval-check.v1"
    assert record["case_id"] == 1
    assert record["valid"] is True
    assert record["strict"] == [True]
    assert record["loose"] == [True]


@pytest.mark.asyncio
async def test_ifeval_check_intent_carries_an_optional_attempt(tmp_path: Path) -> None:
    # AIDEV-NOTE: raw commas in a literal url4 context act as group separators — the
    # real chain passes REFERENCES ($prior_N) resolved after parsing, so this test
    # violates the word-count constraint with comma-free text instead.
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    record = json.loads(
        (
            await node.evaluate(
                render(
                    RelExpr(
                        path=IFEVAL_CHECK_ROUTE,
                        context="A short comma-free answer.",
                        intent=Text("2:2"),
                    )
                )
            )
        ).text
    )

    assert record["case_id"] == 2
    assert record["attempt"] == 2
    assert record["strict"] == [True, False]
    # The retry path needs the checker's own wording of what failed.
    assert record["violations"]
    assert "50" in record["violations"][0]


@pytest.mark.asyncio
async def test_ifeval_check_rejects_a_malformed_attempt(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    with pytest.raises(ResolutionError) as caught:
        await node.evaluate(
            render(
                RelExpr(
                    path=IFEVAL_CHECK_ROUTE,
                    context="anything",
                    intent=Text("1:zero"),
                )
            )
        )

    assert caught.value.code == "benchmark_unavailable"


@pytest.mark.asyncio
async def test_ifeval_check_without_assets_is_unavailable_not_missing_route(
    tmp_path: Path,
) -> None:
    node = Url4Node("test")
    install_benchmarks(node, tmp_path / "missing")

    with pytest.raises(ResolutionError) as caught:
        await node.fetch(IFEVAL_CASES_ROUTE, relative=True)

    assert caught.value.code == "benchmark_unavailable"
    assert caught.value.permanent is True


@pytest.mark.asyncio
async def test_missing_assets_fail_as_unavailable_not_missing_route(tmp_path: Path) -> None:
    node = Url4Node("test")
    install_benchmarks(node, tmp_path / "missing")

    with pytest.raises(ResolutionError) as caught:
        await node.fetch(CASES_ROUTE, relative=True)

    assert caught.value.code == "benchmark_unavailable"
    assert caught.value.permanent is True


@pytest.mark.asyncio
async def test_aggregate_accepts_payload_larger_than_process_argv(tmp_path: Path) -> None:
    """The row collection stays in-process even when it exceeds common ARG_MAX limits."""

    _assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    verdict = {
        "schema": "screamingface.criterion-verdict.v1",
        "criterion_id": "c1",
        "valid": True,
        "explanation": "x" * 2_100_000,
        "criterion_status": "MET",
    }
    expression = render(
        RelExpr(
            path=AGGREGATE_ROUTE,
            context=json.dumps([json.dumps(verdict)]),
            intent=Text("aggregate"),
        )
    )

    result = json.loads((await node.evaluate(expression)).text)

    assert result["score"] == 1.0
    assert result["case_count"] == 1
