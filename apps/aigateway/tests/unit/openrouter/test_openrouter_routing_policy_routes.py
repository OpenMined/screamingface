"""OME-704: the routing controls through the REAL ``POST /v1/chat/completions``.

FEATURE: an authenticated researcher constrains an OpenRouter request by unit price
and downstream data policy, using five documented ``provider_params`` leaves, without
the gateway ever exposing OpenRouter's raw ``provider`` control object.

STORY: as a researcher benchmarking on a budget, I say "sort by price, refuse an
endpoint dearer than X per million prompt tokens, and refuse one that trains on my data" and I
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
