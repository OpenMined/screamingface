"""The published ``cache_behavior`` must survive provider preparation (OME-479).

FEATURE: an honest caller-visible cache contract. ``GET /v1/model-parameters``
publishes ONE unconditional ``gateway.cache_behavior`` per request path, and plan
§4.6 defines ``bypass`` as "any presence of the field bypasses prompt caching".
This suite proves that promise against the REAL route, not against
``build_cache_key()`` in isolation.

WHY a separate module from ``test_chat_request_cache.py``: that suite proves the
cache's own semantics (isolation, TTL, controls, storage). This one proves a
COMPOSITION property of the dispatch pipeline — the cache decision cannot be
undone by a provider preparation hook that runs before cache planning.

INVARIANT: the cache plan is derived from the ACCEPTED CALLER-VISIBLE parameter
contract. A provider hook may remove, rename, flatten or nest a field on its way
to the wire; none of that can turn a declared-``bypass`` request into a cacheable
one.
"""

from __future__ import annotations

import json
import time
from functools import partial
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aigateway.core.oauth.store import OAuthConnectionStore, credential_key_for
from aigateway.plugins.anthropic_provider.auth import credential_service_for

_CHAT_PATH = "/v1/chat/completions"
_CONTRACT_PATH = "/v1/model-parameters"
_MODEL = "anthropic/claude-haiku-4-5"
_PLUGIN = "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin"
_PATCH_TARGET = f"{_PLUGIN}.chat_completion"


async def _create_active_connection(account_id: str, *, label: str = "default"):
    store = OAuthConnectionStore()
    connection = await store.create_pending(
        account_id=account_id, provider="anthropic", label=label, connection_id=uuid4()
    )
    return await store.complete(connection, label=label, identity=None)


def _arrange_account(client, credential_blobs) -> str:
    account_id = client.get("/v1/auth/me").json()["id"]
    connection = client.portal.call(partial(_create_active_connection, account_id))
    credential_blobs.write(
        credential_service_for(credential_key_for(account_id, connection.id)),
        "default",
        json.dumps(
            {
                "access_token": "tok",
                "refresh_token": "rt",
                "expires_at_ms": int(time.time() * 1000) + 3_600_000,
                "token_type": "Bearer",
            }
        ),
    )
    return account_id


class _DispatchCounter:
    """Records every provider dispatch; patched over the CLASS method with an
    instance, which bypasses descriptor binding so only ``body`` arrives."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, body):
        self.calls.append(dict(body))
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"resp-{len(self.calls)}",
                "choices": [{"message": {"content": "ANSWER"}}],
            }
        )


def _chat_body(**overrides) -> dict:
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "cache": {"use-cache": True},
    }
    body.update(overrides)
    return body


@pytest.fixture
def _cache_env(monkeypatch):
    # Must run before the `client` fixture builds the app so Settings sees it.
    monkeypatch.setenv("AIGW_REQUEST_CACHE_ENABLED", "true")


@pytest.fixture
def cache_client(_cache_env, client: TestClient) -> TestClient:
    response = client.post(
        "/v1/auth/login", json={"username": "admin", "password": "test-admin-password"}
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    return client


def test_bare_cache_enabled_request_misses_dispatches_and_stores(
    credential_blobs, cache_client
) -> None:
    # Closure item 1 — the positive baseline every other case is measured against.
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert first.status_code == 200
    assert len(counter.calls) == 1
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert first.headers["X-AIGW-Cache-Reason"] == "stored"


def test_repeated_bare_request_still_hits(credential_blobs, cache_client) -> None:
    # Closure item 4 — the fix must not make everything bypass. A request with no
    # output-affecting optional parameter stays cacheable.
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=_chat_body())
        second = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert len(counter.calls) == 1, "the second identical bare request must be served from cache"
    assert second.headers["X-AIGW-Cache"] == "hit"
    assert second.json() == first.json()


def test_reasoning_effort_none_bypasses_and_never_consumes_the_bare_entry(
    credential_blobs, cache_client
) -> None:
    """Closure item 2 — the reproduced public-contract violation.

    ``prepare_chat_body`` drops ``reasoning_effort == "none"`` (it means "no
    thinking", which is what omission already means for Anthropic), so the body
    reaching cache planning was byte-identical to a bare request and hit its
    stored entry — while the contract published ``cache_behavior: bypass``.
    """
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        bare = cache_client.post(_CHAT_PATH, json=_chat_body())
        assert bare.headers["X-AIGW-Cache"] == "miss"

        response = cache_client.post(_CHAT_PATH, json=_chat_body(reasoning_effort="none"))

    assert response.status_code == 200, response.text
    assert response.headers["X-AIGW-Cache"] == "bypass"
    assert "X-AIGW-Cache-Key" not in response.headers
    assert len(counter.calls) == 2, "a declared-bypass request must reach the provider"
    # The value is still ACCEPTED and still normalizes to omission on the wire.
    assert "reasoning_effort" not in counter.calls[-1]


def test_reasoning_effort_high_bypasses_and_dispatches(credential_blobs, cache_client) -> None:
    # Closure item 3 — the surviving-value positive control. `high` is not removed
    # by prepare_chat_body, so it bypassed before the fix and must still bypass.
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(
            _CHAT_PATH, json=_chat_body(reasoning_effort="high", max_tokens=32000)
        )
        second = cache_client.post(
            _CHAT_PATH, json=_chat_body(reasoning_effort="high", max_tokens=32000)
        )
    assert first.status_code == 200, first.text
    assert first.headers["X-AIGW-Cache"] == "bypass"
    assert second.headers["X-AIGW-Cache"] == "bypass"
    assert len(counter.calls) == 2
    assert counter.calls[-1]["reasoning_effort"] == "high"


def test_detailed_contract_publishes_bypass_for_reasoning_effort(
    credential_blobs, cache_client
) -> None:
    # Closure item 5 — the published value the runtime must now honour. This is
    # the OTHER half of the agreement: the fix makes the pipeline match the
    # contract, so the contract itself must not quietly change to match the bug.
    _arrange_account(cache_client, credential_blobs)
    document = cache_client.get(_CONTRACT_PATH, params={"model": _MODEL})
    assert document.status_code == 200, document.text
    entry = document.json()["parameters"]["reasoning_effort"]
    assert entry["gateway"]["status"] == "enabled"
    assert entry["gateway"]["cache_behavior"] == "bypass"
    assert "none" in entry["schema"]["enum"]


def test_a_preparation_hook_that_strips_an_accepted_field_cannot_make_it_cacheable(
    credential_blobs, cache_client
) -> None:
    """Closure item 6 — the GENERAL provider-pipeline guard.

    INVARIANT: cache eligibility is decided from the accepted caller-visible
    contract, so it is independent of what a provider's ``prepare_chat_body``
    does to the body afterwards. This drives the property with a hook that
    removes a DIFFERENT output-affecting parameter (``temperature``) than the one
    the shipped Anthropic hook touches — the same composition failure any future
    provider hook could reintroduce.

    A component-level ``build_cache_key()`` call cannot express this: the
    stripped body it would receive is, by construction, a cacheable one.
    """
    _arrange_account(cache_client, credential_blobs)

    def _strips_temperature(_self, body: dict[str, Any]) -> dict[str, Any]:
        out = dict(body)
        out.pop("temperature", None)
        return out

    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter), patch(f"{_PLUGIN}.prepare_chat_body", _strips_temperature):
        bare = cache_client.post(_CHAT_PATH, json=_chat_body())
        assert bare.headers["X-AIGW-Cache"] == "miss"

        first = cache_client.post(_CHAT_PATH, json=_chat_body(temperature=0.7))
        second = cache_client.post(_CHAT_PATH, json=_chat_body(temperature=0.7))

    assert first.status_code == second.status_code == 200
    assert first.headers["X-AIGW-Cache"] == "bypass"
    assert second.headers["X-AIGW-Cache"] == "bypass"
    assert len(counter.calls) == 3, "a stripped bypass field must not borrow the bare entry"
    # And the stripped request never wrote an entry under the bare key either.
    assert all("temperature" not in call for call in counter.calls)


def test_a_bypassing_request_does_not_write_the_cache(credential_blobs, cache_client) -> None:
    # The bypass promise is symmetric: a declared-bypass request must neither READ
    # nor WRITE the cache. Without this, the FIRST reasoning_effort="none" request
    # would still store a response under the bare-request key and the NEXT bare
    # request would serve a reasoning-effort-shaped answer.
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=_chat_body(reasoning_effort="none"))
        bare = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert first.headers["X-AIGW-Cache"] == "bypass"
    assert bare.headers["X-AIGW-Cache"] == "miss", "the bypassed request must not have stored"
    assert len(counter.calls) == 2
