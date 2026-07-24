"""Phase 8 (OME-479 §4.4/§6.3): Anthropic detail-contract overlay + auth-split summary.

FEATURE: Anthropic P1 observation overlay — the detailed /v1/model-parameters document
AND the profile-independent /v1/models summary, each derived SEPARATELY per auth mode
from ONE provider-local source (the plan's Phase 8 steps 1/2/5).

STORY: as an API consumer on an api-key connection I can see Anthropic accepts native
top_k and the gateway will project it; on an OAuth (Claude Code subscription) connection
the SAME field is visible-but-disabled — the contract tells me exactly what each
credential may send, without ever sending credentials to a discovery endpoint (§6.3).

INVARIANT (§4.4): an observation NEVER enables a field; only a rule does — ``stop`` now
has a rule (OME-582), so it is ENABLED under every auth mode while still carrying its
observation's provenance.
INVARIANT (§6.3): a field enabled for API key only is DROPPED from the conservative
/v1/models intersection — the summary never overclaims what OAuth cannot prove, even
though the api-key DETAIL contract lists it enabled.
INVARIANT: NO network — the detail endpoint composes from labelled-static evidence.
"""

from __future__ import annotations

from typing import Any

from aigateway.core.chat_parameters import inline_supported_parameters
from aigateway.core.model_parameter_contract import build_model_parameter_document
from aigateway.core.profile_models import AuthType
from aigateway.plugins.anthropic_provider.plugin import AnthropicProviderPlugin

_MODEL = "anthropic/claude-haiku-4-5"
_STATIC = "anthropic:static"


def _parameters(auth_mode: AuthType) -> dict[str, Any]:
    # Mirrors routes/model_parameters.py: the SAME plugin hooks, the SAME composer —
    # only the profile resolution (auth_mode) is supplied directly.
    plugin = AnthropicProviderPlugin()
    document = build_model_parameter_document(
        canonical_id=_MODEL,
        gateway_provider="anthropic",
        auth_mode=auth_mode,
        scope="account_profile",
        context_identity="acct:test|prof:1",
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=auth_mode),
        observations=plugin.chat_parameter_observations(model=_MODEL, auth_type=auth_mode),
        tools=plugin.chat_parameter_tools(model=_MODEL, auth_type=auth_mode),
        transport=plugin.chat_transport_capabilities(model=_MODEL, auth_type=auth_mode),
        freshness={"stale": False, "degraded": False},
    )
    return document["parameters"]


def test_ruled_and_observed_standard_fields_are_enabled_with_evidence() -> None:
    # both auth modes: the standard sampling/generation fields are ruled AND observed
    # → ENABLED carrying the observation's provenance (not "unknown"/"none").
    for auth_mode in ("api_key", "oauth"):
        params = _parameters(auth_mode)
        for path in ("temperature", "top_p", "max_tokens", "reasoning_effort"):
            entry = params[path]
            assert entry["gateway"]["status"] == "enabled", (auth_mode, path)
            assert entry["provider"]["support"] == "supported", (auth_mode, path)
            assert entry["provider"]["source"] == _STATIC, (auth_mode, path)


def test_stop_is_enabled_under_both_modes() -> None:
    # OME-582: `stop` is now RULED (union string | array[string]); it reaches the
    # installed AnthropicConfig transform as stop_sequences, so it is ENABLED under both
    # auth modes while keeping the observation's provenance.
    for auth_mode in ("api_key", "oauth"):
        entry = _parameters(auth_mode)["stop"]
        assert entry["provider"]["support"] == "supported", auth_mode
        assert entry["provider"]["source"] == _STATIC, auth_mode
        assert entry["gateway"]["status"] == "enabled", auth_mode


def test_native_top_k_is_enabled_under_api_key_with_evidence() -> None:
    entry = _parameters("api_key")["provider_params.top_k"]
    assert entry["gateway"]["status"] == "enabled"
    assert entry["provider"]["support"] == "supported"
    assert entry["provider"]["source"] == _STATIC


def test_native_top_k_is_visible_but_disabled_under_oauth() -> None:
    # §6.3: under OAuth the api-key-only rule does not apply, so the SAME observed
    # native field surfaces visible-but-DISABLED — honest, not absent, not enabled.
    entry = _parameters("oauth")["provider_params.top_k"]
    assert entry["provider"]["support"] == "supported"
    assert entry["provider"]["source"] == _STATIC
    assert entry["gateway"]["status"] == "disabled"
    assert entry["gateway"]["reason"] == "projection_not_implemented"


def test_inline_summary_is_the_safe_auth_intersection() -> None:
    # step 5: the /v1/models summary contains only fields enabled under EVERY available
    # auth mode. top_k (api-key-only) is DROPPED; stop (ruled under both modes) is kept.
    plugin = AnthropicProviderPlugin()
    rules = plugin.chat_parameter_rules(model=_MODEL, auth_type=None)
    summary = inline_supported_parameters(rules, available_auth_modes=("api_key", "oauth"))
    assert {"temperature", "top_p", "max_tokens", "reasoning_effort"} <= set(summary)
    assert "provider_params.top_k" not in summary  # api-key-only → dropped
    assert "stop" in summary  # OME-582: now ruled + enabled under both modes


def test_api_key_detail_contract_includes_top_k_that_summary_omits() -> None:
    # the §6.3 signature behavior: a field ENABLED in the api-key DETAIL contract yet
    # ABSENT from the conservative summary — detail and summary agree at different scopes.
    api_key_enabled = {
        path
        for path, entry in _parameters("api_key").items()
        if entry["gateway"]["status"] == "enabled"
    }
    plugin = AnthropicProviderPlugin()
    summary = set(
        inline_supported_parameters(
            plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
            available_auth_modes=("api_key", "oauth"),
        )
    )
    assert "provider_params.top_k" in api_key_enabled
    assert "provider_params.top_k" not in summary


def test_sources_are_labelled_static_or_rule_only() -> None:
    # every observation is labelled-local static evidence; none claims a live fetch or
    # a fabricated per-model truth. Rule-only fields (no observation) read "none".
    for auth_mode in ("api_key", "oauth"):
        params = _parameters(auth_mode)
        sources = {entry["provider"]["source"] for entry in params.values()}
        assert sources <= {_STATIC, "none"}, (auth_mode, sources)


def test_every_observed_field_is_visible_with_a_status() -> None:
    # "expose ALL provider params": each labelled-static field is visible under api_key
    # with a status — nothing the transform accepts silently vanishes.
    params = _parameters("api_key")
    for path in (
        "temperature",
        "top_p",
        "max_tokens",
        "reasoning_effort",
        "stop",
        "provider_params.top_k",
    ):
        assert path in params, path
