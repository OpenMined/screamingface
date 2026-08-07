"""OME-712 — server-side web search meets the OME-305 global exact-request cache.

FEATURE: provider-neutral `web_search`, and one globally shared exact-request cache.
The two landed independently and interact in exactly two places, both of which are
wrong-hit risks rather than performance ones.

STORY: as a benchmark operator I set a deployment blocklist so no run retrieves from
the domains under test. No caller, and no stored cache row, may hand me an answer that
was retrieved without it.

INVARIANT under test (1): a request carrying either search parameter is UNCACHEABLE.
The dispatched envelope's `exclude_domains` is the union of the caller's list and a
DEPLOYMENT setting, and the cache projection is contractually forbidden from reading
settings — so that union can never reach the key. Ruling 34 calls this out by name:
identical bodies, one key, two different upstream calls. Both rules therefore declare
`cache_behavior="bypass"`, and these tests prove the declaration actually fires.

INVARIANT under test (2): the `plugins` envelope is emitted ONLY when
`web_search is True`. That is what keeps invariant (1) sufficient — if the envelope
could appear on any other condition, a CACHEABLE request would carry an unprojected
output-affecting field and `global_cache`'s `prepared` would silently stop describing
what this boundary sends.

INVARIANT under test (3): `:online` — OpenRouter's implicit-search model variant — is
refused at dispatch AND bypassed at projection. The refusal alone is not enough: the
cache is read before `prepare_chat_body` runs, so a stored row would answer 200 for a
request the gateway must refuse. This is the same class as the routing-policy bypass
and is pinned the same way.

AIDEV-NOTE: these are deliberately NOT key-difference tests. A key-difference test is
what plan §10 owes a KEYED parameter; the obligation for a BYPASS parameter is the
opposite — prove no key is produced at all — plus a non-vacuity proof that the same
helper does produce one for a bare request, so a blanket bypass cannot pass by
accident.
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
from aigateway.core.request_cache.global_keys import BYPASS_DECLARED, build_global_cache_key
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


def _bypass_reason(**overrides: Any) -> str:
    built = _built(**overrides)
    assert isinstance(built, CacheBypass), built
    return built.reason


# --- R1: a search request never reaches the key -----------------------------------


def test_a_web_search_request_is_never_keyed() -> None:
    """THE test for the bypass decision.

    If this ever returns a key, the deployment blocklist — which shapes the dispatched
    request and cannot reach that key — becomes a wrong-hit class: an answer retrieved
    WITHOUT an operator's exclusions served to a deployment that requires them.
    """
    assert _bypass_reason(web_search=True) == BYPASS_DECLARED


def test_caller_exclusions_alone_are_never_keyed() -> None:
    """The second field must bypass on its own, not by leaning on the first.

    ``validate_chat_parameter_combination`` refuses exclusions without
    ``web_search: true`` — but that hook runs on the MISS path only, well after the
    lookup. The cache stage never consults it, so this field has to carry its own
    disposition.
    """
    assert _bypass_reason(web_search_excluded_domains=["example.test"]) == BYPASS_DECLARED


def test_both_fields_together_bypass_for_the_declared_reason() -> None:
    # Not the projection failing, not an unknown parameter — the reviewed declaration.
    assert _bypass_reason(web_search=True, web_search_excluded_domains=["a.test"]) == (
        BYPASS_DECLARED
    )


def test_the_deployment_blocklist_cannot_smuggle_itself_into_a_key() -> None:
    """Two deployments, same body, different operator policy: neither may be keyed.

    This is the concrete shape of ruling 34's hazard. Were these keyed, both plugins
    would produce the SAME hash while dispatching different `exclude_domains` — so one
    deployment would be served the other's retrieval.
    """
    for plugin in (_plugin(), _plugin(web_search_excluded_domains=["rubric.test"])):
        built = _built(plugin, web_search=True)
        assert isinstance(built, CacheBypass), built
        assert built.reason == BYPASS_DECLARED


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
    prepared = _plugin(web_search_excluded_domains=["rubric.test"]).prepare_chat_body(
        _body(web_search=value)
    )
    assert "plugins" not in prepared


def test_a_literal_true_does_emit_the_envelope() -> None:
    # The other half: the parametrized test above must not be passing because the
    # envelope is never emitted at all.
    prepared = _plugin().prepare_chat_body(_body(web_search=True))
    assert prepared["plugins"] == [{"id": "web", "engine": "native"}]


def test_a_request_with_no_search_field_projects_without_an_envelope() -> None:
    produced = _plugin(web_search_excluded_domains=["rubric.test"]).global_cache_projection(_body())
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


def test_both_search_paths_publish_a_bypass_disposition() -> None:
    """A caller reading the parameter contract must see that search is not cached."""
    behaviors = {
        rule.request_path: rule.cache_behavior
        for rule in _plugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
    }
    assert behaviors["web_search"] == "bypass"
    assert behaviors["web_search_excluded_domains"] == "bypass"


def test_neither_search_path_appears_in_the_keyed_set() -> None:
    # Guards against a future promotion to ``keyed`` landing without the design work
    # ruling 34 requires — see the AIDEV-NOTE in ``parameters.py``.
    keyed = {
        rule.request_path
        for rule in _plugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
        if rule.cache_behavior == "keyed"
    }
    assert "web_search" not in keyed
    assert "web_search_excluded_domains" not in keyed


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
            model_dump=lambda: {"id": "or-1", "choices": [{"message": {"content": "ok"}}]}
        )

    return fake_acompletion


def test_a_web_search_request_bypasses_the_cache_through_the_real_route(
    monkeypatch: pytest.MonkeyPatch, credential_blobs, cached_client: TestClient
) -> None:
    """End to end: the disposition is wired, not merely declared.

    Asserts store ACTIVITY as well as the published headers — a correct header with a
    stage that never ran would be a vacuous pass, and the probe count is what
    distinguishes the two.
    """
    _enable_openrouter(monkeypatch, web_search_excluded_domains=["rubric.test"])
    _create_connection(cached_client)
    store = _Store()
    cast(Any, cached_client.app).state.request_cache_store = store
    calls: list[dict[str, Any]] = []

    with patch("litellm.acompletion", _fake_acompletion(calls)):
        response = cached_client.post(
            "/v1/chat/completions",
            json={"model": _MODEL, "messages": _MESSAGES, "web_search": True},
        )

    assert response.status_code == 200, response.text
    assert response.headers["X-AIGW-Cache"] == "bypass"
    assert response.headers["X-AIGW-Cache-Reason"] == BYPASS_DECLARED
    # The stage RAN (so the assertions below are not vacuous) and still read nothing.
    assert store.probes >= 1
    assert store.reads == []
    assert store.rows == {}
    # The request was really dispatched, carrying the union of both exclusion lists.
    assert len(calls) == 1
    assert calls[0]["plugins"] == [
        {"id": "web", "engine": "native", "exclude_domains": ["rubric.test"]}
    ]


def test_a_bare_request_still_uses_the_cache_through_the_real_route(
    monkeypatch: pytest.MonkeyPatch, credential_blobs, cached_client: TestClient
) -> None:
    # Blast-radius proof at the route level: the bypass above is about the search
    # fields, not about OpenRouter losing the cache it just gained.
    _enable_openrouter(monkeypatch, web_search_excluded_domains=["rubric.test"])
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
