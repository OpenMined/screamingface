"""Contracts for the full-topology DRACO Lite candidate study."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import screamingface as sf
from screamingface._compiler import _CandidateSpecCompiler
from screamingface.recipe import Recipe

NOTEBOOK = Path(__file__).parents[1] / "examples" / "05_draco_quickstart.ipynb"


def _document() -> dict[str, object]:
    return cast(dict[str, object], json.loads(NOTEBOOK.read_text()))


def _composition_source() -> str:
    cells = cast(list[dict[str, object]], _document()["cells"])
    sources = [
        "".join(cast(list[str], cell["source"]))
        for cell in cells
        if cell.get("cell_type") == "code"
        and "DRACO_ANSWER_PROMPT" in "".join(cast(list[str], cell["source"]))
    ]
    assert len(sources) == 1
    return sources[0]


def _candidates() -> tuple[Recipe, ...]:
    namespace: dict[str, object] = {"sf": sf}
    exec(compile(_composition_source(), NOTEBOOK.name, "exec"), namespace)  # noqa: S102
    values = namespace["candidates"]
    assert isinstance(values, tuple)
    return cast(tuple[Recipe, ...], values)


def test_draco_lite_notebook_is_output_free_and_python_valid() -> None:
    cells = cast(list[dict[str, object]], _document()["cells"])
    assert all(cell.get("outputs", []) == [] for cell in cells)
    for cell in cells:
        if cell.get("cell_type") == "code":
            source = "".join(cast(list[str], cell["source"]))
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_draco_lite_matches_the_seven_solo_nine_fusion_topology() -> None:
    candidates = _candidates()

    assert len(candidates) == 16
    assert sum(isinstance(value, sf.Model) for value in candidates) == 7
    assert sum(isinstance(value, sf.Fusion) for value in candidates) == 9
    assert [value.name for value in candidates] == [
        "claude-fable-5",
        "claude-opus-4.8",
        "gpt-5.5",
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "kimi-k2.5",
        "deepseek-v4-pro",
        "fable-plus-gpt",
        "frontier-trio",
        "opus-plus-gpt",
        "opus-self-fusion",
        "budget-trio",
        "beat-runner-up",
        "pareto-cross",
        "pareto-lean",
        "best-open-source",
    ]


def test_candidate_spec_shares_reused_leaves_but_not_sampled_opus_calls() -> None:
    specification = _CandidateSpecCompiler().compile(_candidates())
    nodes = cast(dict[str, dict[str, object]], specification["nodes"])
    candidates = cast(dict[str, dict[str, str]], specification["candidates"])
    roots = {entry["name"]: entry["root"] for entry in candidates.values()}

    assert len(nodes) == 19
    assert sum(value["kind"] == "model" for value in nodes.values()) == 10
    assert sum(value["kind"] == "fusion" for value in nodes.values()) == 9
    assert tuple(candidates) == tuple(f"candidate_{position}" for position in range(1, 17))
    assert len(roots) == 16

    opus_root = roots["claude-opus-4.8"]
    frontier = nodes[roots["frontier-trio"]]
    assert cast(dict[str, str], frontier["members"])["member_1"] == opus_root

    self_fusion = nodes[roots["opus-self-fusion"]]
    self_members = tuple(cast(dict[str, str], self_fusion["members"]).values())
    assert self_members[0] != self_members[1]
    assert nodes[self_members[0]]["model"] == nodes[self_members[1]]["model"]


def test_documented_nominal_call_count_is_179() -> None:
    markdown = "\n".join(
        "".join(cast(list[str], cell["source"]))
        for cell in cast(list[dict[str, object]], _document()["cells"])
        if cell.get("cell_type") == "markdown"
    )

    research_calls = 10
    synthesis_calls = 9
    judge_calls = 16 * 10 * 1
    assert research_calls + synthesis_calls + judge_calls == 179
    assert "179 model calls" in markdown
    assert "draco.evaluate(candidates)" in "\n".join(
        "".join(cast(list[str], cell["source"]))
        for cell in cast(list[dict[str, object]], _document()["cells"])
        if cell.get("cell_type") == "code"
    )


def test_composition_is_explicit_without_hidden_construction_helpers() -> None:
    source = _composition_source()

    assert "def solo(" not in source
    assert "def synth(" not in source
    assert "answer_params =" not in source
    assert "synthesis_params =" not in source
    assert source.count("sf.Model(") == 10
    assert source.count("sf.Fusion(") == 9
    assert source.count("sf.reducers.Model(") == 9
