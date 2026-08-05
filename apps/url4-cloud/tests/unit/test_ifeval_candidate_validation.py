"""Candidate-shape resolution in the public verifying-ensemble URL4 artifact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, build, expr, render, src, struct, text
from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_VERIFYING_ENSEMBLE,
    RESOLVE_CANDIDATE_ROUTE,
)


def test_verifying_ensemble_prepares_one_semantic_member_collection() -> None:
    """The protocol prepares members once without leaking that mechanism into their name."""

    url4 = IFEVAL_VERIFYING_ENSEMBLE.resource(3)["url4"]

    assert isinstance(url4, str)
    assert render(build(url4)) == url4
    assert url4.count(RESOLVE_CANDIDATE_ROUTE) == 1
    assert f"{RESOLVE_CANDIDATE_ROUTE}($candidate_members)!'$candidate_synthesizer'" in url4
    assert "$members" in url4
    assert "$validated_members" not in url4
    assert "{members:" not in url4
    assert "encoded" not in url4
    assert "!'members'" not in url4


def _model(model: str) -> str:
    return render(
        expr(
            src(
                RelExpr(path=f"/{model}", context="$input", intent=Text("Answer.")),
                name="model_1",
                weight=0.0,
            ),
            intent=Text("$model_1"),
        )
    )


def _candidate_resolution_url4(members: tuple[str, ...], synthesizer: str) -> str:
    bindings = [
        src(text(member), name=f"candidate_member_{index}", weight=0.0)
        for index, member in enumerate(members, 1)
    ]
    bindings.append(
        src(
            struct(
                {
                    f"member_{index}": {
                        "name": f"member-{index}",
                        "url4": f"$candidate_member_{index}",
                    }
                    for index in range(1, len(members) + 1)
                }
            ),
            name="candidate_members",
            weight=0.0,
        )
    )
    return render(
        expr(
            *bindings,
            RelExpr(
                path=RESOLVE_CANDIDATE_ROUTE,
                context="$candidate_members",
                intent=Text(synthesizer),
            ),
            intent=Text(""),
        )
    )


async def _resolve(tmp_path: Path, members: tuple[str, ...], synthesizer: str) -> object:
    node = Url4Node("test")
    model_routes = {
        "/provider/a",
        "/provider/b",
        "/provider/judge",
    }
    install_benchmarks(node, tmp_path, model_routes=model_routes)
    result = await node.evaluate(_candidate_resolution_url4(members, synthesizer))
    return json.loads(result.text)


@pytest.mark.asyncio
async def test_resolution_reads_ordinary_named_url4_member_bindings(tmp_path: Path) -> None:
    members = (_model("provider/a"), _model("provider/b"))

    resolved = await _resolve(tmp_path, members, _model("provider/judge"))

    assert isinstance(resolved, list)
    assert [member["key"] for member in resolved] == ["A", "B"]
    assert [member["name"] for member in resolved] == ["member-1", "member-2"]
    assert [member["expression"] for member in resolved] == list(members)


@pytest.mark.asyncio
async def test_resolution_rejects_a_nested_fusion_member_from_its_url4_shape(
    tmp_path: Path,
) -> None:
    nested_fusion = render(
        expr(
            src(
                RelExpr(path="/provider/a", context="$input", intent=Text("Answer.")),
                name="model_1",
                weight=0.0,
            ),
            src(
                RelExpr(path="/provider/b", context="$input", intent=Text("Answer.")),
                name="model_2",
                weight=0.0,
            ),
            src(
                RelExpr(path="/provider/judge", context="$model_1 $model_2", intent=Text("Pick.")),
                name="synthesis_1",
                weight=0.0,
            ),
            intent=Text("$synthesis_1"),
        )
    )

    with pytest.raises(ResolutionError) as caught:
        await _resolve(tmp_path, (_model("provider/a"), nested_fusion), _model("provider/judge"))

    assert caught.value.code == "benchmark_candidate_invalid"
    assert "direct Model" in str(caught.value)


@pytest.mark.asyncio
async def test_resolution_rejects_a_direct_call_to_an_undeclared_model_route(
    tmp_path: Path,
) -> None:
    """URL4 shape alone cannot distinguish a Model from a command or data endpoint."""

    with pytest.raises(ResolutionError) as caught:
        await _resolve(
            tmp_path,
            (_model("provider/a"), _model("benchmarks/ifeval/private-data")),
            _model("provider/judge"),
        )

    assert caught.value.code == "benchmark_candidate_invalid"
    assert "declared Model route" in str(caught.value)
