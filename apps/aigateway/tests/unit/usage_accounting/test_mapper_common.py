"""Provider-neutral mapper policy shared by every accounting plugin."""

from __future__ import annotations

from aigateway.plugins.taxonomy.mapper import (
    bounded_count,
    cache_write_tokens,
    final_detail_or_none,
    mapping_or_none,
    response_string,
    usage_and_source,
)


def test_bounded_count_requires_an_exact_json_safe_integer() -> None:
    assert bounded_count(0) == 0
    assert bounded_count(2**53 - 1) == 2**53 - 1
    assert bounded_count(True) is None
    assert bounded_count(-1) is None
    assert bounded_count(2**53) is None


def test_mapping_and_response_string_are_total_over_plugin_values() -> None:
    assert mapping_or_none({"usage": {}}) == {"usage": {}}
    assert mapping_or_none(["not", "a", "mapping"]) is None
    assert response_string({"model": "raw"}, {"model": "converted"}, field="model") == "raw"
    assert response_string({"model": 1}, {"model": "converted"}, field="model") == "converted"
    assert response_string(None, {"model": ""}, field="model") is None


def test_raw_usage_precedes_the_converted_fallback() -> None:
    raw = {"usage": {"prompt_tokens": 1}}
    converted = {"usage": {"prompt_tokens": 2}}
    assert usage_and_source(raw, converted) == (raw["usage"], "provider_raw_response")
    assert usage_and_source(None, converted) == (
        converted["usage"],
        "provider_converted_response",
    )
    assert usage_and_source(None, None) == (None, "provider_raw_response")


def test_converted_synthetic_zero_is_unknown_but_raw_zero_is_evidence() -> None:
    assert final_detail_or_none(0, "provider_raw_response") == 0
    assert final_detail_or_none(0, "provider_converted_response") is None


def test_cache_write_alias_fallback_is_based_on_presence_not_truthiness() -> None:
    assert cache_write_tokens({"cache_write_tokens": 0}, "provider_raw_response") == 0
    assert (
        cache_write_tokens(
            {"cache_write_tokens": "bad", "cache_creation_tokens": 7},
            "provider_raw_response",
        )
        is None
    )
    assert cache_write_tokens({"cache_creation_tokens": 7}, "provider_raw_response") == 7
