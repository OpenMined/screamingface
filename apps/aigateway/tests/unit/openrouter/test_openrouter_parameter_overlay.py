"""Phase 6c (OME-479 §4.4/§6.1): OpenRouter detail-contract observation overlay.

FEATURE: OpenRouter P0 observation overlay — the detailed /v1/model-parameters
document. Proves the composition the route performs (build_model_parameter_
document over the plugin's OWN rules + observations) surfaces EVERY endpoint-
accepted field with an honest gateway status, from labelled-local evidence and
with NO network.

STORY: as an API consumer, I can see that OpenRouter accepts top_p even though the
gateway does not yet project it (visible-but-DISABLED), while temperature and the
promoted provider_params.top_k are ENABLED — so I know exactly what I may send.

INVARIANT (§4.4): an observation NEVER enables a field; only a rule does. An
observed-but-unruled field stays visible-but-rejected (projection_not_implemented).
INVARIANT: no network — the detail endpoint composes from labelled-local evidence.
"""

from __future__ import annotations

from typing import Any

from aigateway.core.model_parameter_contract import build_model_parameter_document
from aigateway.core.profile_models import AuthType
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin

_MODEL = "openrouter/google/gemini-2.0-flash-001"


def _parameters(auth_mode: AuthType = "api_key") -> dict[str, Any]:
    # Mirrors routes/model_parameters.py verbatim: the SAME plugin hooks, the SAME
    # composer — only the profile resolution (auth_mode) is supplied directly.
    plugin = OpenRouterProviderPlugin()
    document = build_model_parameter_document(
        canonical_id=_MODEL,
        gateway_provider="openrouter",
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


def test_observed_but_unruled_field_is_visible_but_disabled() -> None:
    top_p = _parameters()["top_p"]
    # top_p is accepted by the endpoint (observed) but has NO gateway rule.
    assert top_p["provider"]["support"] == "supported"
    assert top_p["provider"]["source"] == "openrouter:static"
    assert top_p["gateway"]["status"] == "disabled"
    assert top_p["gateway"]["reason"] == "projection_not_implemented"


def test_promoted_native_param_is_enabled_at_wrapper_path() -> None:
    params = _parameters()
    # the P0 promotion: provider_params.top_k is observed AND ruled → ENABLED, and
    # the bare native name never appears as a parameter.
    assert "top_k" not in params
    top_k = params["provider_params.top_k"]
    assert top_k["gateway"]["status"] == "enabled"
    assert top_k["provider"]["support"] == "supported"
    assert top_k["provider"]["source"] == "openrouter:static"


def test_ruled_and_observed_standard_field_is_enabled_with_evidence() -> None:
    temperature = _parameters()["temperature"]
    assert temperature["gateway"]["status"] == "enabled"
    # carries the observation's evidence, not "unknown/none".
    assert temperature["provider"]["support"] == "supported"
    assert temperature["provider"]["source"] == "openrouter:static"


def test_ruled_but_unobserved_field_is_enabled_with_unknown_support() -> None:
    # `provider` is a ruled routing control, deliberately NOT in the sampling-param
    # evidence set — so it is enabled but honestly carries no provider evidence.
    provider = _parameters()["provider"]
    assert provider["gateway"]["status"] == "enabled"
    assert provider["provider"]["support"] == "unknown"
    assert provider["provider"]["source"] == "none"


def test_every_endpoint_observed_sampling_field_is_visible_with_a_status() -> None:
    params = _parameters()
    # "expose ALL provider params": each accepted sampling field is visible with a
    # status — enabled when ruled, disabled-but-visible otherwise.
    for path in (
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "seed",
        "stop",
        "provider_params.top_k",
    ):
        assert path in params, path
    # every unruled observed field is honest about WHY it is rejected.
    for path in ("top_p", "frequency_penalty", "presence_penalty", "seed", "stop"):
        assert params[path]["gateway"]["status"] == "disabled"
        assert params[path]["gateway"]["reason"] == "projection_not_implemented"


def test_observations_are_labelled_local_not_fabricated_per_model() -> None:
    # every observation surfaced here is labelled-local endpoint evidence; none
    # claims to be live per-model catalog evidence (that arrives via discovery).
    params = _parameters()
    sources = {p["provider"]["source"] for p in params.values()}
    # only labelled-local ("openrouter:static") or rule-only ("none") provenance;
    # never the live "openrouter:models" catalog label without a network fetch.
    assert sources <= {"openrouter:static", "none"}
