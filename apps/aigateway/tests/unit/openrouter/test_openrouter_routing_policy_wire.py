"""OME-704: the OpenRouter provider boundary reconstructs the routing policy.

FEATURE: the caller states price and privacy constraints; the GATEWAY states the
upstream ``provider`` object. ``prepare_chat_body`` never merges a projected
policy — it builds a fresh dict from the five validated targets and then forces
``require_parameters=true``.

INVARIANT (the one that makes the feature safe): there is NO code path that copies
an unrecognized ``provider`` member onto the wire. The excluded control plane
(``order``, ``only``, ``ignore``, ``allow_fallbacks``, ``quantizations``) is
unreachable not because it is filtered, but because reconstruction only ever
writes locations named in the allowlist.

INVARIANT: an unexpected projected key or nested shape is REFUSED, not dropped.
Silently discarding it would let a price ceiling or data policy the gateway told
the caller it accepted disappear before dispatch — the request would be served
under constraints the caller never agreed to.

INVARIANT (the tripwire): the load-bearing proofs run against the FINAL wire JSON
through the INSTALLED litellm 1.87.0 OpenRouter transform, not against mocked
dispatch kwargs. litellm carries a non-OpenAI dispatch kwarg to the provider
through two behaviours it does not promise (folding into ``extra_body``, then
flattening onto the top level). If either changes, the routing policy would stop
reaching OpenRouter SILENTLY while every gateway-side assertion still passed.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from aigateway.core.parameter_projection import classify_and_project_chat_parameters
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin

_MODEL = "openrouter/anthropic/claude-fable-5"
_UPSTREAM = "anthropic/claude-fable-5"
_MESSAGES: list[Any] = [{"role": "user", "content": "hi"}]

# Spelled out rather than imported: a rename of a production constant must not be
# able to silently rename what OpenRouter receives.
_STRICT = {"require_parameters": True}


def _dispatch_body(caller_body: dict[str, Any]) -> dict[str, Any]:
    """The exact route pipeline: strip controls → fail-closed classify/project → prepare."""
    plugin = OpenRouterProviderPlugin()
    stripped = plugin.strip_provider_dispatch_controls(caller_body)
    projected = classify_and_project_chat_parameters(
        stripped,
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    return plugin.prepare_chat_body(projected)


def _policy(wrapper: dict[str, Any]) -> dict[str, Any]:
    body = _dispatch_body(
        {"model": _MODEL, "messages": list(_MESSAGES), "provider_params": wrapper}
    )
    return body["provider"]


def _wire_json(dispatch_body: dict[str, Any]) -> dict[str, Any]:
    """The FINAL OpenRouter request JSON, through the installed litellm 1.87.0 path."""
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig
    from litellm.utils import get_optional_params

    passthrough = {
        key: value
        for key, value in dispatch_body.items()
        # Transport plumbing, not request content — never part of the JSON body.
        if key not in {"model", "messages", "api_base", "extra_headers", "api_key"}
    }
    optional = get_optional_params(model=_UPSTREAM, custom_llm_provider="openrouter", **passthrough)
    return OpenrouterConfig().transform_request(
        model=_UPSTREAM,
        messages=list(_MESSAGES),
        optional_params=dict(optional),
        litellm_params={},
        headers={},
    )


def _wire_provider(wrapper: dict[str, Any]) -> Any:
    body = _dispatch_body(
        {"model": _MODEL, "messages": list(_MESSAGES), "provider_params": wrapper}
    )
    return _wire_json(body)["provider"]


# --- omission changes nothing -------------------------------------------------


def test_a_request_without_routing_controls_still_carries_only_strictness() -> None:
    # Reconstruction must not invent a policy. A caller who said nothing about
    # routing gets exactly what OME-651 always sent.
    assert _dispatch_body({"model": _MODEL, "messages": list(_MESSAGES)})["provider"] == _STRICT


def test_omission_reaches_the_wire_as_strictness_alone() -> None:
    body = _dispatch_body({"model": _MODEL, "messages": list(_MESSAGES)})
    assert _wire_json(body)["provider"] == _STRICT


# --- each control reaches its documented location ------------------------------


@pytest.mark.parametrize(
    ("wrapper", "expected"),
    [
        pytest.param({"sort": "price"}, {"sort": "price"}, id="sort"),
        pytest.param(
            {"max_price_prompt": "1.5"}, {"max_price": {"prompt": "1.5"}}, id="max_price_prompt"
        ),
        pytest.param(
            {"max_price_completion": "3"},
            {"max_price": {"completion": "3"}},
            id="max_price_completion",
        ),
        pytest.param(
            {"data_collection": "deny"}, {"data_collection": "deny"}, id="data_collection_deny"
        ),
        pytest.param(
            {"data_collection": "allow"}, {"data_collection": "allow"}, id="data_collection_allow"
        ),
        pytest.param({"zdr": True}, {"zdr": True}, id="zdr_true"),
    ],
)
def test_each_control_is_reconstructed_at_its_documented_location(
    wrapper: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert _policy(wrapper) == {**expected, **_STRICT}


@pytest.mark.parametrize(
    ("wrapper", "expected"),
    [
        pytest.param({"sort": "price"}, {"sort": "price"}, id="sort"),
        pytest.param(
            {"max_price_prompt": "1.5", "max_price_completion": "3"},
            {"max_price": {"prompt": "1.5", "completion": "3"}},
            id="max_price",
        ),
        pytest.param(
            {"data_collection": "deny"}, {"data_collection": "deny"}, id="data_collection"
        ),
        pytest.param({"zdr": True}, {"zdr": True}, id="zdr"),
    ],
)
def test_each_control_survives_the_installed_litellm_transform(
    wrapper: dict[str, Any], expected: dict[str, Any]
) -> None:
    # The tripwire: gateway-side reconstruction is worthless if litellm drops the
    # object on the way out.
    assert _wire_provider(wrapper) == {**expected, **_STRICT}


def test_the_whole_policy_reaches_the_wire_together_with_strictness() -> None:
    provider = _wire_provider(
        {
            "sort": "price",
            "max_price_prompt": "1.5",
            "max_price_completion": "3",
            "data_collection": "deny",
            "zdr": True,
        }
    )
    assert provider == {
        "sort": "price",
        "max_price": {"prompt": "1.5", "completion": "3"},
        "data_collection": "deny",
        "zdr": True,
        "require_parameters": True,
    }


def test_routing_policy_does_not_disturb_the_native_sampling_projection() -> None:
    # `extra_body` means ONE thing here: the native-target output of projection.
    # Routing policy owns `provider` and stays out of it.
    body = _dispatch_body(
        {
            "model": _MODEL,
            "messages": list(_MESSAGES),
            "temperature": 0.5,
            "provider_params": {"top_k": 40, "sort": "price"},
        }
    )
    assert body["extra_body"] == {"top_k": 40}
    assert body["provider"] == {"sort": "price", **_STRICT}
    assert body["temperature"] == 0.5


# --- zdr: false means what omission means -------------------------------------


def test_zdr_false_is_omitted_rather_than_sent() -> None:
    # OpenRouter treats an absent `zdr` and `zdr: false` identically, so the honest
    # encoding of "I have no ZDR constraint" is to say nothing. Sending an explicit
    # false would read as a positive statement about endpoint eligibility that the
    # caller did not make.
    assert _policy({"zdr": False}) == _STRICT


def test_zdr_false_is_absent_from_the_wire_json() -> None:
    assert _wire_provider({"zdr": False}) == _STRICT


def test_zdr_false_does_not_suppress_the_other_controls() -> None:
    assert _policy({"zdr": False, "sort": "price"}) == {"sort": "price", **_STRICT}


# --- price normalization is EXACT ---------------------------------------------


@pytest.mark.parametrize(
    ("sent", "wire"),
    [
        ("0", "0"),
        ("1", "1"),
        ("10", "10"),  # NOT "1" — a trailing-zero strip on an integer would be a 10x error
        ("100", "100"),
        ("0.5", "0.5"),
        ("1.000", "1"),  # a canonical spelling of one value
        ("100.00", "100"),
        ("0.000", "0"),
        ("0.0000001", "0.0000001"),  # a float round-trip would not survive this
        ("1" + "0" * 30, "1" + "0" * 30),  # past the default Decimal context precision
        ("0." + "9" * 62, "0." + "9" * 62),  # 64 chars: the inclusive length bound
    ],
)
def test_a_price_ceiling_is_normalized_without_losing_a_digit(sent: str, wire: str) -> None:
    # WHY normalize at all: one value must have one wire spelling, so a future cache
    # key over the resolved policy (OME-702) cannot treat "1.000" and "1" as two
    # different policies. WHY it must be EXACT: this is a price the caller set, and a
    # normalization that rounded it would enforce a ceiling nobody chose.
    assert _policy({"max_price_prompt": sent}) == {"max_price": {"prompt": wire}, **_STRICT}


@pytest.mark.parametrize("sent", ["0", "1000000", "0.0000001", "1" + "0" * 30])
def test_a_normalized_price_is_never_exponential(sent: str) -> None:
    # `Decimal.normalize()` would render 100 as "1E+2" and 0.0000001 as "1E-7".
    # OpenRouter documents a decimal price; an exponent is a different spelling that
    # an upstream parser is not obliged to accept.
    value = _policy({"max_price_prompt": sent})["max_price"]["prompt"]
    assert "e" not in value.lower()
    assert "+" not in value


def test_the_price_reaching_the_wire_is_a_string_not_a_number() -> None:
    # Exactness is only preserved end to end if the value stays a string. A number
    # here would be re-encoded as a binary float by the JSON serializer.
    wire = _wire_provider({"max_price_prompt": "0.0000001"})
    assert wire["max_price"]["prompt"] == "0.0000001"
    assert isinstance(wire["max_price"]["prompt"], str)


# --- strictness cannot be removed or relaxed ----------------------------------


@pytest.mark.parametrize("value", [False, True])
def test_projected_strictness_is_refused_as_an_internal_mismatch(value: bool) -> None:
    # `require_parameters` is GATEWAY-owned and reconstruction adds it itself. Seeing
    # it in projected state means the classifier and boundary disagree, so silently
    # overwriting even the strict value would hide a projection regression.
    error = _prepare_with_provider({"require_parameters": value})
    assert error.status_code == 503
    assert error.detail == {
        "code": "provider_unavailable",
        "message": "OpenRouter dispatch is unavailable",
    }


def test_strictness_survives_beside_every_reconstructed_control() -> None:
    assert (
        _policy({"sort": "price", "max_price_prompt": "1", "zdr": True})["require_parameters"]
        is True
    )


def test_each_request_gets_a_fresh_policy_object() -> None:
    # A shared dict would let one request's mutation become the next request's policy.
    plugin = OpenRouterProviderPlugin()
    first = plugin.prepare_chat_body({"model": _MODEL, "messages": list(_MESSAGES)})
    first["provider"]["require_parameters"] = False
    first["provider"]["allow_fallbacks"] = True
    second = plugin.prepare_chat_body({"model": _MODEL, "messages": list(_MESSAGES)})
    assert second["provider"] == _STRICT


# --- an unexpected projected policy is REFUSED --------------------------------


def _prepare_with_provider(provider: Any) -> HTTPException:
    plugin = OpenRouterProviderPlugin()
    with pytest.raises(HTTPException) as exc:
        plugin.prepare_chat_body(
            {"model": _MODEL, "messages": list(_MESSAGES), "provider": provider}
        )
    return exc.value


@pytest.mark.parametrize(
    "provider",
    [
        pytest.param({"order": ["anthropic"]}, id="order"),
        pytest.param({"only": ["anthropic"]}, id="only"),
        pytest.param({"ignore": ["openai"]}, id="ignore"),
        pytest.param({"allow_fallbacks": True}, id="allow_fallbacks"),
        pytest.param({"quantizations": ["fp8"]}, id="quantizations"),
        pytest.param({"sort": "price", "order": ["anthropic"]}, id="valid_plus_excluded"),
        pytest.param({"max_price": {"prompt": "1", "request": "5"}}, id="unknown_nested_leaf"),
        pytest.param({"max_price": "1"}, id="container_is_not_an_object"),
        pytest.param({"max_price": ["1"]}, id="container_is_a_list"),
        pytest.param({"sort": "throughput"}, id="value_outside_the_schema"),
        pytest.param({"zdr": "true"}, id="value_of_the_wrong_type"),
        pytest.param({"max_price": {"prompt": 1.5}}, id="price_became_a_number"),
        pytest.param({"max_price": {"prompt": "-1"}}, id="price_outside_the_grammar"),
        pytest.param("not-an-object", id="policy_is_not_an_object"),
        pytest.param(["sort"], id="policy_is_a_list"),
    ],
)
def test_an_unexpected_projected_policy_is_refused(provider: Any) -> None:
    # Every case here is a GATEWAY bug if it ever happens — the classifier cannot
    # produce it. Refusing is the point: an unexpected policy that was silently
    # dropped would serve the request under constraints the caller never agreed to,
    # and one that was silently forwarded would hand OpenRouter the control plane.
    #
    # The last four also prove the boundary re-validates VALUES rather than trusting
    # that classification must have done it — the two layers stay independent.
    error = _prepare_with_provider(provider)
    assert error.status_code == 503
    assert error.detail == {
        "code": "provider_unavailable",
        "message": "OpenRouter dispatch is unavailable",
    }


@pytest.mark.parametrize(
    "provider",
    [
        {"order": ["anthropic"]},
        {"max_price": {"prompt": "1", "request": "5"}},
        "not-an-object",
    ],
)
def test_the_refusal_leaks_no_raw_value(provider: Any) -> None:
    # The client-facing error is indistinguishable from any other dispatch
    # unavailability: no key name, no value, no shape description.
    error = _prepare_with_provider(provider)
    rendered = repr(error.detail)
    for leaked in ("order", "anthropic", "request", "max_price", "not-an-object"):
        assert leaked not in rendered, leaked


@pytest.mark.parametrize("provider", [{"order": ["x"]}, {"zdr": "true"}])
def test_the_refusal_is_not_retried(provider: Any) -> None:
    # A deterministic gateway-side mismatch cannot be fixed by trying again, and a
    # retry would multiply the work for a request that can never succeed.
    from aigateway.core.retry import is_retryable_status

    assert is_retryable_status(_prepare_with_provider(provider)) is False
