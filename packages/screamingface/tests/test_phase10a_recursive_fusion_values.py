from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pytest
from url4 import Url4Node, evaluate_sync

import screamingface as sf
from screamingface._compiler import compile_fusion
from screamingface.model_inputs import ParameterValue


def test_atomic_fusion_is_one_immutable_model_backed_recipe() -> None:
    params = {"temperature": 0.7, "max_tokens": 8192}

    opus = sf.Fusion(
        " Opus Sample 1 ",
        model="anthropic/claude-opus-4.8",
        prompt="Answer the research question.",
        params=params,
    )
    params["temperature"] = 0.0

    assert opus.name == "opus-sample-1"
    assert opus.model == "anthropic/claude-opus-4.8"
    assert opus.prompt == "Answer the research question."
    assert opus.params == {"temperature": 0.7, "max_tokens": 8192}
    assert opus.inputs == ()
    assert opus.reducer is None
    opus.params["temperature"] = 0.1
    assert opus.params["temperature"] == 0.7
    with pytest.raises(AttributeError):
        opus.name = "changed"  # type: ignore[misc]


def test_composite_fusion_recursively_consumes_fusions_and_string_shorthand() -> None:
    opus = sf.Fusion("opus", model="anthropic/claude-opus-4.8")
    frontier = sf.Fusion(
        "frontier",
        inputs=[opus, "openai/gpt-5.5"],
        reducer=sf.reducers.MajorityVote(),
    )
    refined = sf.Fusion(
        "refined",
        inputs=[frontier],
        reducer=sf.reducers.Model(
            model="anthropic/claude-opus-4.8",
            prompt="Critique and improve the answer.",
        ),
    )

    assert frontier.model is None
    assert frontier.inputs == (opus, "openai/gpt-5.5")
    assert isinstance(frontier.reducer, sf.reducers.MajorityVote)
    assert refined.inputs == (frontier,)
    assert isinstance(refined.reducer, sf.reducers.Model)


def test_reusing_one_explicit_fusion_preserves_object_identity() -> None:
    shared = sf.Fusion("shared", model="provider/shared")
    left = sf.Fusion(
        "left",
        inputs=[shared, "provider/left"],
        reducer=sf.reducers.MajorityVote(),
    )
    right = sf.Fusion(
        "right",
        inputs=[shared, "provider/right"],
        reducer=sf.reducers.MajorityVote(),
    )
    root = sf.Fusion(
        "root",
        inputs=[left, right, shared],
        reducer=sf.reducers.MajorityVote(),
    )

    assert left.inputs[0] is shared
    assert right.inputs[0] is shared
    assert root.inputs[2] is shared


def test_duplicate_explicit_names_are_rejected_but_reusing_one_value_is_valid() -> None:
    shared = sf.Fusion("sample", model="provider/shared")
    sf.Fusion(
        "shared-twice",
        inputs=[shared, shared],
        reducer=sf.reducers.MajorityVote(),
    )

    duplicate = sf.Fusion("sample", model="provider/other")
    with pytest.raises(ValueError, match="duplicate Fusion name 'sample'"):
        sf.Fusion(
            "ambiguous",
            inputs=[shared, duplicate],
            reducer=sf.reducers.MajorityVote(),
        )


def test_nested_recipe_reuses_shared_nodes_and_reports_atomic_members() -> None:
    shared = sf.Fusion("shared", model="provider/shared", prompt="Answer once.")
    left = sf.Fusion(
        "left",
        inputs=[shared, "provider/left"],
        reducer=sf.reducers.Model(model="provider/judge", prompt="Reduce left."),
    )
    root = sf.Fusion(
        "root",
        inputs=[left, shared],
        reducer=sf.reducers.Model(model="provider/judge", prompt="Reduce root."),
    )

    recipe = root.url4

    assert recipe.count("/provider/shared") == 1
    assert recipe.count("/provider/left") == 1
    assert recipe.count("!'Reduce left.'") == 1
    assert recipe.count("!'Reduce root.'") == 1
    assert tuple(member.model for member in root._members) == (
        "provider/shared",
        "provider/left",
    )


def test_nested_recipe_executes_as_one_url4_dag() -> None:
    shared = sf.Fusion("shared", model="provider/shared")
    left = sf.Fusion(
        "left",
        inputs=[shared, "provider/left"],
        reducer=sf.reducers.Model(model="provider/judge", prompt="Reduce left."),
    )
    root = sf.Fusion(
        "root",
        inputs=[left, shared],
        reducer=sf.reducers.Model(model="provider/judge", prompt="Reduce root."),
    )
    node = Url4Node("recursive-fusion")
    calls: list[tuple[str, str]] = []

    @node.endpoint("/provider/shared")
    def shared_model(request):
        calls.append((request.path, request.intent))
        return "shared answer"

    @node.endpoint("/provider/left")
    def left_model(request):
        calls.append((request.path, request.intent))
        return "left answer"

    @node.endpoint("/provider/judge")
    def judge(request):
        calls.append((request.path, request.intent))
        return "left fusion" if request.intent == "Reduce left." else "root fusion"

    result = evaluate_sync(compile_fusion(root, question="Question"), node)
    payload = json.loads(result.text)

    assert payload["answer"] == "root fusion"
    assert payload["members"] == {
        "member_1": {"model": "provider/shared", "answer": "shared answer"},
        "member_2": {"model": "provider/left", "answer": "left answer"},
    }
    assert calls.count(("/provider/shared", "Answer the question.")) == 1
    assert calls.count(("/provider/judge", "Reduce left.")) == 1
    assert calls.count(("/provider/judge", "Reduce root.")) == 1


def test_atomic_recipe_calls_one_model_and_returns_it_as_the_answer() -> None:
    fusion = sf.Fusion(
        "solo",
        model="provider/solo",
        prompt="Answer directly.",
        params={"temperature": 0.2},
    )

    recipe = fusion.url4

    assert "member_1=/provider/solo?temperature=0.2" in recipe
    assert "answer: '$member_1'" in recipe
    assert tuple(member.model for member in fusion._members) == ("provider/solo",)


def test_atomic_fusion_run_aggregates_with_itself_as_the_baseline() -> None:
    fusion = sf.Fusion("solo", model="provider/solo")
    benchmark = sf.Benchmark(
        "tiny@1",
        cases=[sf.Case("q1", "Choose A.", reference="A")],
        grader=sf.graders.ExactChoice(),
    )
    run = sf.Run(
        benchmark=benchmark,
        fusion_name=fusion.name,
        fusion_url4=fusion.url4,
        members={"member_1": "provider/solo"},
        cases=benchmark._materialize_cases(),
        results=[
            sf.CaseResult(
                "q1",
                members={"member_1": sf.MemberResult("provider/solo", "A")},
                answer="A",
            )
        ],
    )

    report = run.grade(progress=False).aggregate()

    assert report.score == 1.0
    assert report.baseline == 1.0
    assert report.gain == 0.0


def test_equal_atomic_configurations_remain_independent_when_separately_named() -> None:
    first = sf.Fusion(
        "opus-sample-1",
        model="anthropic/claude-opus-4.8",
        params={"temperature": 0.7},
    )
    second = sf.Fusion(
        "opus-sample-2",
        model="anthropic/claude-opus-4.8",
        params={"temperature": 0.7},
    )
    self_fusion = sf.Fusion(
        "opus-self-fusion",
        inputs=[first, second],
        reducer=sf.reducers.MajorityVote(),
    )

    assert first is not second
    assert self_fusion.inputs == (first, second)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.Fusion("missing"), "model or inputs"),
        (
            lambda: sf.Fusion(
                "both",
                model="provider/model",
                inputs=["provider/other"],
                reducer=sf.reducers.MajorityVote(),
            ),
            "model or inputs",
        ),
        (
            lambda: sf.Fusion(
                "atomic-reducer",
                model="provider/model",
                reducer=sf.reducers.MajorityVote(),
            ),
            "atomic.*reducer",
        ),
        (
            lambda: sf.Fusion("composite-no-reducer", inputs=["provider/model"]),
            "composite.*reducer",
        ),
        (
            lambda: sf.Fusion(
                "empty",
                inputs=[],
                reducer=sf.reducers.MajorityVote(),
            ),
            "at least one input",
        ),
        (
            lambda: sf.Fusion(
                "not-sequence",
                inputs=cast(Sequence[str | sf.Fusion], "provider/model"),
                reducer=sf.reducers.MajorityVote(),
            ),
            "sequence",
        ),
        (
            lambda: sf.Fusion(
                "mapping",
                inputs=cast(
                    Sequence[str | sf.Fusion],
                    [{"model": "provider/model"}, "provider/other"],
                ),
                reducer=sf.reducers.MajorityVote(),
            ),
            "model IDs or sf.Fusion",
        ),
        (
            lambda: sf.Fusion(
                "composite-params",
                inputs=["provider/one", "provider/two"],
                reducer=sf.reducers.MajorityVote(),
                params={"temperature": 0.2},
            ),
            "composite.*params",
        ),
    ],
)
def test_atomic_and_composite_modes_are_unambiguous(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.Fusion("", model="provider/model"), "name"),
        (lambda: sf.Fusion("sample", model=""), "model"),
        (lambda: sf.Fusion("sample", model="provider/model", prompt=""), "prompt"),
        (
            lambda: sf.Fusion(
                "sample",
                model="provider/model",
                params=cast(Mapping[str, ParameterValue], []),
            ),
            "mapping",
        ),
        (
            lambda: sf.Fusion(
                "sample",
                model="provider/model",
                params={"tools": "web_search"},
            ),
            "reserved",
        ),
    ],
)
def test_atomic_fusion_reuses_model_call_validation(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_discarded_graph_types_and_old_models_keyword_do_not_exist() -> None:
    assert not hasattr(sf, "Model")
    assert not hasattr(sf, "FusionMonster")
    assert not hasattr(sf, "Experiment")
    assert not hasattr(sf, "Solo")
    assert not hasattr(sf, "Lineup")

    with pytest.raises(TypeError, match="unexpected keyword argument 'models'"):
        cast(Any, sf.Fusion)(
            "old-shape",
            models=["provider/one", "provider/two"],
            reducer=sf.reducers.MajorityVote(),
        )
