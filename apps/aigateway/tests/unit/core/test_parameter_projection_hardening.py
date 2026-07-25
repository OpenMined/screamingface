"""Phase 4 (OME-479): fail-closed chat-parameter classification + projection.

FEATURE: the effective parameter contract, dispatch side. The SAME provider
rule set that drives the ``/v1/models`` summary and the ``/v1/model-parameters``
detail decides here which caller-supplied optional parameters are dispatchable,
and projects each accepted value to its provider-body target.

RED-first for the PURE core primitive
``classify_and_project_chat_parameters(body, *, rules, auth_mode)``. No route,
no network, no provider names — fabricated rule sets exercise the algebra so the
mechanism is provider-agnostic (SOLID: a new parameter is one provider-local
rule, never an edit here).

INVARIANT under test: fail closed. Only an enabled rule matching the REAL auth
mode authorizes an optional parameter; unknown / wrong-auth / malformed /
duplicate-channel / non-object-wrapper values reject with HTTP-safe request
paths and never reach the projected dispatch body.
"""

from __future__ import annotations

import pytest

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    inline_supported_parameters,
)
from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.core.profile_models import AuthType

_INT = ParameterSchema(type="integer", minimum=1)
_NUM = ParameterSchema(type="number", minimum=0, maximum=2)


def _direct(
    path: str,
    *,
    auth: tuple[AuthType, ...] = ("api_key",),
    schema: ParameterSchema | None = None,
    target: str | None = None,
) -> ParameterProjectionRule:
    return ParameterProjectionRule(
        request_path=path,
        applicable_auth_modes=auth,
        projection_kind="direct",
        provider_target=target,
        cache_behavior="bypass",
        projection_revision="r1",
        schema=schema,
    )


def _native(
    path: str,
    target: str,
    *,
    auth: tuple[AuthType, ...] = ("api_key",),
    schema: ParameterSchema | None = None,
) -> ParameterProjectionRule:
    return ParameterProjectionRule(
        request_path=path,
        applicable_auth_modes=auth,
        projection_kind="provider_native",
        provider_target=target,
        cache_behavior="bypass",
        projection_revision="r1",
        schema=schema,
    )


def _classify(body, rules=(), auth_mode: AuthType = "api_key"):
    return classify_and_project_chat_parameters(body, rules=rules, auth_mode=auth_mode)


# --- required-protocol / gateway-owned / transport (tier a: no rule needed) ---


def test_gateway_owned_and_protocol_fields_pass_without_any_rule() -> None:
    # STORY: as a client I send the ordinary OpenAI envelope with no optional
    # params; it must dispatch even for a provider that declares no rules.
    body = {
        "model": "p/m",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "extra_headers": {"x-trace": "1"},
        "metadata": {"k": "v"},
        "timeout": 30,
    }
    out = _classify(body, rules=())
    assert out == body
    assert out is not body  # a fresh normalized body, never the caller's dict


def test_input_body_is_never_mutated() -> None:
    body = {"model": "p/m", "messages": [], "temperature": 0.5}
    _classify(body, rules=(_direct("temperature", schema=_NUM),))
    assert body == {"model": "p/m", "messages": [], "temperature": 0.5}


# --- enabled rules: direct + provider_native projection ----------------------


def test_enabled_direct_rule_validates_and_keeps_field_top_level() -> None:
    out = _classify(
        {"model": "p/m", "messages": [], "temperature": 0.25},
        rules=(_direct("temperature", schema=_NUM),),
    )
    assert out["temperature"] == 0.25


def test_provider_native_rule_projects_into_dotted_target_and_consumes_wrapper() -> None:
    # INVARIANT: provider_params is consumed key-by-key into the rule target and
    # NEVER splatted — a raw provider_params object can never reach a provider.
    out = _classify(
        {"model": "p/m", "messages": [], "provider_params": {"top_k": 40}},
        rules=(_native("provider_params.top_k", "extra_body.top_k", schema=_INT),),
    )
    assert out["extra_body"] == {"top_k": 40}
    assert "provider_params" not in out
    assert "top_k" not in out  # only under the projected target


def test_direct_rule_may_project_to_a_provider_target() -> None:
    out = _classify(
        {"model": "p/m", "messages": [], "route": "fallback"},
        rules=(_direct("route", target="extra_body.route"),),
    )
    assert out["extra_body"] == {"route": "fallback"}


def test_rule_without_schema_forwards_complex_value_unchanged() -> None:
    # OpenRouter-native routing objects have no scalar schema; a rule with no
    # schema authorizes the path and forwards the value verbatim.
    prefs = {"order": ["anthropic"], "allow_fallbacks": False}
    out = _classify(
        {"model": "p/m", "messages": [], "provider": prefs},
        rules=(_direct("provider"),),
    )
    assert out["provider"] == prefs


# --- fail-closed rejections (HTTP-safe paths, no raw values) ------------------


def test_unknown_top_level_optional_param_rejects() -> None:
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify({"model": "p/m", "messages": [], "banana": 1}, rules=())
    assert exc.value.rejected == {"banana": "unknown"}


def test_unknown_nested_provider_params_key_rejects_with_dotted_path() -> None:
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {"model": "p/m", "messages": [], "provider_params": {"mystery": 1}},
            rules=(_native("provider_params.top_k", "extra_body.top_k", schema=_INT),),
        )
    assert exc.value.rejected == {"provider_params.mystery": "unknown"}


def test_rule_for_a_different_auth_mode_is_wrong_auth_not_unknown() -> None:
    # A path the provider DOES own but only under another auth mode must be
    # distinguishable from a truly unknown path (fail closed either way).
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {"model": "p/m", "messages": [], "temperature": 0.5},
            rules=(_direct("temperature", auth=("oauth",), schema=_NUM),),
            auth_mode="api_key",
        )
    assert exc.value.rejected == {"temperature": "wrong_auth_mode"}


def test_malformed_value_rejects_against_gateway_schema() -> None:
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {"model": "p/m", "messages": [], "temperature": 9},
            rules=(_direct("temperature", schema=_NUM),),
        )
    assert exc.value.rejected == {"temperature": "malformed"}


def test_boolean_never_satisfies_a_numeric_schema() -> None:
    # WHY: bool is a subclass of int; temperature=true must reject, not slip
    # through as 1 (guarded in ParameterSchema.validate_value).
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {"model": "p/m", "messages": [], "temperature": True},
            rules=(_direct("temperature", schema=_NUM),),
        )
    assert exc.value.rejected == {"temperature": "malformed"}


def test_provider_params_must_be_an_object() -> None:
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {"model": "p/m", "messages": [], "provider_params": [1, 2, 3]},
            rules=(_native("provider_params.top_k", "extra_body.top_k", schema=_INT),),
        )
    assert exc.value.rejected == {"provider_params": "not_an_object"}


def test_duplicate_channel_to_the_same_target_rejects() -> None:
    # ONE legitimate rule reached via TWO caller encodings — the flat dot-key
    # top-level form and the nested provider_params wrapper — resolves to the SAME
    # provider target; supplying both is ambiguous and must reject rather than
    # silently drop one. This is the still-reachable duplicate_channel case.
    #
    # WHY (OME-597): two DISTINCT rules sharing one target can no longer occur —
    # normalize_rules now rejects that at CONSTRUCTION (load time), proven by the
    # duplicate-provider-target tests in test_chat_parameter_contract.py. Both
    # protections are required and complementary: load-time rejects a conflicting
    # rule config; this runtime guard rejects two encodings of one legitimate rule.
    rules = (_native("provider_params.top_k", "extra_body.top_k", schema=_INT),)
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {
                "model": "p/m",
                "messages": [],
                "provider_params.top_k": 40,  # flat dot-key encoding
                "provider_params": {"top_k": 50},  # nested wrapper encoding
            },
            rules=rules,
        )
    assert exc.value.rejected == {"provider_params.top_k": "duplicate_channel"}


def test_all_rejections_are_reported_together_and_sorted() -> None:
    with pytest.raises(UnsupportedParametersError) as exc:
        _classify(
            {"model": "p/m", "messages": [], "zeta": 1, "alpha": 2, "temperature": 99},
            rules=(_direct("temperature", schema=_NUM),),
        )
    # deterministic, path-sorted; every offending path surfaces at once.
    assert exc.value.rejected == {
        "alpha": "unknown",
        "temperature": "malformed",
        "zeta": "unknown",
    }


# --- single-source consistency: summary path ⇒ dispatchable ------------------


def test_every_summary_path_is_accepted_by_dispatch_for_that_auth_mode() -> None:
    # The cross-projection invariant at the dispatch layer: a path the
    # profile-independent summary advertises is accepted by the classifier for
    # that auth mode, because BOTH read the one rule source.
    rules = (
        _direct("temperature", auth=("api_key", "oauth"), schema=_NUM),
        _direct("max_tokens", auth=("api_key", "oauth"), schema=_INT),
    )
    summary = inline_supported_parameters(rules, available_auth_modes=("api_key", "oauth"))
    assert set(summary) == {"temperature", "max_tokens"}
    body = {"model": "p/m", "messages": [], "temperature": 1.0, "max_tokens": 8}
    out = _classify(body, rules=rules, auth_mode="api_key")
    assert out["temperature"] == 1.0
    assert out["max_tokens"] == 8
