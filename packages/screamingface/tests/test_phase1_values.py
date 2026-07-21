from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import cast

import pytest

import screamingface as sf


def test_config_is_network_free_and_returns_none() -> None:
    assert sf.config(engine="http://127.0.0.1:4404") is None


@pytest.mark.parametrize(
    "engine",
    [
        "",
        "localhost:4404",
        "ftp://engine.test",
        "https://engine.test/prefix",
        "https://engine.test/?token=value",
        "https://engine.test/#fragment",
    ],
)
def test_config_rejects_invalid_engine_urls(engine: str) -> None:
    with pytest.raises(ValueError, match="engine"):
        sf.config(engine=engine)


def test_config_normalizes_an_origin_only() -> None:
    from screamingface._config import current_engine_url

    sf.config(engine=" HTTPS://Engine.Test:4404/ ")

    assert current_engine_url() == "https://Engine.Test:4404"


def test_case_is_immutable_and_defensively_owns_json_values() -> None:
    reference = {"sections": [{"id": "facts"}]}
    metadata = {"domain": "science"}
    case = sf.Case("q1", "What is true?", reference=reference, metadata=metadata)

    reference["sections"].append({"id": "changed"})
    metadata["domain"] = "changed"

    assert case.id == "q1"
    assert case.input == "What is true?"
    assert case.reference == {"sections": [{"id": "facts"}]}
    assert case.metadata == {"domain": "science"}
    with pytest.raises(AttributeError):
        setattr(case, "input", "changed")


def test_benchmark_uses_one_compact_definition_for_local_cases() -> None:
    case = sf.Case("q1", "2 + 2?", reference="B")
    benchmark = sf.Benchmark(
        "arithmetic@1",
        title="Arithmetic",
        cases=[case],
        grader=sf.graders.ExactChoice(),
        aggregator=sf.aggregators.Mean(),
    )

    assert benchmark.id == "arithmetic@1"
    assert benchmark.title == "Arithmetic"
    assert benchmark.tools == ()
    assert isinstance(benchmark.grader, sf.Grader)
    assert isinstance(benchmark.aggregator, sf.Aggregator)
    assert not hasattr(benchmark, "iter_cases")
    assert not hasattr(benchmark, "cases")


def test_fusion_authoring_is_network_free_and_uses_namespaced_strategies() -> None:
    sf.config(engine="http://engine-that-does-not-exist.invalid")
    gemini = sf.Model(
        "gemini/2.5-flash",
        name="gemini",
        prompt="Answer carefully: $question",
        params={"temperature": 0.2},
    )
    fusion = sf.Fusion(
        "frontier-trio",
        members=[
            "codex/gpt-5.5",
            gemini,
            "claude/sonnet-4.6",
        ],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Synthesize $member_answers",
            params={"temperature": 0.0},
        ),
    )

    assert fusion.model_ids == (
        "codex/gpt-5.5",
        "gemini/2.5-flash",
        "claude/sonnet-4.6",
    )
    assert fusion.members[1] is gemini
    assert isinstance(fusion.reducer, sf.reducers.Model)


def test_concrete_strategies_exist_only_in_namespaces() -> None:
    assert isinstance(sf.reducers.MajorityVote(), sf.Reducer)
    assert isinstance(sf.graders.ExactChoice(), sf.Grader)
    assert isinstance(
        sf.graders.Rubric(
            model="gemini/3.1-pro-preview",
            prompt="Judge one criterion",
            passes=5,
            params={"reasoning": "low"},
        ),
        sf.Grader,
    )
    assert isinstance(sf.aggregators.Mean(), sf.Aggregator)

    assert not hasattr(sf, "MajorityVote")
    assert not hasattr(sf, "ModelReducer")
    assert not hasattr(sf, "RubricJudge")
    assert not hasattr(sf, "judges")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.Case("", "input"), "case id"),
        (lambda: sf.Case("q", ""), "case input"),
        (lambda: sf.Case("q", "input", reference=math.nan), "JSON values"),
        (
            lambda: sf.Case("q", "input", metadata=cast(Mapping[str, object], [])),
            "mapping",
        ),
        (
            lambda: sf.Benchmark("b", cases=[], grader=sf.graders.ExactChoice()),
            "at least one case",
        ),
        (
            lambda: sf.Benchmark(
                "b",
                cases=cast(Sequence[sf.Case], ["not a case"]),
                grader=sf.graders.ExactChoice(),
            ),
            "sf.Case",
        ),
        (
            lambda: sf.Benchmark(
                "b",
                cases=[sf.Case("q", "input")],
                grader=cast(sf.Grader, "wrong"),
            ),
            "sf.Grader",
        ),
        (
            lambda: sf.Benchmark(
                "b",
                cases=[sf.Case("q", "input")],
                grader=sf.graders.ExactChoice(),
                aggregator=cast(sf.Aggregator, "wrong"),
            ),
            "sf.Aggregator",
        ),
        (
            lambda: sf.Benchmark(
                "b",
                cases=[sf.Case("q", "input")],
                grader=sf.graders.ExactChoice(),
                tools=[sf.tools.WebSearch(), sf.tools.WebSearch()],
                max_tool_calls=1,
            ),
            "unique",
        ),
        (
            lambda: sf.Benchmark(
                "b",
                cases=[sf.Case("q", "input")],
                grader=sf.graders.ExactChoice(),
                tools=cast(Sequence[sf.tools.Tool], ["Web-Search"]),
                max_tool_calls=1,
            ),
            "sf.tools",
        ),
    ],
)
def test_case_and_benchmark_validation(factory: Callable[[], object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_callable_case_source_is_validated_when_materialized() -> None:
    benchmark = sf.Benchmark(
        "duplicates",
        cases=lambda: (sf.Case("same", "one"), sf.Case("same", "two")),
        grader=sf.graders.ExactChoice(),
    )

    with pytest.raises(ValueError, match="duplicate case ID"):
        benchmark._materialize_cases()


def test_strategy_parameters_are_defensive_and_validated() -> None:
    reducer = sf.reducers.Model(model="judge", prompt="reduce", params={"temperature": 0.2})
    reducer.params["temperature"] = 1.0
    assert reducer.params == {"temperature": 0.2}
    rubric = sf.graders.Rubric(model="judge", prompt="grade", params={"reasoning": "low"})
    rubric.params["reasoning"] = "high"
    assert rubric.params == {"reasoning": "low"}
    with pytest.raises(ValueError, match="positive integer"):
        sf.graders.Rubric(model="judge", prompt="grade", passes=0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: sf.Model(
            "one",
            name="reserved",
            params={"tools": "web_search"},
        ),
        lambda: sf.reducers.Model(
            model="judge",
            prompt="reduce",
            params={"tools": "web_search"},
        ),
        lambda: sf.graders.Rubric(
            model="judge",
            prompt="grade",
            params={"tools": "web_search"},
        ),
    ],
)
def test_tools_are_not_generic_model_parameters(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match="reserved.*sf.Benchmark"):
        factory()


def test_fusion_repr_is_compact_and_does_not_contact_the_engine() -> None:
    fusion = sf.Fusion(
        "My Fusion",
        members=["model/a", "model/b"],
        reducer=sf.reducers.MajorityVote(),
    )

    assert fusion.name == "my-fusion"
    assert "model/a" in repr(fusion)
    with pytest.raises(AttributeError):
        setattr(fusion, "name", "changed")
