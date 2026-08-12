"""OME-781 — OpenRouter native web search becomes cacheable.

FEATURE: `web_search` / `web_search_excluded_domains` join the global exact-request
cache. Under OME-712 both bypassed, because the dispatched envelope's
`exclude_domains` was the UNION of the caller's list and a DEPLOYMENT setting
(`AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS`) the cache key could never see — two
deployments would agree on a key while dispatching different calls (ruling 34).

STORY: as a benchmark operator, I re-run the same `web_search` request and it is
served from the shared cache exactly like any other keyed OpenRouter parameter,
because the deployment input that made it unsafe to key is gone (OME-781/D2): the
envelope is now a pure function of the two caller fields alone.

INVARIANT under test: two deployments with DIFFERENT settings objects agree on the
SAME key for one body — the direct proof that no deployment input can reach the key
any more, since there is no longer a deployment input to smuggle.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from aigateway.core.cache_ports import CacheBypass
from aigateway.core.parameter_projection import IncompatibleParametersError
from aigateway.core.request_cache.global_keys import build_global_cache_key
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings
from aigateway.plugins.openrouter_provider.web_search import apply_web_search

_MODEL = "openrouter/anthropic/claude-fable-5"
_MESSAGES: list[Any] = [{"role": "user", "content": "what happened today?"}]


def _plugin(**settings: Any) -> OpenRouterProviderPlugin:
    return OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=True, **settings))


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"model": _MODEL, "messages": [dict(m) for m in _MESSAGES]}
    body.update(overrides)
    return body


def _built(plugin: OpenRouterProviderPlugin | None = None, **overrides: Any) -> Any:
    plugin = plugin or _plugin()
    return build_global_cache_key(
        provider="openrouter",
        body=_body(**overrides),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )


def test_a_web_search_request_is_keyed() -> None:
    """`web_search: True` now produces a key, not a bypass.

    Was the whole point of the OME-712 bypass: a search request could never enter
    the cache. With the deployment blocklist deleted the envelope is a pure
    function of the body, so it must key like every other output-affecting field.
    """
    built = _built(web_search=True)
    assert not isinstance(built, CacheBypass), built
    assert built.key_hash


def test_two_deployments_agree_on_the_key_for_one_body() -> None:
    """THE proof D2 worked: with no deployment input left, deployment identity
    cannot reach the key.

    Inverse of the deleted smuggle test
    (`test_the_deployment_blocklist_cannot_smuggle_itself_into_a_key`), which
    proved two deployments could NOT share a key while a deployment setting still
    shaped the dispatched envelope. That setting is gone, so the same two
    deployments must now agree.
    """
    plugin_a = _plugin()
    plugin_b = OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=True))
    built_a = _built(plugin_a, web_search=True)
    built_b = _built(plugin_b, web_search=True)
    assert not isinstance(built_a, CacheBypass), built_a
    assert not isinstance(built_b, CacheBypass), built_b
    assert built_a.key_hash == built_b.key_hash


def test_different_excluded_domains_produce_different_keys() -> None:
    first = _built(web_search=True, web_search_excluded_domains=["a.test"])
    second = _built(web_search=True, web_search_excluded_domains=["b.test"])
    assert not isinstance(first, CacheBypass), first
    assert not isinstance(second, CacheBypass), second
    assert first.key_hash != second.key_hash


def test_web_search_false_and_omitted_dispatch_the_same_call_under_two_keys() -> None:
    """`web_search: False` and the field omitted dispatch the SAME upstream call, under
    DIFFERENT keys — a duplicate entry, never a wrong hit.

    An earlier draft of this test asserted the two keys were EQUAL. They cannot be:
    `web_search` is kept `direct_rule` (OME-781/D2 — `provider_native_rule` is illegal
    for a top-level path), and `direct_rule`'s keying hashes the caller's raw value
    verbatim with no falsy-omission normalization, so an explicit `False` and an
    absent field necessarily land in different `keyed_parameters`. What this test pins
    instead is the ACCEPTED shape of that gap: the two requests are byte-identical on
    the wire (no `plugins` envelope either way) but occupy two cache entries — the
    same trade already documented for `reasoning_effort="none"` vs omitted in
    `anthropic_provider/plugin.py::global_cache_projection`, which is a lost dedupe
    opportunity, not a correctness defect.

    AIDEV-NOTE: collapsing the two keys would require falsy-omission semantics in the
    shared `direct_rule`/`_accept` path (`core/request_cache/global_eligibility.py`) —
    a core change touching every provider for a marginal dedupe, deliberately declined
    in OME-781.
    """
    out_false: dict[str, Any] = dict(_body(web_search=False))
    out_omitted: dict[str, Any] = dict(_body())
    apply_web_search(out_false)
    apply_web_search(out_omitted)
    assert "plugins" not in out_false
    assert "plugins" not in out_omitted
    assert out_false == out_omitted

    with_false = _built(web_search=False)
    omitted = _built()
    assert not isinstance(with_false, CacheBypass), with_false
    assert not isinstance(omitted, CacheBypass), omitted
    assert with_false.key_hash != omitted.key_hash


def test_the_envelope_is_a_pure_function_of_the_body() -> None:
    """`apply_web_search` needs no settings input and is deterministic over the body.

    INVARIANT (OME-781): the function must never regain a non-body input without
    re-opening this decision. Inspecting the signature is the tripwire — a settings
    parameter creeping back in would pass every value-level assertion here while
    silently reopening the smuggle hazard.
    """
    signature = inspect.signature(apply_web_search)
    assert list(signature.parameters) == ["body"]

    first = {"model": _MODEL, "web_search": True, "web_search_excluded_domains": ["a.test"]}
    second = dict(first)
    apply_web_search(first)
    apply_web_search(second)
    assert first["plugins"] == second["plugins"]
    assert first == second


def test_exclusions_without_web_search_are_still_rejected() -> None:
    """The existing guard in `plugin.py` is unaffected by this change."""
    plugin = _plugin()
    with pytest.raises(
        IncompatibleParametersError,
        match="web_search_excluded_domains_requires_web_search_true",
    ):
        plugin.validate_chat_parameter_combination(
            {"web_search_excluded_domains": ["a.test"]},
            model=_MODEL,
            auth_mode="api_key",
        )
