"""The published ``cache_behavior`` must survive provider preparation (OME-479).

FEATURE: an honest caller-visible cache contract. ``GET /v1/model-parameters``
publishes ONE unconditional ``gateway.cache_behavior`` per request path, and plan
§4.6 defines ``bypass`` as "any presence of the field bypasses prompt caching".
This suite proves that promise against the REAL route, not against
``build_cache_key()`` in isolation.

WHY a separate module from ``test_chat_request_cache.py``: that suite proves the
cache's own semantics (isolation, controls, storage). This one proves a COMPOSITION
property of the dispatch pipeline — the cache decision cannot be undone by what a
provider does to the body on its way to the wire.

INVARIANT: the cache plan is derived from the ACCEPTED CALLER-VISIBLE parameter
contract. A provider hook may remove, rename, flatten or nest a field on its way
to the wire; none of that can turn a declared-``bypass`` request into a cacheable
one.

AIDEV-NOTE (OME-305): the MECHANISM behind that invariant inverted, while every
assertion below still holds. Under v1 ``prepare_chat_body`` ran BEFORE cache
planning, so a hook that stripped a field genuinely could hand the planner a body
indistinguishable from a bare one — the bug closure item 2 reproduced. Under v2 the
cache stage runs FIRST and never sees a prepared body at all, so that particular
failure is now structurally impossible rather than merely tested against.

The composition risk did not disappear, it MOVED: the key is now built from what
``global_cache_projection`` returns, so a projection that dropped an
output-affecting value would reintroduce exactly this class of bug one layer over.
Every test here is therefore retained deliberately — they pin the property from the
CALLER's side, which is the side that does not change when the internals do, and
they are the regression net for whichever layer next decides what the key contains.
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
                "choices": [{"message": {"content": "ANSWER"}, "finish_reason": "stop"}],
            }
        )


def _chat_body(**overrides) -> dict:
    # OME-305: the explicit ``use-cache`` opt-in is now REDUNDANT — participation is
    # the default — and it is retained on purpose. It keeps this suite proving the
    # composition property for a request that asks for caching in so many words, and
    # ``test_chat_request_cache.py`` covers the say-nothing default separately.
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
    # SUPERSEDED (OME-305): v1 reported the fill through X-AIGW-Cache-Reason, which
    # conflated "why this request was not served from cache" with "what happened when
    # we tried to store it". v2 splits them — Reason explains a bypass and is
    # present-but-empty when there is nothing to explain, and the fill outcome has its
    # own header with a three-value vocabulary. Both halves are asserted so the split
    # itself is pinned, not just the new name.
    assert first.headers["X-AIGW-Cache-Reason"] == ""
    assert first.headers["X-AIGW-Cache-Write"] == "stored"


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
    first_body = first.json()
    second_body = second.json()
    assert {key: value for key, value in second_body.items() if key != "_aigw"} == {
        key: value for key, value in first_body.items() if key != "_aigw"
    }
    assert first_body["_aigw"]["usage_accounting"]["cache"]["status"] == "miss"
    assert second_body["_aigw"]["usage_accounting"]["cache"]["status"] == "hit"


def test_reasoning_effort_none_is_keyed_and_never_consumes_the_bare_entry(
    credential_blobs, cache_client
) -> None:
    """SUPERSEDED (OME-305, owner decision B) — the INVARIANT is preserved, the
    MECHANISM changed.

    Was ``test_reasoning_effort_none_bypasses_and_never_consumes_the_bare_entry``,
    asserting verbatim: ``assert response.headers["X-AIGW-Cache"] == "bypass"``,
    ``assert "X-AIGW-Cache-Key" not in response.headers`` and ``assert
    len(counter.calls) == 2, "a declared-bypass request must reach the provider"``.

    The BUG this test reproduces is unchanged and still closed: ``prepare_chat_body``
    drops ``reasoning_effort == "none"``, so the PREPARED body is byte-identical to a
    bare request. Under v1 the cache stage ran after preparation and therefore served
    the bare entry — a wrong hit. Two different things now prevent it, and only the
    second is new: the stage runs BEFORE preparation, so it sees the field at all; and
    ``reasoning_effort`` is now KEYED, so the field lands in the fingerprint instead of
    forcing a bypass.

    WHY the surviving assertion is the important one: "does not consume the bare entry"
    is the property that was ever at stake. Whether it is delivered by refusing to look
    or by looking under a different key is an implementation choice; being served
    another request's answer is the harm.

    AIDEV-NOTE: this is the CONSERVATIVE direction of keying, and the cost is real —
    a bare request and ``reasoning_effort="none"`` dispatch IDENTICAL wire bodies yet
    occupy two entries. That wastes one dispatch and one row. It is the right trade:
    the cache keys what the CALLER sent, because deciding equivalence from what
    preparation happens to strip is exactly the coupling that produced the original
    bug.
    """
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        bare = cache_client.post(_CHAT_PATH, json=_chat_body())
        assert bare.headers["X-AIGW-Cache"] == "miss"

        response = cache_client.post(_CHAT_PATH, json=_chat_body(reasoning_effort="none"))

    assert response.status_code == 200, response.text
    assert response.headers["X-AIGW-Cache"] == "miss", "must not be served the bare entry"
    assert response.headers["X-AIGW-Cache-Key"] != bare.headers["X-AIGW-Cache-Key"]
    assert len(counter.calls) == 2, "the request must reach the provider, not the bare entry"
    # The value is still ACCEPTED and still normalizes to omission on the wire — which
    # is precisely why the two keys must differ despite identical dispatch bodies.
    assert "reasoning_effort" not in counter.calls[-1]


def test_reasoning_effort_high_is_cached_under_its_value(credential_blobs, cache_client) -> None:
    """SUPERSEDED (OME-305, owner decision B).

    Was ``test_reasoning_effort_high_bypasses_and_dispatches``, asserting verbatim:
    ``assert first.headers["X-AIGW-Cache"] == "bypass"``, ``assert
    second.headers["X-AIGW-Cache"] == "bypass"`` and ``assert len(counter.calls) == 2``.

    ``high`` is the surviving-value control: ``prepare_chat_body`` does not remove it,
    so it reaches the wire. Keyed, the repeat is served from the entry — and the
    differing-value case below is what proves the VALUE is in the fingerprint rather
    than merely the field's presence.
    """
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(
            _CHAT_PATH, json=_chat_body(reasoning_effort="high", max_tokens=32000)
        )
        repeat = cache_client.post(
            _CHAT_PATH, json=_chat_body(reasoning_effort="high", max_tokens=32000)
        )
        other = cache_client.post(
            _CHAT_PATH, json=_chat_body(reasoning_effort="low", max_tokens=32000)
        )
    assert first.status_code == 200, first.text
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert repeat.headers["X-AIGW-Cache"] == "hit"
    assert other.headers["X-AIGW-Cache"] == "miss", "a different effort must not hit"
    assert len(counter.calls) == 2
    assert counter.calls[0]["reasoning_effort"] == "high"
    assert counter.calls[-1]["reasoning_effort"] == "low"


def test_detailed_contract_publishes_keyed_for_reasoning_effort(
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
    # SUPERSEDED (OME-305, owner decision B), was:
    #     assert entry["gateway"]["cache_behavior"] == "bypass"
    # The agreement this test protects is UNCHANGED — the published contract and the
    # runtime must say the same thing. Only the shared value moved.
    assert entry["gateway"]["cache_behavior"] == "keyed"
    assert "none" in entry["schema"]["enum"]


def test_a_preparation_hook_that_strips_a_keyed_field_cannot_make_it_borrow_the_bare_entry(
    credential_blobs, cache_client
) -> None:
    """SUPERSEDED (OME-305, owner decision B) — same invariant, stated positively.

    Was ``test_a_preparation_hook_that_strips_an_accepted_field_cannot_make_it_cacheable``,
    asserting verbatim: ``assert first.headers["X-AIGW-Cache"] == "bypass"``, ``assert
    second.headers["X-AIGW-Cache"] == "bypass"`` and ``assert len(counter.calls) == 3,
    "a stripped bypass field must not borrow the bare entry"``.

    INVARIANT (unchanged, and the reason this test exists): cache identity is decided
    from the ACCEPTED CALLER-VISIBLE CONTRACT, so it is independent of what a provider's
    ``prepare_chat_body`` does to the body afterwards. The old name framed that as
    "cannot become cacheable"; with ``temperature`` keyed the request IS cacheable, and
    the property is the sharper one it always stood for: it cannot borrow a DIFFERENT
    request's entry.

    The hook here strips a different parameter (``temperature``) than the shipped
    Anthropic hook touches, so it stands in for the composition failure any future
    provider hook could reintroduce. The three requests dispatch only TWO distinct wire
    bodies — bare, and temperature-stripped-to-bare — and still occupy two separate
    keys, which is the whole point.

    A component-level ``build_cache_key()`` call cannot express this: the stripped body
    it would receive is, by construction, already a bare one.
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
    assert first.headers["X-AIGW-Cache"] == "miss", "must not borrow the bare entry"
    assert first.headers["X-AIGW-Cache-Key"] != bare.headers["X-AIGW-Cache-Key"]
    assert second.headers["X-AIGW-Cache"] == "hit", "its own entry must be reusable"
    # Two dispatches, not three: bare, then the first temperature request. The stripped
    # body was identical to bare both times and STILL did not resolve to bare's entry.
    assert len(counter.calls) == 2, "a stripped keyed field must not borrow the bare entry"
    assert all("temperature" not in call for call in counter.calls)


def test_a_bypassing_request_does_not_write_the_cache(credential_blobs, cache_client) -> None:
    # The bypass promise is symmetric: a bypassing request must neither READ nor
    # WRITE the cache. Without this, the FIRST bypassing request would still store a
    # response under the bare-request key and the NEXT bare request would serve an
    # answer shaped by a parameter it never sent.
    #
    # AIDEV-NOTE (OME-305, owner decision B): the ASSERTIONS here are untouched and this
    # is deliberately NOT a supersession — the invariant did not change, only the
    # VEHICLE. ``reasoning_effort="none"`` used to be a declared bypass and is now
    # keyed, so it can no longer demonstrate the property. ``metadata`` replaces it and
    # is a better vehicle besides: its presence bypasses STRUCTURALLY, ahead of any
    # rule, so no future promotion can silently make this test vacuous the way decision
    # B just did. The empty dict also pins decision 6 — metadata bypasses on PRESENCE,
    # even when it carries nothing.
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=_chat_body(metadata={}))
        bare = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert first.headers["X-AIGW-Cache"] == "bypass"
    # OME-305: the write header exists only on a miss, so its ABSENCE is the direct
    # statement that no fill was even attempted — the bare request below then proves
    # the consequence (nothing was there to be served).
    assert "X-AIGW-Cache-Write" not in first.headers
    assert bare.headers["X-AIGW-Cache"] == "miss", "the bypassed request must not have stored"
    assert bare.headers["X-AIGW-Cache-Write"] == "stored"
    assert len(counter.calls) == 2
