from __future__ import annotations

import pytest

from aigateway.core.request_cache.keys import (
    CacheBypass,
    CacheControls,
    CacheKeyResult,
    build_cache_key,
    parse_cache_controls,
)

_BASE_KW = {
    "account_id": "acct-1",
    "profile_name": "default",
    "provider": "anthropic",
}


def _body(**overrides):
    body = {
        "model": "anthropic/claude-haiku-4-5",
        "messages": [{"role": "user", "content": "hi"}],
    }
    body.update(overrides)
    return body


def _key(**kw) -> CacheKeyResult:
    merged = {**_BASE_KW, "normalized_body": _body()}
    merged.update(kw)
    result = build_cache_key(**merged)
    assert isinstance(result, CacheKeyResult), result
    return result


class TestKeyHashing:
    def test_dict_key_order_does_not_change_hash(self) -> None:
        a = build_cache_key(
            **_BASE_KW,
            normalized_body={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        b = build_cache_key(
            **_BASE_KW,
            normalized_body={
                "messages": [{"content": "hi", "role": "user"}],
                "model": "anthropic/claude-haiku-4-5",
            },
        )
        assert isinstance(a, CacheKeyResult) and isinstance(b, CacheKeyResult)
        assert a.key_hash == b.key_hash
        assert a.prompt_hash == b.prompt_hash

    def test_different_messages_change_hash(self) -> None:
        a = _key()
        b = _key(normalized_body=_body(messages=[{"role": "user", "content": "bye"}]))
        assert a.key_hash != b.key_hash

    def test_message_order_changes_hash(self) -> None:
        m1 = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        m2 = [{"role": "user", "content": "b"}, {"role": "user", "content": "a"}]
        assert (
            _key(normalized_body=_body(messages=m1)).key_hash
            != _key(normalized_body=_body(messages=m2)).key_hash
        )

    def test_different_model_changes_hash(self) -> None:
        a = _key()
        b = _key(normalized_body=_body(model="anthropic/claude-sonnet-4-6"))
        assert a.key_hash != b.key_hash

    def test_different_provider_changes_hash(self) -> None:
        assert _key(provider="anthropic").key_hash != _key(provider="codex").key_hash

    def test_different_account_changes_hash(self) -> None:
        assert _key(account_id="acct-1").key_hash != _key(account_id="acct-2").key_hash

    def test_different_profile_changes_hash(self) -> None:
        assert _key(profile_name="default").key_hash != _key(profile_name="work").key_hash

    def test_top_level_system_is_part_of_prompt(self) -> None:
        a = _key()
        b = _key(normalized_body=_body(system=[{"type": "text", "text": "be brief"}]))
        assert a.prompt_hash != b.prompt_hash

    def test_result_contains_no_raw_prompt_in_hashes(self) -> None:
        result = _key(
            normalized_body=_body(messages=[{"role": "user", "content": "SECRET-PROMPT"}])
        )
        assert "SECRET-PROMPT" not in result.key_hash
        assert "SECRET-PROMPT" not in result.prompt_hash
        assert len(result.key_hash) == 64
        assert len(result.prompt_hash) == 64


class TestEligibility:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("temperature", 0.2),
            ("max_tokens", 128),
            ("response_format", {"type": "json_object"}),
            ("tools", [{"type": "function"}]),
            ("tool_choice", "auto"),
            ("reasoning", {"effort": "high"}),
            ("reasoning_effort", "high"),
            ("top_p", 0.9),
            ("stop", ["x"]),
            ("presence_penalty", 0.1),
            ("logit_bias", {"1": 1}),
            ("some_unknown_field", 1),
        ],
    )
    def test_output_affecting_fields_bypass(self, field, value) -> None:
        result = build_cache_key(**_BASE_KW, normalized_body=_body(**{field: value}))
        assert isinstance(result, CacheBypass)
        assert result.reason == "unsupported_fields"

    def test_stream_true_bypasses(self) -> None:
        result = build_cache_key(**_BASE_KW, normalized_body=_body(stream=True))
        assert isinstance(result, CacheBypass)
        assert result.reason == "stream"

    def test_stream_false_is_ignored(self) -> None:
        assert isinstance(
            build_cache_key(**_BASE_KW, normalized_body=_body(stream=False)), CacheKeyResult
        )

    @pytest.mark.parametrize("field", ["timeout", "api_key", "extra_headers"])
    def test_transport_fields_are_ignored(self, field) -> None:
        a = _key()
        b = build_cache_key(**_BASE_KW, normalized_body=_body(**{field: "whatever"}))
        assert isinstance(b, CacheKeyResult)
        assert a.key_hash == b.key_hash

    def test_non_dict_body_bypasses(self) -> None:
        result = build_cache_key(**_BASE_KW, normalized_body=["not", "a", "dict"])  # type: ignore[arg-type]
        assert isinstance(result, CacheBypass)

    def test_non_list_messages_bypasses(self) -> None:
        result = build_cache_key(**_BASE_KW, normalized_body=_body(messages="oops"))
        assert isinstance(result, CacheBypass)


class TestCacheControls:
    def test_absent_cache_field_means_not_requested(self) -> None:
        body = _body()
        controls = parse_cache_controls(body)
        assert isinstance(controls, CacheControls)
        assert controls.use_cache is False
        assert "cache" not in body

    def test_controls_are_popped_from_body(self) -> None:
        body = _body(cache={"use-cache": True, "ttl": 60})
        controls = parse_cache_controls(body)
        assert controls.use_cache is True
        assert controls.ttl == 60
        assert "cache" not in body  # never forwarded to providers

    def test_all_fields_parse(self) -> None:
        body = _body(
            cache={
                "use-cache": True,
                "ttl": 120,
                "s-maxage": 30,
                "no-cache": True,
                "no-store": True,
            }
        )
        controls = parse_cache_controls(body)
        assert (controls.use_cache, controls.ttl, controls.s_maxage) == (True, 120, 30)
        assert (controls.no_cache, controls.no_store) == (True, True)

    def test_malformed_cache_field_is_ignored(self) -> None:
        body = _body(cache="not-a-dict")
        controls = parse_cache_controls(body)
        assert controls.use_cache is False
        assert "cache" not in body
