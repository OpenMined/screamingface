from __future__ import annotations

import pytest
from url4 import ResolutionError

from screamingface_engine.tool_policy import parse_tool_policy


def _search_params() -> dict[str, str]:
    return {
        "tools": "web_fetch web_search",
        "max_tool_rounds": "12",
        "temperature": "0.2",
        "tavily.search.search_depth": "advanced",
        "tavily.search.chunks_per_source": "3",
        "tavily.search.max_results": "5",
        "tavily.search.topic": "general",
        "tavily.search.include_answer": "basic",
        "tavily.search.include_raw_content": "markdown",
        "tavily.search.include_images": "true",
        "tavily.search.include_image_descriptions": "true",
        "tavily.search.include_favicon": "true",
        "tavily.search.include_domain.1": "one.example",
        "tavily.search.include_domain.2": "two.example",
        "tavily.search.exclude_domain.1": "blocked.example",
        "tavily.search.country": "united kingdom",
        "tavily.search.auto_parameters": "false",
        "tavily.search.exact_match": "true",
        "tavily.search.include_usage": "true",
        "tavily.search.safe_search": "false",
        "tavily.extract.extract_depth": "advanced",
        "tavily.extract.chunks_per_source": "4",
        "tavily.extract.include_images": "true",
        "tavily.extract.include_favicon": "true",
        "tavily.extract.format": "text",
        "tavily.extract.timeout": "30",
        "tavily.extract.include_usage": "true",
    }


def test_policy_parser_separates_model_loop_and_tavily_fields() -> None:
    parsed = parse_tool_policy(_search_params())

    assert parsed.model_params == {"temperature": "0.2"}
    assert parsed.policy is not None
    assert parsed.policy.tools == frozenset({"web_search", "web_fetch"})
    assert parsed.policy.max_rounds == 12
    assert parsed.policy.search is not None
    assert parsed.policy.search.include_domains == ("one.example", "two.example")
    assert parsed.policy.search.include_answer == "basic"
    assert parsed.policy.extract is not None
    assert parsed.policy.extract.timeout == 30.0
    assert parsed.policy.extract.request_body("https://example.org", query="focused") == {
        "urls": ["https://example.org"],
        "query": "focused",
        "extract_depth": "advanced",
        "chunks_per_source": 4,
        "include_images": True,
        "include_favicon": True,
        "format": "text",
        "timeout": 30.0,
        "include_usage": True,
    }


def test_tool_free_policy_forwards_only_model_parameters() -> None:
    parsed = parse_tool_policy({"temperature": "0", "max_tokens": "8"})

    assert parsed.model_params == {"temperature": "0", "max_tokens": "8"}
    assert parsed.policy is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"tools": "web_search web_search"}, "unique"),
        ({"tools": "unknown"}, "unsupported tool"),
        ({"max_tool_rounds": "12"}, "tool-free"),
        ({"tools": "web_search"}, "max_tool_rounds"),
        ({"tools": "web_search", "max_tool_rounds": "0"}, "positive integer"),
        ({"tools": "web_search", "max_tool_rounds": "true"}, "positive integer"),
        (
            {"tools": "web_search", "max_tool_rounds": "2", "tavily.search.unknown": "x"},
            "unknown Tavily",
        ),
        (
            {
                "tools": "web_fetch",
                "max_tool_rounds": "2",
                "tavily.search.search_depth": "basic",
            },
            "undeclared",
        ),
    ],
)
def test_policy_parser_rejects_invalid_declarations_before_execution(
    change: dict[str, str], message: str
) -> None:
    with pytest.raises(ResolutionError, match=message) as captured:
        parse_tool_policy(change)

    assert captured.value.code in {"malformed_tool_policy", "unsupported_tool"}
    assert captured.value.permanent is True


def test_policy_parser_requires_complete_compiler_contract_and_contiguous_domains() -> None:
    missing = _search_params()
    del missing["tavily.search.max_results"]
    with pytest.raises(ResolutionError, match="missing"):
        parse_tool_policy(missing)

    gapped = _search_params()
    del gapped["tavily.search.include_domain.1"]
    with pytest.raises(ResolutionError, match="contiguous"):
        parse_tool_policy(gapped)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("tavily.search.max_results", "21", "0 to 20"),
        ("tavily.search.include_images", "yes", "boolean"),
        ("tavily.search.start_date", "20-07-2026", "YYYY-MM-DD"),
        ("tavily.search.end_date", "2020-01-01", "later"),
        ("tavily.extract.timeout", "61", "1 to 60"),
    ],
)
def test_policy_parser_repeats_sdk_value_and_cross_field_validation(
    key: str, value: str, message: str
) -> None:
    params = _search_params()
    if key == "tavily.search.start_date":
        params[key] = value
    elif key == "tavily.search.end_date":
        params["tavily.search.start_date"] = "2026-07-20"
        params[key] = value
    else:
        params[key] = value

    with pytest.raises(ResolutionError, match=message) as captured:
        parse_tool_policy(params)

    assert captured.value.code == "malformed_tool_policy"
