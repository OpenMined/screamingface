"""OME-305 U3 — OpenRouter's own projection for the global exact-request cache.

FEATURE: a globally shared exact-request cache that OpenRouter requests can
actually enter. Under v1 they could not: ``prepare_chat_body`` pins an API base
and rebuilds the ``provider`` object, and a key builder that INSPECTS the prepared
body cannot tell a reviewed rewrite from an unreviewed one, so every OpenRouter
call bypassed. The provider now PROJECTS its preparation instead — a pure function
of the request body — and the fingerprint is computed from what will be sent.

STORY: as a benchmark operator I run the same OpenRouter suite from a second
account and the identical calls are answered from the first run's stored
responses, without a second dispatch and without touching the second account's
key.

INVARIANT under test: the projection is PURE and TOTAL. No I/O, no credential, no
identity, no clock; it never mutates the caller's body; and a request this plugin
would refuse to dispatch yields a bounded ``CacheBypass`` rather than the
exception ``prepare_chat_body`` raises — the cache may never fail a request.

INVARIANT under test (the reason the projection calls the real reconstruction):
one upstream routing policy is ONE cache entry. Three spellings of a price
ceiling, and a ``zdr`` flag whose ``false`` is sent as nothing at all, canonicalize
to the same policy — so they must canonicalize to the same projection. Splitting
them would silently cost the hit rate this ticket exists to create, while the
inverse — two genuinely different policies sharing an entry — would serve a
response produced under a ceiling or data policy the caller did not ask for.

AIDEV-NOTE: two layers of pin live here, deliberately. The PROJECTION-level ones
hold whatever ``cache_behavior`` the five OME-704 rules declare, so they survived
the promotion of those rules to ``keyed`` unchanged. The KEY-level section at the
end is what the promotion itself owes (plan §10: a provider parameter may not
become keyed without a key-difference test) — it proves the equivalences reach the
HASH, which is the only place they protect a caller.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi import HTTPException

from aigateway.core.cache_ports import PROJECTION_BYPASS_REASON, CacheBypass
from aigateway.core.parameter_projection import (
    WRAPPER_KEY,
    classify_and_project_chat_parameters,
)
from aigateway.core.request_cache.global_controls import GlobalCacheControls
from aigateway.core.request_cache.global_keys import (
    build_global_cache_key,
    build_global_cache_key_dto,
    canonical_key_material,
)
from aigateway.core.request_cache.global_plan import build_global_cache_plan
from aigateway.plugins.openrouter_provider.plugin import (
    GLOBAL_CACHE_ADAPTER_REVISION,
    OFFICIAL_API_BASE,
    OpenRouterProviderPlugin,
)
from aigateway.plugins.openrouter_provider.routing_policy import (
    ROUTING_CONTROLS,
    STRICT_ROUTING_KEY,
)
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_MODEL = "openrouter/anthropic/claude-fable-5"
_UPSTREAM = "anthropic/claude-fable-5"
_MESSAGES: list[Any] = [{"role": "user", "content": "hi"}]

# Spelled out rather than imported: a rename of the production constant must not be
# able to silently rename what the gateway forces onto every routing policy.
_STRICT = {"require_parameters": True}


def _plugin() -> OpenRouterProviderPlugin:
    return OpenRouterProviderPlugin()


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"model": _MODEL, "messages": [dict(m) for m in _MESSAGES]}
    body.update(overrides)
    return body


def _projected(**overrides: Any) -> dict[str, Any]:
    produced = _plugin().global_cache_projection(_body(**overrides))
    assert not isinstance(produced, CacheBypass), produced
    return produced


def _policy(**overrides: Any) -> Any:
    return _projected(**overrides)["prepared"]["provider"]


def _reason(**overrides: Any) -> str:
    produced = _plugin().global_cache_projection(_body(**overrides))
    assert isinstance(produced, CacheBypass), produced
    return produced.reason


# --- the projected shape ------------------------------------------------------


def test_a_bare_request_projects_the_pinned_base_and_the_strict_policy() -> None:
    # The two output-affecting things this boundary adds on its own. Attribution
    # headers and the injected key are transport and deliberately absent.
    assert _projected() == {
        "resolved_model": _UPSTREAM,
        "provider_adapter_revision": GLOBAL_CACHE_ADAPTER_REVISION,
        "prepared": {"api_base": OFFICIAL_API_BASE, "provider": dict(_STRICT)},
    }


def test_the_projected_model_is_the_upstream_remainder() -> None:
    # D8: the gateway prefix IS LiteLLM's provider prefix and is stripped exactly
    # once at the wire, so the upstream id is what OpenRouter resolves.
    assert _projected()["resolved_model"] == _UPSTREAM
    assert not _projected()["resolved_model"].startswith("openrouter/")


def test_the_projection_is_deterministic_and_leaves_the_body_untouched() -> None:
    body = _body(provider_params={"sort": "price"})
    snapshot = copy.deepcopy(body)
    plugin = _plugin()
    assert plugin.global_cache_projection(body) == plugin.global_cache_projection(body)
    assert body == snapshot


def test_a_fresh_policy_object_is_returned_each_call() -> None:
    # A shared object would let one request's mutation become the next one's key.
    first = _policy(provider_params={"sort": "price"})
    first["sort"] = "tampered"
    assert _policy(provider_params={"sort": "price"})["sort"] == "price"


# --- strictness is unconditional ----------------------------------------------


def test_require_parameters_is_in_every_projected_policy() -> None:
    # OME-651: there is no caller-dependent path that omits it, so it is part of
    # every fingerprint — a stored response was produced under strict routing.
    for overrides in (
        {},
        {"provider_params": {"sort": "price"}},
        {"provider_params": {"zdr": True}},
        {"provider_params": {"max_price_prompt": "1", "data_collection": "deny"}},
    ):
        assert _policy(**overrides)[STRICT_ROUTING_KEY] is True, overrides


# --- one upstream policy is one entry (plan §2.6) -----------------------------


@pytest.mark.parametrize("spelling", ["1", "1.0", "1.000"])
def test_every_spelling_of_one_price_ceiling_projects_to_one_policy(spelling: str) -> None:
    # The gateway canonicalizes a validated decimal string before it goes upstream,
    # so these are one ceiling — and must be one cache entry, not three.
    assert _policy(provider_params={"max_price_prompt": spelling}) == {
        "max_price": {"prompt": "1"},
        **_STRICT,
    }


def test_a_different_ceiling_is_a_different_policy() -> None:
    assert _policy(provider_params={"max_price_prompt": "1"}) != _policy(
        provider_params={"max_price_prompt": "2"}
    )


def test_the_two_price_ceilings_are_addressed_independently() -> None:
    assert _policy(provider_params={"max_price_prompt": "1"}) != _policy(
        provider_params={"max_price_completion": "1"}
    )


def test_a_false_zdr_flag_projects_exactly_like_omitting_it() -> None:
    # ``false`` and absence mean the same thing upstream, so the honest encoding of
    # "I have no constraint" is to send nothing — and the two requests are the same
    # request.
    assert _policy(provider_params={"zdr": False}) == _policy()


def test_a_true_zdr_flag_is_a_distinct_policy() -> None:
    assert _policy(provider_params={"zdr": True}) == {"zdr": True, **_STRICT}
    assert _policy(provider_params={"zdr": True}) != _policy()


def test_each_reviewed_control_reaches_its_documented_location() -> None:
    assert _policy(provider_params={"sort": "price"}) == {"sort": "price", **_STRICT}
    assert _policy(provider_params={"data_collection": "deny"}) == {
        "data_collection": "deny",
        **_STRICT,
    }
    assert _policy(provider_params={"max_price_completion": "0.5"}) == {
        "max_price": {"completion": "0.5"},
        **_STRICT,
    }


# --- what the projection refuses to describe ----------------------------------


def test_a_wrapper_leaf_that_is_not_a_routing_control_is_not_projected() -> None:
    # ``provider_params.top_k`` targets ``extra_body``, not the routing policy. The
    # projection describes only what it owns; the key builder is what decides
    # whether an undescribed keyed path may participate.
    assert _policy(provider_params={"top_k": 3}) == dict(_STRICT)


@pytest.mark.parametrize(
    "wrapper",
    [
        {"allow_fallbacks": True},  # the excluded control plane
        {"order": ["openai"]},  # provider selection the gateway owns
        {"max_price": {"prompt": "1"}},  # the upstream spelling is not a caller path
        {"nonesuch": 1},
    ],
)
def test_an_unruled_wrapper_leaf_makes_the_whole_request_uncacheable(wrapper: Any) -> None:
    """The refusal these need lives in the KEY BUILDER, not in the projection.

    A leaf with no rule is a 400 on dispatch, so it may never be silently dropped
    from a fingerprint — but the projection is not where that is decided: it
    describes only the surface it owns, and describing an unruled leaf is exactly
    what it must not do. The two halves together are what closes the door.
    """
    plugin = _plugin()
    built = build_global_cache_key(
        provider="openrouter",
        body=_body(provider_params=wrapper),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )
    assert isinstance(built, CacheBypass), built
    assert built.reason == "unknown_parameter"


def test_a_bare_openrouter_request_is_cacheable_end_to_end() -> None:
    # The property v1 could never have: a request to a provider that rewrites the
    # body gets a global key, because the rewrite is PROJECTED rather than inspected.
    plugin = _plugin()
    built = build_global_cache_key(
        provider="openrouter",
        body=_body(),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )
    assert not isinstance(built, CacheBypass), built
    assert len(built.key_hash) == 64


@pytest.mark.parametrize(
    "wrapper",
    [
        {"sort": "throughput"},  # the excluded ordering (OME-703 owns provider selection)
        {"max_price_prompt": "abc"},  # not a decimal
        {"max_price_prompt": "-1"},  # a ceiling that is not a ceiling
        {"max_price_prompt": " 1"},  # invisible in a diff and in a log
        {"zdr": "true"},  # a string is not a boolean
        {"data_collection": "maybe"},  # outside the reviewed enum
    ],
)
def test_a_value_the_gateway_would_refuse_to_reconstruct_bypasses(wrapper: Any) -> None:
    # INVARIANT (ledger decision 12): a request whose policy cannot be rebuilt 503s
    # on dispatch. Moving the cache read ahead of preparation must never turn one
    # into a 200 hit, so the projection bypasses instead of describing it.
    assert _reason(provider_params=wrapper) == PROJECTION_BYPASS_REASON


def test_a_malformed_wrapper_bypasses() -> None:
    assert _reason(provider_params="nope") == PROJECTION_BYPASS_REASON
    assert _reason(provider_params=["sort"]) == PROJECTION_BYPASS_REASON


@pytest.mark.parametrize(
    "model",
    [
        "anthropic/claude-fable-5",  # no gateway prefix
        "openrouter/claude-fable-5",  # no author segment
        "openrouter/",  # nothing upstream
        "openai/gpt-5",  # another provider's prefix
        "",
        None,
        7,
    ],
)
def test_a_model_this_plugin_would_not_dispatch_bypasses_instead_of_raising(model: Any) -> None:
    # ``prepare_chat_body`` raises a 400 for exactly these. A projection may not
    # fail a request, so the same judgement is reported as a bypass.
    plugin = _plugin()
    body = _body(model=model)
    assert isinstance(plugin.global_cache_projection(body), CacheBypass)
    with pytest.raises(HTTPException) as raised:
        plugin.prepare_chat_body(dict(body))
    assert raised.value.status_code == 400


def test_a_caller_supplied_provider_object_is_never_projected() -> None:
    # INVARIANT: raw ``provider`` is not a caller request path. The classifier
    # refuses it, and the projection reads only the wrapper — so a caller cannot
    # reach the routing control plane through the fingerprint either.
    assert _policy(provider={"order": ["openai"], "allow_fallbacks": True}) == dict(_STRICT)


# --- the promotion to `keyed`: the same pins, at the HASH ----------------------
#
# Plan §10 stop condition: "a provider parameter becomes keyed without a
# key-difference test". Everything above proves the PROJECTION canonicalizes
# correctly; a projection can be perfect while the value never reaches the key at
# all — which is exactly what a `bypass` rule does, and exactly what these catch.


def _key(**overrides: Any) -> str:
    plugin = _plugin()
    built = build_global_cache_key(
        provider="openrouter",
        body=_body(**overrides),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )
    assert not isinstance(built, CacheBypass), built
    return built.key_hash


def test_a_routing_controlled_request_is_keyed_rather_than_bypassed() -> None:
    # The half the promotion delivers: a request CARRYING a control gets a key at all.
    # While the rules declared `bypass` this returned a CacheBypass, so `_key`'s own
    # assertion is the test.
    assert len(_key(provider_params={"sort": "price"})) == 64


def test_the_same_routing_controlled_request_repeats_to_the_same_key() -> None:
    # A keyed HIT on repeat — the hit rate this promotion exists to create.
    controls = {"max_price_prompt": "1", "data_collection": "deny"}
    assert _key(provider_params=dict(controls)) == _key(provider_params=dict(controls))


def test_a_routing_control_changes_the_key_at_all() -> None:
    # Guards against the control being accepted and then silently excluded — the
    # under-keying failure that would share one entry across two policies.
    assert _key(provider_params={"sort": "price"}) != _key()


@pytest.mark.parametrize(
    ("leaf", "first", "second"),
    [
        ("max_price_prompt", "1", "2"),
        ("max_price_completion", "0.5", "0.75"),
        ("data_collection", "deny", "allow"),
        ("zdr", True, False),
    ],
)
def test_two_requests_differing_only_in_one_control_never_cross_hit(
    leaf: str, first: Any, second: Any
) -> None:
    # THE privacy/correctness test for this promotion. A different price ceiling or a
    # different data policy is a different request, and serving one from the other's
    # entry is a correctness bug for price and a privacy bug for data policy.
    #
    # AIDEV-NOTE: `sort` is absent from this table because its reviewed enum admits
    # exactly one value (`("price",)`), so two distinct VALID values cannot be
    # constructed for it. Its key difference is presence-vs-absence and is covered by
    # test_a_routing_control_changes_the_key_at_all. Widen the enum and add a row here.
    assert _key(provider_params={leaf: first}) != _key(provider_params={leaf: second})


def test_every_reviewed_control_is_covered_by_a_key_difference_test() -> None:
    """Guards the table above against a control being promoted and never pinned.

    AIDEV-NOTE: plan §10 forbids a parameter becoming keyed without a key-difference
    test, and a hand-written parametrize table cannot notice a SIXTH control being
    added to ``ROUTING_CONTROLS``. This asserts the reviewed surface is exactly what
    the tests above exercise, so adding a control without pinning it fails here.
    """
    covered = {"max_price_prompt", "max_price_completion", "data_collection", "zdr"}
    # `sort` is pinned by presence-vs-absence rather than by two values — see above.
    assert {control.leaf for control in ROUTING_CONTROLS} == covered | {"sort"}


@pytest.mark.parametrize(
    ("path", "first", "second"),
    [
        ("seed", 1, 2),
        ("response_format", {"type": "text"}, {"type": "json_object"}),
        ("n", 1, 2),
        ("logprobs", False, True),
        ("top_logprobs", 1, 2),
        ("stop", ["alpha"], ["beta"]),
        ("max_tokens", 32, 64),
        ("temperature", 0.2, 0.8),
        ("frequency_penalty", 0.1, 0.2),
        ("presence_penalty", 0.1, 0.2),
        (
            "tools",
            [{"type": "function", "function": {"name": "a"}}],
            [{"type": "function", "function": {"name": "b"}}],
        ),
        (
            "tool_choice",
            "auto",
            {"type": "function", "function": {"name": "f"}},
        ),
    ],
)
def test_two_openrouter_requests_differing_only_in_one_keyed_value_never_share_a_key(
    path: str, first: Any, second: Any
) -> None:
    assert _key(**{path: first}) != _key(**{path: second})


def test_every_openrouter_keyed_path_has_an_explicit_key_difference_proof() -> None:
    """Ruling 7: the tables in this module account for every keyed path."""
    plugin = _plugin()
    keyed = {
        rule.request_path
        for rule in plugin.chat_parameter_rules(model=_MODEL, auth_type=None)
        if rule.cache_behavior == "keyed"
    }
    covered_by_two_values = {
        "seed",
        "response_format",
        "n",
        "logprobs",
        "top_logprobs",
        "stop",
        "max_tokens",
        "temperature",
        "frequency_penalty",
        "presence_penalty",
        "top_p",
        "provider_params.max_price_prompt",
        "provider_params.max_price_completion",
        "provider_params.data_collection",
        "provider_params.zdr",
        "provider_params.top_k",
        # OME-787: OpenRouter is the first provider opted into keyed tools/tool_choice
        # (it has a real ``global_cache_projection`` to back them) — pinned by the two
        # rows above, same as every other direct-keyed path.
        "tools",
        "tool_choice",
    }
    # `sort` has one valid value and is pinned by presence versus absence above.
    assert keyed == covered_by_two_values | {"provider_params.sort"}


def test_the_two_price_ceilings_are_keyed_independently() -> None:
    # A ceiling on the prompt is not a ceiling on the completion; collapsing them
    # would serve a completion-capped answer to a prompt-capped request.
    assert _key(provider_params={"max_price_prompt": "1"}) != _key(
        provider_params={"max_price_completion": "1"}
    )


@pytest.mark.parametrize("spelling", ["1", "1.0", "1.000"])
def test_every_spelling_of_one_price_ceiling_shares_one_key(spelling: str) -> None:
    # Plan §2.6 at the hash: "1" == "1.0" == "1.000". These are ONE upstream ceiling,
    # so they must be one entry — three would be a silent 3x loss of hit rate.
    #
    # WHY this can only work through the reconstructed policy: `normalize_price`
    # collapses the spellings on the way to the wire, so hashing the caller's raw leaf
    # could never make them agree.
    assert _key(provider_params={"max_price_prompt": spelling}) == _key(
        provider_params={"max_price_prompt": "1"}
    )


def test_a_false_zdr_flag_keys_exactly_like_omitting_it() -> None:
    # Plan §2.6: `zdr` omitted == `zdr: false`. The gateway sends NOTHING for a false
    # flag, so the two requests are byte-identical upstream and must be one entry.
    assert _key(provider_params={"zdr": False}) == _key()


def test_a_true_zdr_flag_is_a_distinct_key() -> None:
    # The inverse, and the one that matters for privacy: a zero-data-retention
    # request must never be answered from an entry filled without that restriction.
    true_key = _key(provider_params={"zdr": True})
    assert true_key != _key()
    assert true_key != _key(provider_params={"zdr": False})


def test_the_strict_routing_policy_participates_in_every_key() -> None:
    # OME-651's `require_parameters` is forced onto every dispatch, so every stored
    # response was produced under strict routing. It reaches the key through
    # `prepared_request`, which is what makes that a property of the ENTRY and not
    # merely of the dispatch.
    plugin = _plugin()
    dto = build_global_cache_key_dto(
        provider="openrouter",
        body=_body(),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )
    assert not isinstance(dto, CacheBypass), dto
    assert dto.prepared_request["provider"] == dict(_STRICT)
    assert WRAPPER_KEY not in canonical_key_material(dto)


def test_the_callers_raw_spelling_never_appears_in_the_key_material() -> None:
    # The design this promotion rests on: what participates is the RECONSTRUCTED
    # policy, not the caller's wrapper. A caller leaf name leaking into the hashed
    # material would mean the spelling was being keyed after all, and the §2.6
    # equivalences above would be accidental rather than structural.
    plugin = _plugin()
    dto = build_global_cache_key_dto(
        provider="openrouter",
        body=_body(provider_params={"max_price_prompt": "1.000"}),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )
    assert not isinstance(dto, CacheBypass), dto
    material = canonical_key_material(dto)
    assert "max_price_prompt" not in material
    assert "1.000" not in material
    # ...while the canonical upstream form IS there.
    assert dto.prepared_request["provider"]["max_price"] == {"prompt": "1"}


# --- the operator gate decides PARTICIPATION, not KEY MATERIAL (review MEDIUM-1) --


def _disabled_plugin() -> OpenRouterProviderPlugin:
    return OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=False))


def _enabled_plugin() -> OpenRouterProviderPlugin:
    # WHY spelled out here and NOT folded into `_plugin()`: `enabled` ships FALSE, so
    # the two arrangements differ — but only for PARTICIPATION. Every projection
    # assertion above deliberately keeps using the default-constructed plugin, because
    # the projection is contractually blind to this setting and those tests are the
    # place that stays true whichever way the switch is thrown.
    return OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=True))


def test_a_disabled_provider_declines_to_participate_in_the_shared_cache() -> None:
    # INVARIANT: a provider kill switch must reach the CACHE path, not only the
    # dispatch path. `register_models` returns nothing and `api_key_strategy_for`
    # returns None when disabled — but a STORED ROW needs neither a model entry nor a
    # credential to be replayed, and the cache stage runs ahead of both checks.
    assert _disabled_plugin().participates_in_global_cache() is False
    assert _enabled_plugin().participates_in_global_cache() is True


def test_the_gate_changes_participation_without_touching_key_material() -> None:
    # WHY both halves in one test: they are the two directions of the same ruling —
    # settings may gate participation, never shape the key. If the gate also changed
    # the key, flipping the switch would abandon every stored row: a silent cache
    # flush dressed up as a bug fix.
    #
    # The projection is therefore asserted to be BLIND to the setting. That is also
    # its port contract (it reads the body alone), enforced globally by
    # `tests/unit/test_global_cache_projection_purity.py`; this is the
    # OpenRouter-specific statement of the same property, at the value level.
    expected = {
        "resolved_model": _UPSTREAM,
        "provider_adapter_revision": GLOBAL_CACHE_ADAPTER_REVISION,
        "prepared": {"api_base": OFFICIAL_API_BASE, "provider": dict(_STRICT)},
    }
    assert _projected() == expected
    assert _disabled_plugin().global_cache_projection(_body()) == expected


def test_a_disabled_provider_yields_a_plan_that_does_not_participate() -> None:
    # The layer that actually enforces the gate: participation is refused in the PLAN,
    # which is where a settings read is legitimate. Asserted here rather than only at
    # the route so the property is pinned without a database, a profile or a
    # credential — and so a future refactor that drops the plan's call to the hook
    # fails a unit test rather than only an end-to-end one.
    def _plan(plugin: OpenRouterProviderPlugin):
        return build_global_cache_plan(
            body=_body(),
            plugin=plugin,
            controls=GlobalCacheControls(participate=True, bypass_reason=""),
            cache_enabled=True,
        )

    refused = _plan(_disabled_plugin())
    assert isinstance(refused, CacheBypass)
    assert refused.reason == PROJECTION_BYPASS_REASON
    # Non-vacuous: the SAME request under an enabled provider does participate, so the
    # refusal is owed to the gate and not to the request being unkeyable.
    assert not isinstance(_plan(_enabled_plugin()), CacheBypass)


# --- the declared `top_k` leaf is really projected (OME-305 review, MEDIUM-2) ---


def test_a_top_k_request_projects_the_exact_leaf_its_own_rule_targets() -> None:
    # The rule publishes `provider_params.top_k -> extra_body.top_k` as `keyed`, and
    # a native value participates in the key ONLY through `prepared`. So the leaf
    # itself must be here: satisfying the key builder's ROOT check with an empty
    # `extra_body` would pass that check while silently dropping the value from the
    # hash, which is the one failure a globally shared cache may never have.
    assert _projected(provider_params={"top_k": 3})["prepared"]["extra_body"] == {"top_k": 3}


def test_a_request_without_top_k_projects_no_extra_body_root_at_all() -> None:
    # BOUNDARY, and the reason the emission is conditional. The key builder's guard
    # is root-only: once `extra_body` is present, every rule targeting that root is
    # keyed on trust, and a leaf missing from it reads as a DELIBERATE omission
    # rather than an error. Emitting the root unconditionally would therefore turn a
    # future `extra_body.*` rule into a silent collision instead of a safe bypass.
    assert "extra_body" not in _projected()["prepared"]
    assert "extra_body" not in _projected(provider_params={"sort": "price"})["prepared"]


def test_two_top_k_values_never_share_a_key() -> None:
    plugin = _plugin()

    def _key(**overrides: Any) -> Any:
        return build_global_cache_key(
            provider="openrouter",
            body=_body(**overrides),
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
            projection=plugin.global_cache_projection,
            provider_auth_modes=plugin.available_auth_modes(),
        )

    three, seven = _key(provider_params={"top_k": 3}), _key(provider_params={"top_k": 7})
    # It must be keyed at all — the defect was a permanent `unprojected_parameter`.
    assert not isinstance(three, CacheBypass), three
    assert not isinstance(seven, CacheBypass), seven
    assert three.key_hash != seven.key_hash
    # ...and neither may collide with the bare request that asked for no top_k.
    bare = _key()
    assert not isinstance(bare, CacheBypass), bare
    assert three.key_hash != bare.key_hash


def test_the_projected_top_k_is_the_value_dispatch_will_actually_send() -> None:
    # The agreement that makes keying it sound. If the projection and the dispatch
    # path disagreed about the effective value, the key would describe a request the
    # provider never receives.
    plugin = _plugin()
    dispatched = classify_and_project_chat_parameters(
        _body(provider_params={"top_k": 3}),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    projected = _projected(provider_params={"top_k": 3})["prepared"]
    assert dispatched["extra_body"]["top_k"] == projected["extra_body"]["top_k"]
