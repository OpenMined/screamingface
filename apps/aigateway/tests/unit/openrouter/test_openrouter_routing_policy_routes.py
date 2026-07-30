"""OME-704: the routing controls through the REAL ``POST /v1/chat/completions``.

FEATURE: an authenticated researcher constrains an OpenRouter request by unit price
and downstream data policy, using five documented ``provider_params`` leaves, without
the gateway ever exposing OpenRouter's raw ``provider`` control object.

STORY: as a researcher benchmarking on a budget, I say "sort by price, refuse an
endpoint dearer than X per prompt token, and refuse one that trains on my data" and I
get either a request served under exactly those constraints or an explicit refusal.

WHY this module exists alongside the unit suites: ``test_openrouter_routing_policy``
proves the RULES and ``test_openrouter_routing_policy_wire`` proves the BOUNDARY, both
by calling the pieces directly. Neither can prove the pipeline ORDER — that a refusal
happens before credential material is read, that the 503 precedes cache planning, that
the generic ingress strip still runs first. Order is a property of the composed route,
so it is tested through the route.

INVARIANT (the security core): nothing a caller can write reaches a credential or the
wire until classification has accepted it. Every negative case below therefore asserts
TWO things — the sanitized rejection, and that dispatch never happened.

AIDEV-NOTE: the fixtures/helpers are the house OpenRouter route harness (see
``test_openrouter_security`` and ``test_openrouter_error_policy``), copied rather than
shared because each module pins its own dispatch double.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from litellm.exceptions import NotFoundError

from aigateway.core.oauth.store import OAuthConnectionStore
from aigateway.core.parameter_projection import caller_cache_bypass_paths
from aigateway.core.request_cache.models import RequestCacheEntry
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-routing"
_MODEL = "openrouter/anthropic/claude-fable-5"
_MESSAGES: list[Any] = [{"role": "user", "content": "hi"}]
_OFFICIAL_API_BASE = "https://openrouter.ai/api/v1"

# Spelled out, never imported: a rename of a production constant must not be able to
# silently rename what the caller writes or what OpenRouter receives.
_STRICT = {"require_parameters": True}


@pytest.fixture(autouse=True)
def _api_key_validation_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit test double (per tests/unit/conftest.py AIDEV-NOTE): key readiness is
    # not what the routing controls exercise.
    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(_self, _plugin, _provider, _api_key) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID, stage=ApiKeyValidationStage.READINESS
        )

    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


def _create_connection(client) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


class _Dispatch:
    """Records every ``litellm.acompletion`` call — the last gateway-controlled point."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"or-{len(self.calls)}",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    @property
    def only(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected exactly one dispatch, got {len(self.calls)}"
        return self.calls[0]


def _post_chat(client, body: dict[str, Any] | None = None):
    payload = {"model": _MODEL, "messages": list(_MESSAGES), **(body or {})}
    return client.post("/v1/chat/completions", json=payload)


def _post_wrapper(client, wrapper: dict[str, Any]):
    return _post_chat(client, {"provider_params": wrapper})


# --- the reviewed surface, spelled out ----------------------------------------
#
# (caller leaf, accepted value, the fragment it must produce inside `provider`).
_CONTROLS: tuple[tuple[str, Any, dict[str, Any]], ...] = (
    ("sort", "price", {"sort": "price"}),
    ("max_price_prompt", "1.5", {"max_price": {"prompt": "1.5"}}),
    ("max_price_completion", "0.002", {"max_price": {"completion": "0.002"}}),
    ("data_collection", "deny", {"data_collection": "deny"}),
    ("zdr", True, {"zdr": True}),
)
_ALL_LEAVES = {leaf: value for leaf, value, _ in _CONTROLS}
_ALL_POLICY = {
    "sort": "price",
    # The two price leaves are separate caller controls that share ONE upstream
    # object — the case a per-leaf test cannot reach.
    "max_price": {"prompt": "1.5", "completion": "0.002"},
    "data_collection": "deny",
    "zdr": True,
    **_STRICT,
}


# --- 1 + 2: each control, and all of them, dispatch once with the right policy ---


@pytest.mark.parametrize(("leaf", "value", "fragment"), _CONTROLS, ids=[c[0] for c in _CONTROLS])
def test_each_control_dispatches_once_with_its_documented_policy(
    leaf, value, fragment, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {leaf: value})

    assert resp.status_code == 200, resp.text
    # Exactly one upstream call: an accepted control must not cost a retry.
    assert dispatch.only["provider"] == {**fragment, **_STRICT}


def test_the_whole_control_set_dispatches_as_one_policy(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # Four logical controls, five caller leaves, one upstream object.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, dict(_ALL_LEAVES))

    assert resp.status_code == 200, resp.text
    assert dispatch.only["provider"] == _ALL_POLICY
    # The credential still comes from the account-scoped connection, and the host is
    # still the pinned official base: no routing field may redirect either.
    assert dispatch.only["api_key"] == _KEY
    assert dispatch.only["api_base"] == _OFFICIAL_API_BASE


# --- 10: omission changes nothing ---------------------------------------------


def test_omitting_every_control_leaves_the_request_as_it_was(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # The feature is additive: a caller who says nothing about routing gets exactly
    # the pre-OME-704 request — the gateway-owned strict-routing policy alone.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client)

    assert resp.status_code == 200, resp.text
    assert dispatch.only["provider"] == _STRICT


# --- 3: invalid values get the existing stable rejection shape -----------------
#
# WHY the value grammar is this strict: a price ceiling that parses loosely is a
# ceiling the caller did not choose. Each row is a spelling that would otherwise
# reach OpenRouter as a DIFFERENT number, or as no number at all.
_INVALID: tuple[tuple[str, Any], ...] = (
    ("sort", "throughput"),  # provider SELECTION, excluded scope (OME-703)
    ("sort", "latency"),
    ("sort", "price "),  # trailing space — invisible in a diff
    ("sort", 1),
    ("max_price_prompt", "-1"),  # a signed "ceiling" is not a ceiling
    ("max_price_prompt", "+1"),
    ("max_price_prompt", "1e5"),  # exponent: a second spelling of one value
    ("max_price_prompt", "01"),  # ambiguous spelling
    ("max_price_prompt", ".5"),  # incomplete
    ("max_price_prompt", "1."),
    ("max_price_prompt", " 1"),
    ("max_price_prompt", "NaN"),  # Decimal-parseable, and NOT a price
    ("max_price_prompt", "inf"),
    ("max_price_prompt", ""),
    ("max_price_prompt", 1.5),  # a float would round; the contract says string
    ("max_price_prompt", True),
    ("max_price_prompt", "1" * 65),  # past the published maxLength
    ("max_price_completion", "0.1.2"),
    ("max_price_completion", None),
    ("data_collection", "maybe"),
    ("data_collection", "Deny"),  # case is not normalized: an enum is an enum
    ("data_collection", ""),
    ("zdr", "true"),  # a string is not a boolean
    ("zdr", 1),
    ("zdr", None),
)


@pytest.mark.parametrize(("leaf", "value"), _INVALID, ids=[f"{k}={v!r}" for k, v in _INVALID])
def test_an_invalid_value_is_refused_and_never_dispatched(
    leaf, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {leaf: value})

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    # The existing shape, unchanged: the path is named, the reason is a closed code.
    assert detail["rejected"] == {f"provider_params.{leaf}": "malformed"}
    # INVARIANT: an invalid value never reaches dispatch.
    assert dispatch.calls == []


def test_a_rejection_never_echoes_the_raw_value(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # INVARIANT: the rejection map carries SAFE request paths and closed reason codes
    # only. The caller's value is untrusted input that would otherwise land in a
    # response body and every log line that copies it — so it is named nowhere. A
    # distinctive value makes this checkable instead of coincidental.
    _create_connection(authenticated_client)
    marker = "9e5c-canary-value"
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {"max_price_prompt": marker})

    assert resp.status_code == 400, resp.text
    assert marker not in resp.text
    assert dispatch.calls == []


def test_a_refusal_names_every_bad_leaf_at_once(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # One pass, one answer: a caller fixing three mistakes should not need three
    # round trips to discover them.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(
            authenticated_client,
            {"sort": "throughput", "max_price_prompt": "-1", "zdr": "yes", "data_collection": "ok"},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {
        "provider_params.sort": "malformed",
        "provider_params.max_price_prompt": "malformed",
        "provider_params.zdr": "malformed",
        "provider_params.data_collection": "malformed",
    }
    assert dispatch.calls == []


def test_one_bad_leaf_refuses_the_whole_request(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # Fail closed, never partially: serving the request without the ceiling the
    # caller asked for is the failure mode this whole design exists to prevent.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(
            authenticated_client, {"sort": "price", "max_price_prompt": "not-a-price"}
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider_params.max_price_prompt": "malformed"}
    assert dispatch.calls == []


# --- 4: a refusal precedes credential material AND dispatch -------------------


def _credential_tripwire(_request, **_kwargs):
    raise AssertionError("credential injection ran on a refused request")


@pytest.mark.parametrize(
    "wrapper",
    [
        {"max_price_prompt": "-1"},
        {"sort": "throughput"},
        {"zdr": "true"},
        {"order": ["anthropic"]},
        {"max_price": {"prompt": "1"}},
    ],
    ids=["bad-price", "bad-sort", "bad-zdr", "wrapped-order", "wrapped-max_price"],
)
def test_a_refused_request_never_reaches_credential_material(
    wrapper, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # INVARIANT (the fail-closed ordering): classification runs before
    # ``_inject_credentials``, so a malformed or forbidden routing field is refused
    # while the account's encrypted key is still untouched. Proved by a tripwire on
    # the injection seam itself rather than by reading the route's source.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with (
        patch("aigateway.routes.chat._inject_credentials", _credential_tripwire),
        patch("litellm.acompletion", dispatch),
    ):
        resp = _post_wrapper(authenticated_client, wrapper)

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "unsupported_parameters"
    assert dispatch.calls == []


def test_a_refused_request_never_reaches_provider_preparation(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # The second ordering half: the provider boundary — which is where the routing
    # policy is BUILT — never runs on input classification refused.
    _create_connection(authenticated_client)

    def _tripwire(_self, _body):
        raise AssertionError("prepare_chat_body ran on a refused routing control")

    target = "aigateway.plugins.openrouter_provider.plugin.OpenRouterProviderPlugin"
    with patch(f"{target}.prepare_chat_body", _tripwire):
        resp = _post_wrapper(authenticated_client, {"max_price_prompt": "1e5"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_parameters"


# --- 5: the excluded control plane stays a NAMED unknown rejection -------------
#
# INVARIANT: OME-704 exposes four logical controls and NOTHING else. The raw
# ``provider`` object and every routing/fallback field around it stay unruled, so
# they are refused by name rather than silently dropped — a caller who tries to pin
# an endpoint order learns the gateway refused, instead of believing it complied.
_EXCLUDED_TOP_LEVEL: tuple[tuple[str, Any], ...] = (
    ("provider", {"order": ["anthropic"], "allow_fallbacks": False}),
    ("provider", {"max_price": {"prompt": "1"}}),  # even the SHAPE OME-704 projects
    ("order", ["anthropic"]),
    ("only", ["anthropic"]),
    ("ignore", ["openai"]),
    ("allow_fallbacks", False),
    ("quantizations", ["fp8"]),
    ("route", "fallback"),
    ("models", ["openrouter/anthropic/claude-opus-4.8"]),
    ("plugins", [{"id": "web"}]),
)


@pytest.mark.parametrize(
    ("path", "value"),
    _EXCLUDED_TOP_LEVEL,
    ids=[f"{k}-{i}" for i, (k, _) in enumerate(_EXCLUDED_TOP_LEVEL)],
)
def test_an_excluded_routing_field_is_a_named_unknown_rejection(
    path, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client, {path: value})

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {path: "unknown"}
    assert dispatch.calls == []


def test_the_raw_provider_object_is_refused_even_beside_valid_controls(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # The interesting composition: valid wrapper leaves do not buy the raw object a
    # way in. `provider` is refused, and its neighbours are refused with it.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(
            authenticated_client,
            {"provider_params": {"sort": "price"}, "provider": {"order": ["anthropic"]}},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider": "unknown"}
    assert dispatch.calls == []


# --- 7: wrapper-shaped attacks ------------------------------------------------
#
# The wrapper is not a passthrough. Each nested key needs its OWN rule, so putting
# an excluded field inside ``provider_params`` is refused exactly like putting it at
# the top level — and the dotted path in the answer names where it was found.
_WRAPPER_ATTACKS: tuple[tuple[str, Any], ...] = (
    ("order", ["anthropic"]),
    ("only", ["anthropic"]),
    ("ignore", ["openai"]),
    ("allow_fallbacks", False),
    ("quantizations", ["fp8"]),
    ("require_parameters", False),  # gateway-owned: not the caller's to relax
    ("max_price", {"prompt": "1"}),  # the upstream SHAPE, not the caller contract
    ("provider", {"order": ["anthropic"]}),
    ("data_collection_policy", "deny"),  # near-miss spelling gets no benefit
    ("zero_data_retention", True),
    ("max_price_prompt_usd", "1"),
)


@pytest.mark.parametrize(("leaf", "value"), _WRAPPER_ATTACKS, ids=[k for k, _ in _WRAPPER_ATTACKS])
def test_a_wrapped_excluded_field_is_a_named_unknown_rejection(
    leaf, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {leaf: value})

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {f"provider_params.{leaf}": "unknown"}
    assert dispatch.calls == []


@pytest.mark.parametrize("leaf", [leaf for leaf, _, _ in _CONTROLS])
def test_a_dotted_top_level_leaf_is_not_a_second_addressing_form(
    leaf, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # INVARIANT: the wrapper OBJECT is the only addressing form. A rule's
    # request_path is literally the string "provider_params.<leaf>", so a TOP-LEVEL
    # key spelled that way would otherwise match the rule directly and dispatch —
    # an undocumented second door into every wrapped control, outside the published
    # contract and outside every wrapper-shaped protection built on it.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client, {f"provider_params.{leaf}": "price"})

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {f"provider_params.{leaf}": "unknown"}
    assert dispatch.calls == []


def test_a_non_object_wrapper_is_refused_by_shape(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client, {"provider_params": ["sort"]})

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider_params": "not_an_object"}
    assert dispatch.calls == []


# --- 6: the generic LiteLLM control plane keeps its SILENT pre-credential strip ---


def test_generic_dispatch_controls_are_still_stripped_not_rejected(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # WHY these stay SILENT while routing fields are NAMED: the generic control
    # plane is stripped at ingress, before this provider is even resolved — it is
    # not a model parameter any provider could ever enable, so there is no contract
    # under which to report it. OME-704 must not change that: a caller sending
    # `api_base` alongside a price ceiling still gets a served request pinned to the
    # official host, not a 400.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(
            authenticated_client,
            {
                "provider_params": {"max_price_prompt": "1.5"},
                "api_base": "https://evil.example/v1",
                "base_url": "https://evil.example/v1",
                "model_list": [{"model_name": _MODEL, "litellm_params": {"api_key": "sk-evil"}}],
                "extra_body": {"provider": {"order": ["anthropic"], "allow_fallbacks": True}},
            },
        )

    assert resp.status_code == 200, resp.text
    captured = dispatch.only
    # Pinned host, and the caller's control-plane fields are simply gone.
    assert captured["api_base"] == _OFFICIAL_API_BASE
    assert "base_url" not in captured
    assert "model_list" not in captured
    # INVARIANT: `extra_body` is the wire location the routing policy itself travels
    # through, which makes a caller-supplied one the most dangerous of the four —
    # it is the one field that could smuggle a raw `provider` object to the exact
    # place the gateway's own policy lands. It must be gone, and the policy that
    # arrives must be the gateway's.
    assert captured["provider"] == {"max_price": {"prompt": "1.5"}, **_STRICT}
    # `extra_body` is gone outright. Nothing in this request projects there (only
    # `provider_params.top_k` does), so its presence could only be the caller's.
    assert "extra_body" not in captured
    assert "evil.example" not in repr({k: v for k, v in captured.items() if k != "api_key"})


def test_a_wrapped_native_param_and_the_routing_policy_share_the_wire(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # WHY this composition is worth pinning: ``provider_params.top_k`` projects to
    # ``extra_body.top_k`` while the routing policy travels as ``provider`` — and
    # litellm reaches OpenRouter by folding non-OpenAI kwargs INTO ``extra_body``
    # and then flattening it onto the top level. The two channels therefore meet in
    # one place, and a collision there would drop one of them silently.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {"top_k": 40, "sort": "price"})

    assert resp.status_code == 200, resp.text
    captured = dispatch.only
    assert captured["extra_body"] == {"top_k": 40}
    assert captured["provider"] == {"sort": "price", **_STRICT}


# --- 8: a no-eligible-endpoint refusal stays sanitized and keeps the key valid ---


_WIRE_REQUEST = httpx.Request("POST", _OFFICIAL_API_BASE)


def _as_transport(exc: Exception, *, wire_status: int) -> Exception:
    # Mirrors the provenance a real litellm OpenRouter transport failure carries
    # (chained httpx.HTTPStatusError + surfaced wire headers), so the fail-closed
    # classifier reads it as transport rather than as an ambiguous 502.
    response = httpx.Response(wire_status, request=_WIRE_REQUEST)
    exc.__cause__ = httpx.HTTPStatusError(
        f"{wire_status}", request=_WIRE_REQUEST, response=response
    )
    exc.litellm_response_headers = dict(response.headers)  # type: ignore[attr-defined]
    return exc


def _active_labels(client, account_id: str) -> list[str]:
    async def _list() -> list[str]:
        connections = await OAuthConnectionStore().list(
            account_id, provider="openrouter", status="active"
        )
        return sorted(connection.label for connection in connections)

    return client.portal.call(_list)


def test_a_price_ceiling_no_endpoint_can_meet_is_refused_without_touching_the_key(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # This is what a price ceiling BUYS, and its cost: OpenRouter refuses rather than
    # quietly serving the request at a higher price. The refusal must arrive as a
    # refusal, sanitized — and it says nothing about the CREDENTIAL, so the key that
    # was perfectly valid must still be active afterwards. Marking it invalid here
    # would lock a researcher out of their account over a routing constraint.
    _create_connection(authenticated_client)
    account_id = authenticated_client.get("/v1/auth/me").json()["id"]
    exc = _as_transport(
        NotFoundError(
            message=(
                "No endpoints found that satisfy max_price. Tried provider secret-internal-router."
            ),
            llm_provider="openrouter",
            model=_MODEL,
            response=httpx.Response(404, request=_WIRE_REQUEST),
        ),
        wire_status=404,
    )

    async def _raise(**_kwargs):
        raise exc

    with patch("litellm.acompletion", _raise):
        resp = _post_wrapper(authenticated_client, {"max_price_prompt": "0.0000001"})

    assert resp.status_code == 404, resp.text
    assert resp.status_code != 200
    # Neither the provider's prose nor a named internal endpoint reaches the caller.
    assert "secret-internal-router" not in resp.text
    assert "No endpoints found" not in resp.text
    # INVARIANT: only a 401 may invalidate an OpenRouter credential.
    assert _active_labels(authenticated_client, account_id) == ["work-openrouter"]


def test_a_zdr_refusal_embedded_in_a_200_body_still_keeps_the_key_valid(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # The second shape of the same refusal — an error object inside an HTTP 200. A
    # gateway reading only the status would hand back a "successful" completion with
    # no choices while the ZDR constraint was never honored.
    _create_connection(authenticated_client)
    account_id = authenticated_client.get("/v1/auth/me").json()["id"]
    payload = {
        "id": "gen-zdr",
        "choices": [],
        "error": {
            "code": 404,
            "message": "No endpoints found that support zero data retention",
            "metadata": {"provider_name": "secret-internal-router"},
        },
    }

    async def _return(**_kwargs):
        return SimpleNamespace(model_dump=lambda: payload)

    with patch("litellm.acompletion", _return):
        resp = _post_wrapper(authenticated_client, {"zdr": True})

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "provider_error"
    assert "No endpoints found" not in resp.text
    assert "secret-internal-router" not in resp.text
    assert _active_labels(authenticated_client, account_id) == ["work-openrouter"]


# --- 11: ZDR is upstream endpoint ELIGIBILITY, never a retention guarantee -----


def test_no_response_claims_end_to_end_zero_retention(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # WHY this test exists: `zdr` and `data_collection: "deny"` are ENDPOINT
    # ELIGIBILITY filters — they ask OpenRouter to route to endpoints that declare a
    # property. The gateway does not observe upstream storage and cannot verify a
    # claim about it, so no gateway response may imply one. A caller who read
    # "zero data retention guaranteed" in an AIGateway response would make a real
    # privacy decision on a promise nobody here can keep.
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {"zdr": True, "data_collection": "deny"})

    assert resp.status_code == 200, resp.text
    lowered = resp.text.lower()
    for claim in ("zero data retention", "not retained", "no retention", "guarantee"):
        assert claim not in lowered, f"the response implies a retention promise: {claim!r}"
    # The controls are carried as what they are — routing conditions on the request.
    assert dispatch.only["provider"] == {"zdr": True, "data_collection": "deny", **_STRICT}


# --- 9: every routing-control request bypasses the prompt cache ----------------


@pytest.fixture
def _cache_env(monkeypatch):
    # Must run before the `client` fixture builds the app so Settings sees it.
    monkeypatch.setenv("AIGW_REQUEST_CACHE_ENABLED", "true")


@pytest.fixture
def cache_client(_cache_env, authenticated_client: TestClient) -> TestClient:
    return authenticated_client


def _stored_entries(client) -> int:
    return client.portal.call(RequestCacheEntry.all().count)


def _post_cacheable(client, wrapper: dict[str, Any] | None = None):
    body: dict[str, Any] = {"cache": {"use-cache": True}}
    if wrapper is not None:
        body["provider_params"] = wrapper
    return _post_chat(client, body)


@pytest.mark.parametrize(
    ("leaf", "value"),
    [*[(leaf, value) for leaf, value, _ in _CONTROLS], ("zdr", False)],
    ids=[*[c[0] for c in _CONTROLS], "zdr-false"],
)
def test_a_routing_control_request_bypasses_the_cache_and_stores_nothing(
    leaf, value, enabled_openrouter, credential_blobs, cache_client
) -> None:
    # INVARIANT (OME-479 §4.6): every routing control declares
    # ``cache_behavior="bypass"``, because the v1 cache key cannot carry a routing
    # policy (OME-702). Serving a cached answer produced under a DIFFERENT price
    # ceiling or data policy would silently violate the constraint the caller set —
    # and ``zdr: false`` is included precisely because it projects to nothing: the
    # bypass is owed to the field's PRESENCE in the request, not to its effect on
    # the wire.
    _create_connection(cache_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        first = _post_cacheable(cache_client, {leaf: value})
        second = _post_cacheable(cache_client, {leaf: value})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.headers["X-AIGW-Cache"] == "bypass"
    assert second.headers["X-AIGW-Cache"] == "bypass"
    # No key is published for a bypassed request, so nothing identifies an entry.
    assert "X-AIGW-Cache-Key" not in first.headers
    # Symmetric proof: it neither READ (both dispatched) nor WROTE (store empty).
    assert len(dispatch.calls) == 2
    assert _stored_entries(cache_client) == 0


@pytest.mark.parametrize(
    ("leaf", "value"),
    [*[(leaf, value) for leaf, value, _ in _CONTROLS], ("zdr", False)],
    ids=[*[c[0] for c in _CONTROLS], "zdr-false"],
)
def test_every_control_is_attributed_as_a_caller_visible_bypass_path(leaf, value) -> None:
    # AIDEV-NOTE: the route test above cannot ATTRIBUTE the bypass. Today every
    # OpenRouter request is structurally cache-ineligible (``prepare_chat_body``
    # always sets ``api_base`` and ``provider``, neither of which the v1 key builder
    # can key), so a bare request bypasses too and the header proves nothing about
    # these five paths specifically.
    #
    # This is the tripwire that survives that: the bypass is ALSO owed to the
    # caller-visible contract, resolved from the real rule set before preparation.
    # If a later cache change (OME-702) makes the prepared body keyable, this path
    # still forces the bypass — and if a rule ever stopped declaring it, this test
    # fails while the route test would still pass on the structural accident.
    plugin = OpenRouterProviderPlugin()
    rules = tuple(plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"))
    paths = caller_cache_bypass_paths(
        {
            "model": _MODEL,
            "messages": list(_MESSAGES),
            # The `zdr: False` row is here on purpose: presence is what bypasses.
            "provider_params": {leaf: value},
        },
        rules=rules,
        auth_mode="api_key",
    )
    assert paths == (f"provider_params.{leaf}",)
