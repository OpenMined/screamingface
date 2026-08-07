from __future__ import annotations

import json
import logging
import time
from functools import partial
from typing import Any, Literal, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aigateway.core.cache_ports import CACHE_UNAVAILABLE_REASON, PUBLISHED_CACHE_REASONS
from aigateway.core.oauth.store import OAuthConnectionStore, credential_key_for
from aigateway.core.request_cache import CacheUnavailable, RequestCacheWrite
from aigateway.core.request_cache.global_keys import BYPASS_CANONICALIZATION
from aigateway.core.request_cache.models.request_cache_entry import RequestCacheEntry
from aigateway.plugins.anthropic_provider.auth import credential_service_for
from aigateway.plugins.anthropic_provider.chat_handler import prepare_claude_code_body

_CHAT_PATH = "/v1/chat/completions"
_PATCH_TARGET = (
    "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion"
)
_OAUTH_TOKEN = "sk-ant-oat01-subscription-token"
_API_KEY_TOKEN = "sk-ant-api03-raw-key-token"

_WriteStatus = Literal["stored", "race_lost", "not_stored"]


# --- arrangement --------------------------------------------------------------


async def _create_active_connection(
    account_id: str, *, label: str = "default", auth_type: Literal["oauth", "api_key"] = "oauth"
):
    store = OAuthConnectionStore()
    if auth_type == "api_key":
        return await store.create_api_key(
            account_id=account_id,
            provider="anthropic",
            label=label,
            connection_id=uuid4(),
        )
    connection = await store.create_pending(
        account_id=account_id,
        provider="anthropic",
        label=label,
        connection_id=uuid4(),
    )
    return await store.complete(connection, label=label, identity=None)


def _arrange_account(
    client,
    credential_blobs,
    *,
    label: str = "default",
    token: str = "tok",
    auth_type: Literal["oauth", "api_key"] = "oauth",
) -> str:
    account_id = client.get("/v1/auth/me").json()["id"]
    connection = client.portal.call(
        partial(_create_active_connection, account_id, label=label, auth_type=auth_type)
    )
    credential = (
        {"auth_type": "api_key", "api_key": token}
        if auth_type == "api_key"
        else {
            "access_token": token,
            "refresh_token": "rt",
            "expires_at_ms": int(time.time() * 1000) + 3_600_000,
            "token_type": "Bearer",
        }
    )
    credential_blobs.write(
        credential_service_for(credential_key_for(account_id, connection.id)),
        "default",
        json.dumps(credential),
    )
    return account_id


def _chat_body(**overrides) -> dict:
    body = {
        "model": "anthropic/claude-haiku-4-5",
        "messages": [{"role": "user", "content": "how many primes below one hundred?"}],
    }
    body.update(overrides)
    return body


class _DispatchCounter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, body):
        self.calls.append(dict(body))
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"resp-{len(self.calls)}",
                "choices": [
                    {"message": {"content": "PLAINTEXT-ANSWER-42"}, "finish_reason": "stop"}
                ],
            }
        )


@pytest.fixture
def _cache_env(monkeypatch):
    monkeypatch.setenv("AIGW_REQUEST_CACHE_ENABLED", "true")


@pytest.fixture
def cache_client(_cache_env, client: TestClient) -> TestClient:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    return client


# --- the fake store: the TARGET contract, not the implementation --------------


class _ContractStore:
    """An in-memory store that behaves exactly as the frozen contract specifies.

    INVARIANT modelled: ``get`` returns ``None`` ONLY for a genuine miss and
    raises ``CacheUnavailable`` for every failure mode; ``set_if_absent`` NEVER raises
    and reports one of three outcomes; first successful insert wins.
    """

    def __init__(
        self,
        *,
        available: bool = True,
        get_raises: Exception | None = None,
        set_raises: Exception | None = None,
        set_result: _WriteStatus | None = None,
        availability_raises: bool = False,
    ) -> None:
        self._available = available
        self._get_raises = get_raises
        self._set_raises = set_raises
        self._set_result: _WriteStatus | None = set_result
        self._availability_raises = availability_raises
        self.rows: dict[str, dict[str, Any]] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[RequestCacheWrite] = []

    def cache_available(self) -> bool:
        if self._availability_raises:
            raise RuntimeError("the availability probe itself failed")
        return self._available

    async def get(self, key_hash: str) -> dict[str, Any] | None:
        self.get_calls.append(key_hash)
        if not self._available:
            # Modelled from the real store: a closed gate RAISES rather than reporting
            # a miss, because a miss would make the route write to a degraded worker.
            raise CacheUnavailable("this worker is not serving the global cache")
        if self._get_raises is not None:
            raise self._get_raises
        return self.rows.get(key_hash)

    async def set_if_absent(self, entry: RequestCacheWrite) -> _WriteStatus:
        self.set_calls.append(entry)
        if self._set_raises is not None:
            # The contract says this never raises; the route must survive it anyway.
            raise self._set_raises
        if self._set_result is not None:
            return self._set_result
        if entry.key_hash in self.rows:
            return "race_lost"
        self.rows[entry.key_hash] = entry.response
        return "stored"


def _install(client: TestClient, store: _ContractStore) -> _ContractStore:
    # INVARIANT (plan §5.1): ONE object under ONE attribute. Swapping it wholesale is
    # the only supported way to substitute the store, which is what makes these
    # failure modes testable without a broken database.
    cast(Any, client.app).state.request_cache_store = store
    return store


# --- the availability contract ------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        CacheUnavailable("global cache read failed"),
        CacheUnavailable("global cache entry contains malformed JSON"),
        CacheUnavailable("global cache payload is not an object"),
    ],
    ids=["database_error", "malformed_json", "invalid_shape"],
)
def test_a_store_that_cannot_be_read_yields_a_bypass_and_never_a_500(
    credential_blobs, cache_client, failure: Exception
) -> None:
    """THE availability test: the cache may never fail a request the provider can serve.

    This is the whole reason the store contract signals failure with an exception
    rather than a ``None``: the three failures parametrized here are indistinguishable
    from a miss at the type level, and a miss makes the route dispatch AND write. The
    STATUS is asserted, not just the header — a 500 here would mean an unreachable
    database took the gateway down with it.
    """
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore(get_raises=failure))
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "bypass"
    assert resp.headers["X-AIGW-Cache-Reason"] == CACHE_UNAVAILABLE_REASON
    assert len(counter.calls) == 1, "the provider must still have been dispatched"
    assert resp.json()["choices"][0]["message"]["content"] == "PLAINTEXT-ANSWER-42"
    # INVARIANT: a read failure is a BYPASS, not a miss — so NO write was attempted.
    assert store.set_calls == []
    assert "X-AIGW-Cache-Write" not in resp.headers


def test_a_surrogate_in_the_prompt_bypasses_instead_of_failing_the_request(
    credential_blobs, cache_client
) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    body = _chat_body(messages=[{"role": "user", "content": "cut " + chr(0xD800)}])
    with patch(_PATCH_TARGET, counter):
        response = cache_client.post(
            _CHAT_PATH,
            content=json.dumps(body, ensure_ascii=True).encode("ascii"),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200, response.text
    assert response.headers["X-AIGW-Cache"] == "bypass"
    assert response.headers["X-AIGW-Cache-Reason"] == BYPASS_CANONICALIZATION
    assert len(counter.calls) == 1


def test_cache_failure_logs_escape_caller_controlled_model_newlines(
    credential_blobs, cache_client, caplog
) -> None:
    _arrange_account(cache_client, credential_blobs)
    _install(cache_client, _ContractStore(get_raises=CacheUnavailable("read failed")))
    forged_marker = "FORGED-CACHE-LOG-LINE"
    model = f"anthropic/claude-haiku-4-5\n{forged_marker}"

    with caplog.at_level(logging.WARNING, logger="aigateway.routes.chat_cache_stage"):
        response = cache_client.post(_CHAT_PATH, json=_chat_body(model=model))

    assert response.status_code < 500, response.text
    messages = [
        record.getMessage() for record in caplog.records if forged_marker in record.getMessage()
    ]
    assert messages, "the test did not exercise the caller-controlled model log"
    assert all("\n" not in message for message in messages)


def test_cache_on_does_not_hide_invalid_parameter_validation(
    credential_blobs, cache_client
) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        fill = cache_client.post(_CHAT_PATH, json=_chat_body())
        invalid = cache_client.post(
            _CHAT_PATH,
            json=_chat_body(unknown_field_entirely=1),
        )

    assert fill.status_code == 200, fill.text
    assert fill.headers["X-AIGW-Cache"] == "miss"
    assert invalid.status_code == 400, invalid.text
    assert invalid.headers.get("X-AIGW-Cache") != "hit"
    assert len(counter.calls) == 1, "the invalid request must not replay or dispatch"
    assert cache_client.portal.call(RequestCacheEntry.all().count) == 1


def test_a_closed_gate_bypasses_without_attempting_a_write(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore(available=False))
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "bypass"
    assert len(counter.calls) == 1
    assert store.set_calls == []


def test_an_availability_probe_that_itself_raises_is_treated_as_closed(
    credential_blobs, cache_client
) -> None:
    # WHY: a gate that cannot answer is a gate that is closed. Defence in depth — the
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore(availability_raises=True))
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "bypass"
    assert resp.headers["X-AIGW-Cache-Reason"] == CACHE_UNAVAILABLE_REASON
    assert store.get_calls == [], "a closed gate must not be read"
    assert len(counter.calls) == 1


def test_a_write_that_fails_after_a_successful_dispatch_still_returns_the_response(
    credential_blobs, cache_client
) -> None:
    """Plan §8 #16: the caller owns their dispatch result; only the fill is lost."""
    _arrange_account(cache_client, credential_blobs)
    _install(cache_client, _ContractStore(set_raises=RuntimeError("disk full")))
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["choices"][0]["message"]["content"] == "PLAINTEXT-ANSWER-42"
    assert resp.headers["X-AIGW-Cache"] == "miss"
    assert resp.headers["X-AIGW-Cache-Write"] == "not_stored"


def test_a_lost_race_returns_the_callers_own_response(credential_blobs, cache_client) -> None:
    """INVARIANT (plan §5.3): first successful insert wins, and the loser is unharmed.

    The racing caller already paid for a dispatch, so they get their own answer; the
    WINNER's row is what every later caller reads. Two callers must be able to trust
    that one key means one stored response.
    """
    _arrange_account(cache_client, credential_blobs)
    _install(cache_client, _ContractStore(set_result="race_lost"))
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "miss"
    assert resp.headers["X-AIGW-Cache-Write"] == "race_lost"
    assert resp.json()["id"] == "resp-1"


def test_a_response_the_gateway_cannot_round_trip_is_served_but_not_stored(
    credential_blobs, cache_client
) -> None:
    """The narrow, real gap the serializability guard exists for.

    WHY a ``datetime`` and not an arbitrary object: FastAPI's ``jsonable_encoder`` is
    strictly MORE permissive than ``json.dumps`` — it renders a datetime as an ISO
    string, while ``json.dumps`` raises. So a provider response can be perfectly
    serviceable to the caller and still be unstorable. A response nothing could encode
    would fail the RESPONSE, not just the fill, and is not this guard's job.

    INVARIANT: the caller is unaffected. A fill the gateway cannot perform is a lost
    entry, never a lost answer.
    """
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore())

    class _DatetimeBearingDispatch:
        # A callable INSTANCE, not a function: patching a class attribute with a
        # function makes it a descriptor that would also receive ``self``.
        async def __call__(self, body):
            from datetime import UTC, datetime
            from types import SimpleNamespace

            return SimpleNamespace(
                model_dump=lambda: {
                    "id": "resp-1",
                    "created": datetime(2026, 8, 3, tzinfo=UTC),
                    "choices": [
                        {"message": {"content": "PLAINTEXT-ANSWER-42"}, "finish_reason": "stop"}
                    ],
                }
            )

    with patch(_PATCH_TARGET, _DatetimeBearingDispatch()):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["choices"][0]["message"]["content"] == "PLAINTEXT-ANSWER-42"
    assert resp.headers["X-AIGW-Cache"] == "miss"
    assert resp.headers["X-AIGW-Cache-Write"] == "not_stored"
    assert store.rows == {}


def test_response_size_uses_the_compact_json_bytes_that_are_persisted(
    credential_blobs, cache_client
) -> None:
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore())
    response = {
        "id": "resp-1",
        "choices": [{"message": {"content": "PLAINTEXT-ANSWER-42"}, "finish_reason": "stop"}],
    }
    expected_size = len(
        json.dumps(
            response,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    )
    cast(Any, cache_client.app).state.settings.request_cache_max_response_bytes = expected_size

    with patch(_PATCH_TARGET, _DispatchCounter()):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())

    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache-Write"] == "stored"
    assert store.set_calls[0].response_size_bytes == expected_size


@pytest.mark.parametrize(
    ("margin", "expected_write", "expected_rows"),
    [(-2_000, "stored", 1), (+2_000, "not_stored", 0)],
    ids=["just-under-the-cap", "just-over-the-cap"],
)
def test_the_response_size_cap_decides_whether_a_miss_fills_the_cache(
    margin, expected_write, expected_rows, credential_blobs, cache_client
) -> None:
    """An oversized response is SERVED but never stored (plan U5, §8 acceptance 16).

    WHY this guard matters MORE under v2 than it did under v1: a v1 row expired, so an
    oversized entry was a bounded waste of space. A v2 row has ``expires_at = NULL``
    and is shared by every account, so one pathological response would occupy the
    database permanently. The cap is the only thing standing between "no expiry" and
    "unbounded growth" for a single entry.

    WHY a BOUNDARY PAIR and not just the rejection: a cap that refused everything
    would pass a rejection-only test while silently disabling the whole cache. The
    under-cap case is what proves the guard discriminates by size.

    The limit is READ from settings rather than hard-coded — an operator who lowers
    ``AIGW_REQUEST_CACHE_MAX_RESPONSE_BYTES`` must not turn this test red.
    """
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore())
    limit = cast(Any, cache_client.app).state.settings.request_cache_max_response_bytes
    # The JSON wrapper around the content is ~100 bytes, so a 2 KB margin puts each
    # case unambiguously on its side of the cap without depending on exact framing.
    content = "A" * (limit + margin)

    class _BulkyDispatch:
        async def __call__(self, body):
            from types import SimpleNamespace

            return SimpleNamespace(
                model_dump=lambda: {
                    "id": "resp-1",
                    "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                }
            )

    with patch(_PATCH_TARGET, _BulkyDispatch()):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())

    # INVARIANT: the caller gets the full response either way. Refusing to STORE a
    # response may never truncate or withhold it.
    assert resp.status_code == 200, resp.text
    assert resp.json()["choices"][0]["message"]["content"] == content
    assert resp.headers["X-AIGW-Cache"] == "miss"
    assert resp.headers["X-AIGW-Cache-Write"] == expected_write
    assert len(store.rows) == expected_rows


def test_a_response_that_is_not_an_object_is_served_but_not_stored(
    credential_blobs, cache_client
) -> None:
    """Malformed responses are never stored (plan §1 bypass list, §5.2).

    The route builds ``result`` as ``model_dump()`` when the provider response offers
    one and passes the raw object through otherwise, so its dict-ness is a convention
    of every shipped plugin rather than something the type system enforces. A plugin
    that returned a bare list would serialize fine to the caller and then become a
    permanent global entry shaped nothing like a chat completion.

    INVARIANT: the store is fed only what a later reader can serve as a chat response.
    """
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore())

    class _ListReturningDispatch:
        async def __call__(self, body):
            return [{"not": "a completion object"}]

    with patch(_PATCH_TARGET, _ListReturningDispatch()):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())

    assert resp.status_code == 200, resp.text
    assert resp.json() == [{"not": "a completion object"}]
    assert resp.headers["X-AIGW-Cache-Write"] == "not_stored"
    assert store.rows == {}


def test_a_failed_dispatch_stores_nothing_at_all(credential_blobs, cache_client) -> None:
    """An ERROR must never become a cache entry (plan §5.2 — "errors ... never stored").

    WHY this is the most consequential of the never-store rules: a v2 row has
    ``expires_at = NULL`` and is shared by every account. Storing one transient
    provider failure would serve that failure to every caller of that exact request,
    for as long as the database lives, with no TTL to rescue it.

    It holds by CONSTRUCTION — the fill happens after the dispatch returns, so a raise
    skips it — and this test exists because that construction is the kind that a later
    refactor (a try/except around the dispatch that keeps going, say) can quietly undo
    with no other symptom.
    """
    _arrange_account(cache_client, credential_blobs)
    store = _install(cache_client, _ContractStore())

    class _FailingDispatch:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, body):
            self.calls += 1
            raise RuntimeError("upstream exploded")

    dispatch = _FailingDispatch()
    with patch(_PATCH_TARGET, dispatch):
        first = cache_client.post(_CHAT_PATH, json=_chat_body())
        # The identical request again: if the failure had been cached, this would be
        # served from the store and would NOT reach the provider a second time.
        second = cache_client.post(_CHAT_PATH, json=_chat_body())

    assert first.status_code >= 500
    assert store.rows == {}
    assert store.set_calls == []
    assert dispatch.calls == 2, "a failed request must not be answered from cache next time"
    assert second.status_code == first.status_code


# --- the published reason vocabulary at the route -----------------------------


def test_every_reason_the_route_publishes_is_in_the_published_vocabulary(
    credential_blobs, cache_client
) -> None:
    """The header is an operator-facing contract, so its values must be enumerable.

    WHY at the ROUTE and not only at the layers: each layer's constants are checked
    for membership by ``test_global_cache_reason_vocabulary``, but only here is it
    proven that the value which actually reaches the wire is one of them — a header
    writer could still stringify something else on the way out.
    """
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    observed: set[str] = set()
    scenarios = [
        _chat_body(),
        _chat_body(cache={"use-cache": False}),
        _chat_body(cache={"ttl": 30}),
        _chat_body(cache="malformed"),
        _chat_body(temperature=0.5),
        _chat_body(tools=[]),
        _chat_body(unknown_field_entirely=1),
    ]
    with patch(_PATCH_TARGET, counter):
        for body in scenarios:
            resp = cache_client.post(_CHAT_PATH, json=body)
            if resp.status_code != 200:
                continue
            reason = resp.headers.get("X-AIGW-Cache-Reason", "")
            if reason:
                observed.add(reason)
    assert observed, "the sweep must actually have produced some reasons"
    assert observed <= PUBLISHED_CACHE_REASONS, observed - PUBLISHED_CACHE_REASONS


def test_the_reason_header_is_present_and_empty_when_there_is_nothing_to_explain(
    credential_blobs, cache_client
) -> None:
    # WHY present-but-empty rather than absent: an operator scraping the header can
    # then distinguish "this build publishes reasons" from "this reason was omitted".
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        miss = cache_client.post(_CHAT_PATH, json=_chat_body())
        hit = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert miss.headers["X-AIGW-Cache-Reason"] == ""
    assert hit.headers["X-AIGW-Cache-Reason"] == ""


# --- what actually lands in the database (acceptance 5) ----------------------


async def _all_rows() -> list[RequestCacheEntry]:
    return await RequestCacheEntry.all()


def test_the_persisted_row_carries_no_prompt_but_stores_response_plaintext(
    credential_blobs, cache_client
) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(
            _CHAT_PATH,
            json=_chat_body(messages=[{"role": "user", "content": "UNIQUE-PROMPT-MARKER"}]),
        )
    assert resp.headers["X-AIGW-Cache-Write"] == "stored", resp.headers
    rows = cache_client.portal.call(_all_rows)
    assert len(rows) == 1
    row = rows[0]
    blob = json.dumps(
        {
            "key_hash": row.key_hash,
            "prompt_hash": row.prompt_hash,
            "provider": row.provider,
            "model": row.model,
            "response_json": row.response_json,
        }
    )
    assert "UNIQUE-PROMPT-MARKER" not in blob
    assert json.loads(row.response_json)["choices"][0]["message"]["content"] == (
        "PLAINTEXT-ANSWER-42"
    )
    assert row.response_json.lstrip().startswith("{")
    assert row.response_size_bytes > 0


def test_the_persisted_row_never_expires(credential_blobs, cache_client) -> None:
    """RECONSTRUCTS v1's ``test_expired_entry_dispatches_again``.

    v1 wrote a TTL and proved an expired entry re-dispatched. v2 has no per-request
    TTL at all, so the property that replaces it is the one that made the TTL
    unnecessary: a global row is written with ``expires_at = NULL``, which means
    indefinite. Proving it at the row level is the only place this is observable —
    a route test can only ever show that a hit happened *so far*.
    """
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=_chat_body())
    (row,) = cache_client.portal.call(_all_rows)
    assert row.expires_at is None


def test_a_bypassed_request_persists_nothing_at_all(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=_chat_body(cache={"use-cache": False}))
    assert cache_client.portal.call(_all_rows) == []


# --- the Claude-Code attribution block (SF-244 F02 under a shared cache) -----


class _WireCapture:
    """Captures the FINAL kwargs litellm would send, after dispatch-time preparation.

    WHY patched this deep: the Claude-Code block is applied inside ``chat_handler``
    from the RESOLVED credential, so a fake that replaces the plugin's
    ``chat_completion`` would skip the very transform under test.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"resp-{len(self.calls)}",
                "choices": [
                    {"message": {"content": "PLAINTEXT-ANSWER-42"}, "finish_reason": "stop"}
                ],
            }
        )

    def system_text(self, index: int = 0) -> str:
        return json.dumps(self.calls[index].get("system", ""))


def test_an_api_key_miss_dispatches_with_no_claude_code_billing_block(
    credential_blobs, cache_client
) -> None:
    """SF-244 audit F02, re-proven with the global cache in the path.

    A raw API key is billed directly and must never carry the spoofed Claude-Code
    attribution block. The global cache moved the lookup ahead of credential
    resolution, so this is exactly the guarantee an inversion like that could have
    broken: what a MISS sends upstream is still decided by the caller's own resolved
    credential, and the cache changes only who may READ a stored answer.
    """
    _arrange_account(cache_client, credential_blobs, token=_API_KEY_TOKEN, auth_type="api_key")
    wire = _WireCapture()
    with patch("litellm.acompletion", wire):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "miss"
    assert len(wire.calls) == 1
    assert "x-anthropic-billing-header" not in wire.system_text()


def test_an_oauth_miss_still_dispatches_with_the_attribution_block(
    credential_blobs, cache_client
) -> None:
    # The control for the test above: the block IS sent on subscription traffic, so
    # F02's absence assertion is not passing merely because the block never appears.
    _arrange_account(cache_client, credential_blobs, token=_OAUTH_TOKEN)
    wire = _WireCapture()
    with patch("litellm.acompletion", wire):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert resp.status_code == 200, resp.text
    assert len(wire.calls) == 1
    assert "x-anthropic-billing-header" in wire.system_text()


@pytest.mark.parametrize(
    ("filler", "reader"),
    [("oauth", "api_key"), ("api_key", "oauth")],
    ids=["oauth_fills_api_key_reads", "api_key_fills_oauth_reads"],
)
def test_an_entry_filled_under_one_credential_kind_is_read_under_the_other(
    credential_blobs,
    cache_client,
    provisioned_user_factory,
    filler: Literal["oauth", "api_key"],
    reader: Literal["oauth", "api_key"],
) -> None:
    """ACCEPTED CONSEQUENCE, pinned in BOTH directions so it cannot drift silently.

    Whether the attribution block is sent depends on the resolved credential, and a
    global key may never see one — so the mode bit is deliberately NOT keyed and a
    cross-kind read is possible. This is approved, and it rests on the block being
    billing ATTRIBUTION derived from the caller's own first user text (already hashed
    verbatim as ``messages``), plus the fact that a MISS always dispatches under the
    caller's real credential.

    AIDEV-NOTE: the block VARIES per request — its fingerprint is a digest of the
    first user text — so never assert a constant block here. What is asserted is the
    cross-kind READ, and that the constants shaping the block are folded into the
    adapter revision (``tests/unit/anthropic/test_anthropic_global_cache_projection.py``)
    so changing the scheme abandons these entries rather than re-serving them.
    """
    tokens = {"oauth": _OAUTH_TOKEN, "api_key": _API_KEY_TOKEN}
    _arrange_account(
        cache_client,
        credential_blobs,
        token=tokens[filler],
        auth_type=filler,
    )
    wire = _WireCapture()
    with (
        patch("litellm.acompletion", wire),
        patch(
            "aigateway.plugins.anthropic_provider.chat_handler.prepare_claude_code_body",
            wraps=prepare_claude_code_body,
        ) as prepare,
    ):
        filled = cache_client.post(_CHAT_PATH, json=_chat_body())
        assert filled.headers["X-AIGW-Cache"] == "miss", filled.headers

        provisioned_user_factory("other-kind-user")
        login = cache_client.post(
            "/v1/auth/login",
            json={"username": "other-kind-user", "password": "test-user-password"},
        )
        assert login.status_code == 200
        other_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        other_account = cache_client.get("/v1/auth/me", headers=other_headers).json()["id"]
        connection = cache_client.portal.call(
            partial(_create_active_connection, other_account, auth_type=reader)
        )
        credential = (
            {"auth_type": "api_key", "api_key": tokens[reader]}
            if reader == "api_key"
            else {
                "access_token": tokens[reader],
                "refresh_token": "rt",
                "expires_at_ms": int(time.time() * 1000) + 3_600_000,
                "token_type": "Bearer",
            }
        )
        credential_blobs.write(
            credential_service_for(credential_key_for(other_account, connection.id)),
            "default",
            json.dumps(credential),
        )
        hit = cache_client.post(_CHAT_PATH, json=_chat_body(), headers=other_headers)
    assert hit.status_code == 200, hit.text
    assert hit.headers["X-AIGW-Cache"] == "hit"
    assert len(wire.calls) == 1, "the reader must not have dispatched at all"
    assert prepare.call_count == int(filler == "oauth")
    assert hit.json() == filled.json()
