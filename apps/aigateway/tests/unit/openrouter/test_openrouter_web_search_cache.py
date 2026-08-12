"""OME-712 — server-side web search meets the OME-305 global exact-request cache.

FEATURE: provider-neutral `web_search`, and one globally shared exact-request cache.
The two landed independently and interact in exactly two places, both of which are
wrong-hit risks rather than performance ones.

SUPERSEDED IN PART (OME-781, owner decision D2, 2026-08-11). Under OME-712 both
search rules declared `cache_behavior="bypass"`, because the dispatched envelope's
`exclude_domains` was the UNION of the caller's list and a DEPLOYMENT setting
(`AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS`) the cache projection could never see.
OME-781 DELETED that setting: the request body is now the sole source of blocked
domains, so the envelope is a pure function of two caller fields and both rules are
`cache_behavior="keyed"`. The tests below that pinned the bypass are inverted or
deleted accordingly; see `docs/spec/2026-08-11-OME-777-cacheable-web-search.md` §3.3.1
for the guarantee the deleted tests recorded before they were removed.

STORY (as it now stands): as a benchmark operator I re-run the same `web_search`
request and it is served from the shared cache like any other keyed OpenRouter
parameter — there is no longer a deployment input that could make two hosts silently
disagree about what a shared key would dispatch.

INVARIANT under test (2, unchanged by OME-781): the `plugins` envelope is emitted
ONLY when `web_search is True`. Combined with `web_search` and
`web_search_excluded_domains` both being keyed leaves, this is what keeps
`global_cache`'s `prepared` a complete description of what this boundary sends
without describing the envelope itself — two requests with the same key carry the
same envelope inputs, hence the same envelope, hence the same upstream call.

INVARIANT under test (3, unchanged by OME-781): `:online` — OpenRouter's
implicit-search model variant — is refused at dispatch AND bypassed at projection.
The refusal alone is not enough: the cache is read before `prepare_chat_body` runs,
so a stored row would answer 200 for a request the gateway must refuse. This is the
same class as the routing-policy bypass and is pinned the same way.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from aigateway.core.cache_ports import PROJECTION_BYPASS_REASON, CacheBypass
from aigateway.core.request_cache import RequestCacheWrite
from aigateway.core.request_cache.global_keys import build_global_cache_key
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_MODEL = "openrouter/anthropic/claude-fable-5"
_ONLINE_MODEL = f"{_MODEL}:online"
_MESSAGES: list[Any] = [{"role": "user", "content": "what happened today?"}]
_KEY = "sk-or-v1-test"

_WriteStatus = Literal["stored", "race_lost", "not_stored"]


def _plugin(**settings: Any) -> OpenRouterProviderPlugin:
    return OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=True, **settings))


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"model": _MODEL, "messages": [dict(m) for m in _MESSAGES]}
    body.update(overrides)
    return body


def _built(plugin: OpenRouterProviderPlugin | None = None, **overrides: Any) -> Any:
    """The real key builder, wired exactly as the route wires it."""
    plugin = plugin or _plugin()
    return build_global_cache_key(
        provider="openrouter",
        body=_body(**overrides),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type=None),
        projection=plugin.global_cache_projection,
        provider_auth_modes=plugin.available_auth_modes(),
    )


# --- R1: a search request now reaches the key --------------------------------------


def test_a_web_search_request_is_now_keyed() -> None:
    """SUPERSEDED (OME-781, owner decision D2).

    Was ``test_a_web_search_request_is_never_keyed``, asserting verbatim:
    ``assert _bypass_reason(web_search=True) == BYPASS_DECLARED``.

    D2 deleted the deployment setting that made bypass necessary, so this is now THE
    test for the keying decision: a ``web_search`` request must reach the cache like
    any other output-affecting OpenRouter parameter.
    """
    built = _built(web_search=True)
    assert not isinstance(built, CacheBypass), built
    assert built.key_hash


def test_both_fields_together_are_keyed_rather_than_bypassed() -> None:
    """SUPERSEDED (OME-781, owner decision D2).

    Was ``test_both_fields_together_bypass_for_the_declared_reason``, asserting
    verbatim: ``assert _bypass_reason(web_search=True,
    web_search_excluded_domains=["a.test"]) == BYPASS_DECLARED``.
    """
    built = _built(web_search=True, web_search_excluded_domains=["a.test"])
    assert not isinstance(built, CacheBypass), built
    assert built.key_hash


# --- R4: the bypass is scoped to search traffic -----------------------------------


def test_a_request_without_search_still_gets_a_key() -> None:
    """Non-vacuity for every bypass assertion above, and the blast-radius proof.

    A blanket bypass would satisfy all of R1 while quietly destroying the cache this
    provider just gained.
    """
    built = _built()
    assert not isinstance(built, CacheBypass), built
    assert built.key_hash


def test_an_ordinary_keyed_parameter_is_unaffected() -> None:
    built = _built(temperature=0.4)
    assert not isinstance(built, CacheBypass), built


# --- R3: the invariant the bypass decision rests on -------------------------------


@pytest.mark.parametrize("value", [False, None, 0, "true", "True", [], {}])
def test_only_a_literal_true_emits_the_provider_envelope(value: Any) -> None:
    """No cacheable request may carry a `plugins` block.

    INVARIANT: the envelope is emitted on `web_search is True` and nothing else. Every
    body that produces one bypasses the cache, so `global_cache`'s `prepared` stays a
    COMPLETE description of what this boundary sends. Widen this condition — an
    is-truthy test, a deployment default that turns search on — and the projection
    silently becomes incomplete while every test above still passes.
    """
    prepared = _plugin().prepare_chat_body(_body(web_search=value))
    assert "plugins" not in prepared


def test_a_literal_true_does_emit_the_envelope() -> None:
    # The other half: the parametrized test above must not be passing because the
    # envelope is never emitted at all.
    prepared = _plugin().prepare_chat_body(_body(web_search=True))
    assert prepared["plugins"] == [{"id": "web"}]


def test_a_request_with_no_search_field_projects_without_an_envelope() -> None:
    produced = _plugin().global_cache_projection(_body())
    assert not isinstance(produced, CacheBypass), produced
    assert "plugins" not in produced["prepared"]


# --- R2: the :online variant is refused ahead of the cache ------------------------


def test_an_online_model_is_bypassed_by_the_projection() -> None:
    """The guard that has to sit AHEAD of the cache read.

    ``prepare_chat_body`` refuses `:online` (see the dual-path pin below), but it runs
    long after the lookup. Without this bypass a row stored before that refusal landed
    would answer 200 for a request the gateway now refuses — retrieval with neither the
    neutral parameter nor the deployment exclusions.
    """
    produced = _plugin().global_cache_projection(_body(model=_ONLINE_MODEL))
    assert isinstance(produced, CacheBypass), produced
    assert produced.reason == PROJECTION_BYPASS_REASON


def test_an_online_model_is_refused_at_dispatch() -> None:
    # The dual-path pin: the projection BYPASSES where dispatch RAISES. One predicate
    # answers both, so the two cannot drift into disagreeing.
    with pytest.raises(HTTPException) as excinfo:
        _plugin().prepare_chat_body(_body(model=_ONLINE_MODEL))
    assert excinfo.value.status_code == 400
    assert cast(dict, excinfo.value.detail)["code"] == "unsupported_model_variant"


def test_an_online_model_produces_no_key() -> None:
    built = _built(model=_ONLINE_MODEL)
    assert isinstance(built, CacheBypass), built


# --- R5: the published contract states the disposition ----------------------------


def test_both_search_paths_now_publish_a_keyed_disposition() -> None:
    """SUPERSEDED (OME-781, owner decision D2).

    Was ``test_both_search_paths_publish_a_bypass_disposition``, asserting verbatim:
    ``assert behaviors["web_search"] == "bypass"`` and
    ``assert behaviors["web_search_excluded_domains"] == "bypass"``.
    """
    behaviors = {
        rule.request_path: rule.cache_behavior
        for rule in _plugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
    }
    assert behaviors["web_search"] == "keyed"
    assert behaviors["web_search_excluded_domains"] == "keyed"


def test_both_search_paths_now_appear_in_the_keyed_set() -> None:
    """SUPERSEDED (OME-781, owner decision D2).

    Was ``test_neither_search_path_appears_in_the_keyed_set``, asserting verbatim:
    ``assert "web_search" not in keyed`` and
    ``assert "web_search_excluded_domains" not in keyed``.

    Guards against a future REGRESSION to ``bypass`` landing without the design work
    OME-781/D2 did — see the AIDEV-NOTE in ``parameters.py``.
    """
    keyed = {
        rule.request_path
        for rule in _plugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
        if rule.cache_behavior == "keyed"
    }
    assert "web_search" in keyed
    assert "web_search_excluded_domains" in keyed


# --- R6: the same behaviour through the real route --------------------------------


class _Store:
    """Records every probe, read and write so a bypass can be proven non-vacuous."""

    def __init__(self) -> None:
        self.probes = 0
        self.reads: list[str] = []
        self.rows: dict[str, dict[str, Any]] = {}

    def cache_available(self) -> bool:
        self.probes += 1
        return True

    async def get(self, key_hash: str) -> dict[str, Any] | None:
        self.reads.append(key_hash)
        return self.rows.get(key_hash)

    async def set_if_absent(self, entry: RequestCacheWrite) -> _WriteStatus:
        self.rows[entry.key_hash] = entry.response
        return "stored"


@pytest.fixture(autouse=True)
def _api_key_validation_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(_self, _plugin, _provider, _api_key) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )

    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)


@pytest.fixture
def _cache_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIGW_REQUEST_CACHE_ENABLED", "true")


@pytest.fixture
def cached_client(_cache_env, authenticated_client: TestClient) -> TestClient:
    return authenticated_client


def _enable_openrouter(monkeypatch: pytest.MonkeyPatch, **settings: Any) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN,
        "settings",
        OpenRouterPluginSettings(enabled=True, **settings),
    )


def _create_connection(client: TestClient) -> None:
    response = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert response.status_code == 201, response.text


def _fake_acompletion(calls: list[dict[str, Any]]):
    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {
                "id": "or-1",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            }
        )

    return fake_acompletion


def test_a_web_search_request_now_uses_the_cache_through_the_real_route(
    monkeypatch: pytest.MonkeyPatch, credential_blobs, cached_client: TestClient
) -> None:
    """SUPERSEDED (OME-781, owner decision D2) — MECHANICAL FALLOUT, not a named
    inversion target: the deleted setting made the OLD version of this test
    (``test_a_web_search_request_bypasses_the_cache_through_the_real_route``) both
    unrunnable (``_enable_openrouter`` no longer accepts a meaningful
    ``web_search_excluded_domains`` kwarg — ``OpenRouterPluginSettings`` dropped the
    field) and semantically false (the route no longer bypasses). Was asserting
    verbatim: ``assert response.headers["X-AIGW-Cache"] == "bypass"``, ``assert
    response.headers["X-AIGW-Cache-Reason"] == BYPASS_DECLARED``, ``assert
    store.reads == []`` and ``assert calls[0]["plugins"] == [{"id": "web", "engine":
    "native", "exclude_domains": ["rubric.test"]}]`` (the union of a caller list and a
    deployment list that no longer exists).

    End to end, through the real route: a repeat ``web_search`` request is served
    from cache exactly like any other keyed OpenRouter parameter.
    """
    _enable_openrouter(monkeypatch)
    _create_connection(cached_client)
    store = _Store()
    cast(Any, cached_client.app).state.request_cache_store = store
    calls: list[dict[str, Any]] = []

    with patch("litellm.acompletion", _fake_acompletion(calls)):
        first = cached_client.post(
            "/v1/chat/completions",
            json={
                "model": _MODEL,
                "messages": _MESSAGES,
                "web_search": True,
                "web_search_excluded_domains": ["rubric.test"],
            },
        )
        repeat = cached_client.post(
            "/v1/chat/completions",
            json={
                "model": _MODEL,
                "messages": _MESSAGES,
                "web_search": True,
                "web_search_excluded_domains": ["rubric.test"],
            },
        )

    assert first.status_code == repeat.status_code == 200, first.text
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert first.headers["X-AIGW-Cache-Write"] == "stored"
    assert repeat.headers["X-AIGW-Cache"] == "hit"
    # Only ONE real dispatch: the repeat was served from the entry, never re-sent.
    assert len(calls) == 1
    # No deployment list to union with any more — the caller's own list, verbatim.
    assert calls[0]["plugins"] == [{"id": "web", "exclude_domains": ["rubric.test"]}]


def test_a_bare_request_still_uses_the_cache_through_the_real_route(
    monkeypatch: pytest.MonkeyPatch, credential_blobs, cached_client: TestClient
) -> None:
    # Blast-radius proof at the route level: search becoming cacheable did not cost
    # OpenRouter the cache it already had for ordinary requests.
    _enable_openrouter(monkeypatch)
    _create_connection(cached_client)
    store = _Store()
    cast(Any, cached_client.app).state.request_cache_store = store
    calls: list[dict[str, Any]] = []

    with patch("litellm.acompletion", _fake_acompletion(calls)):
        response = cached_client.post(
            "/v1/chat/completions",
            json={"model": _MODEL, "messages": _MESSAGES},
        )

    assert response.status_code == 200, response.text
    assert response.headers["X-AIGW-Cache"] == "miss"
    assert store.reads != []
