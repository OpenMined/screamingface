from __future__ import annotations

import pytest

import screamingface as sf
from screamingface import connections
from screamingface._connection_preflight import require_connections
from screamingface._profile import ModelRecord, ProviderRecord, ReducerRecord, Registry
from screamingface._requirements import evaluate_requirements, run_requirements


def _registry() -> Registry:
    return Registry(
        models=(
            ModelRecord(
                "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
                ("web_search", "web_fetch"),
                "huggingface",
                ("tavily",),
            ),
        ),
        reducers=(ReducerRecord("majority_vote", "/reducers/majority-vote/1"),),
        response_schemas=(
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ),
        max_request_target_bytes=61_440,
        providers=(
            ProviderRecord("huggingface", "Hugging Face", ("api_key",)),
            ProviderRecord("tavily", "Tavily", ("api_key",)),
        ),
    )


def _benchmark() -> sf.Benchmark:
    return sf.Benchmark(
        "research@1",
        cases=[sf.Case("one", "Question", reference="A")],
        grader=sf.graders.ExactChoice(),
        tools=(sf.tools.WebSearch(), sf.tools.WebFetch()),
        max_tool_calls=12,
    )


def _fusion() -> sf.Fusion:
    return sf.Fusion(
        "research",
        members=[
            "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
            "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
        ],
        reducer=sf.reducers.MajorityVote(),
    )


def test_tool_enabled_run_requires_tavily_separately_from_member_models() -> None:
    requirements = run_requirements(_fusion(), _benchmark(), _registry())

    assert [(item.provider, item.model, item.role) for item in requirements] == [
        (
            "huggingface",
            "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
            "member",
        ),
        ("tavily", None, "tool"),
    ]
    assert evaluate_requirements(_fusion(), _benchmark(), _registry()) == requirements


def test_connection_error_lists_tavily_without_calling_it_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry()
    monkeypatch.setattr(
        connections,
        "_list_for_registry",
        lambda _registry: (
            sf.Connection(
                "huggingface",
                "Hugging Face",
                ("api_key",),
                "connected",
                "api_key",
                None,
            ),
            sf.Connection("tavily", "Tavily", ("api_key",), "not_connected", None, None),
        ),
    )

    with pytest.raises(sf.ConnectionRequiredError) as captured:
        require_connections(run_requirements(_fusion(), _benchmark(), registry), registry)

    assert captured.value.providers == ("tavily",)
    assert captured.value.models == ()
    assert captured.value.roles == ("tool",)
    assert "required connection" in str(captured.value)
    assert "sf.connect('tavily', api_key=...)" in str(captured.value)


def test_openrouter_managed_tools_do_not_require_tavily() -> None:
    registry = Registry(
        models=(
            ModelRecord(
                "openrouter/google/gemini-3.1-pro-preview",
                ("web_search", "web_fetch"),
                "openrouter",
                (),
            ),
        ),
        reducers=(ReducerRecord("majority_vote", "/reducers/majority-vote/1"),),
        response_schemas=("screamingface.recipe-result.v1", "screamingface.report.v1"),
        max_request_target_bytes=61_440,
        providers=(
            ProviderRecord("openrouter", "OpenRouter", ("api_key",)),
            ProviderRecord("tavily", "Tavily", ("api_key",)),
        ),
    )
    recipe = sf.Model("openrouter/google/gemini-3.1-pro-preview")
    requirements = run_requirements(recipe, _benchmark(), registry)
    assert [(item.provider, item.role) for item in requirements] == [("openrouter", "member")]
