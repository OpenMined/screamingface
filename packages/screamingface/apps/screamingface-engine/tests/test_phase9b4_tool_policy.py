from __future__ import annotations

import pytest
from url4 import ResolutionError

from screamingface_engine.benchmarks import DRACO_TOOL_POLICY
from screamingface_engine.tool_policy import parse_tool_policy, parse_tool_policy_document


def _params() -> dict[str, str]:
    return {
        "tools": "web_fetch:web_search",
        "tools.max_calls": "12",
        "temperature": "0.2",
        "web_search.max_results": "5",
        "web_search.include_domain.1": "one.example",
        "web_search.include_domain.2": "two.example",
        "web_search.exclude_domain.1": "blocked.example",
    }


def test_policy_parser_separates_model_and_portable_tool_fields() -> None:
    parsed = parse_tool_policy(_params())

    assert parsed.model_params == {"temperature": "0.2"}
    assert parsed.policy is not None
    assert parsed.policy.tools == frozenset({"web_search", "web_fetch"})
    assert parsed.policy.max_calls == 12
    assert parsed.policy.search is not None
    assert parsed.policy.search.max_results == 5
    assert parsed.policy.search.include_domains == ("one.example", "two.example")
    assert parsed.policy.search.exclude_domains == ("blocked.example",)
    assert parsed.policy.fetch is not None


def test_policy_translates_to_tavily_and_openrouter_at_the_engine_boundary() -> None:
    policy = parse_tool_policy(_params()).policy
    assert policy is not None and policy.search is not None and policy.fetch is not None

    assert policy.search.tavily_request_body("evidence")["query"] == "evidence"
    assert policy.search.tavily_request_body("evidence")["exclude_domains"] == ["blocked.example"]
    assert policy.search.openrouter_parameters(max_calls=12) == {
        "engine": "auto",
        "max_results": 5,
        "max_total_results": 60,
        "allowed_domains": ["one.example", "two.example"],
        "excluded_domains": ["blocked.example"],
    }
    assert policy.fetch.tavily_request_body("https://example.org", query="focused") == {
        "urls": ["https://example.org"],
        "query": "focused",
        "extract_depth": "basic",
        "include_images": False,
        "include_favicon": False,
        "format": "markdown",
        "include_usage": False,
    }


def test_tool_free_policy_forwards_only_model_parameters() -> None:
    parsed = parse_tool_policy({"temperature": "0", "max_tokens": "8"})
    assert parsed.model_params == {"temperature": "0", "max_tokens": "8"}
    assert parsed.policy is None


def test_versioned_policy_document_decodes_the_same_portable_contract() -> None:
    import json

    policy = parse_tool_policy_document(json.dumps(DRACO_TOOL_POLICY))

    assert policy.tools == frozenset({"web_search", "web_fetch"})
    assert policy.max_calls == 12
    assert policy.search is not None
    assert policy.search.max_results == 5
    assert policy.search.include_domains == ()
    assert policy.search.exclude_domains[0].startswith("huggingface.co/")
    assert policy.fetch is not None


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "[]",
        '{"schema":"wrong","tools":[],"max_calls":1,"web_search":null}',
        '{"schema":"screamingface.tool-policy.v1","tools":["web_search"],'
        '"max_calls":12,"web_search":null}',
        '{"schema":"screamingface.tool-policy.v1","tools":["web_fetch"],'
        '"max_calls":12,"web_search":{}}',
    ],
)
def test_versioned_policy_document_fails_closed(body: str) -> None:
    with pytest.raises(ResolutionError) as captured:
        parse_tool_policy_document(body)
    assert captured.value.code in {"malformed_tool_policy", "unsupported_tool"}
    assert captured.value.permanent is True


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"tools": "web_search:web_search"}, "unique"),
        ({"tools": "unknown"}, "unsupported tool"),
        ({"tools.max_calls": "12"}, "tool-free"),
        ({"tools": "web_search", "web_search.max_results": "5"}, "tools.max_calls"),
        (
            {
                "tools": "web_search",
                "tools.max_calls": "0",
                "web_search.max_results": "5",
            },
            "positive integer",
        ),
        (
            {
                "tools": "web_search",
                "tools.max_calls": "33",
                "web_search.max_results": "5",
            },
            "1 to 32",
        ),
        (
            {
                "tools": "web_search",
                "tools.max_calls": "2",
                "web_search.unknown": "x",
                "web_search.max_results": "5",
            },
            "unknown web-search",
        ),
        (
            {
                "tools": "web_fetch",
                "tools.max_calls": "2",
                "web_search.max_results": "5",
            },
            "undeclared",
        ),
    ],
)
def test_policy_parser_rejects_invalid_declarations(params: dict[str, str], message: str) -> None:
    with pytest.raises(ResolutionError, match=message) as captured:
        parse_tool_policy(params)
    assert captured.value.code in {"malformed_tool_policy", "unsupported_tool"}
    assert captured.value.permanent is True


def test_policy_requires_search_result_limit_and_contiguous_domains() -> None:
    missing = _params()
    del missing["web_search.max_results"]
    with pytest.raises(ResolutionError, match="missing"):
        parse_tool_policy(missing)

    gapped = _params()
    del gapped["web_search.include_domain.1"]
    with pytest.raises(ResolutionError, match="contiguous"):
        parse_tool_policy(gapped)

    too_many = _params()
    too_many["web_search.max_results"] = "21"
    with pytest.raises(ResolutionError, match="1 to 20"):
        parse_tool_policy(too_many)
