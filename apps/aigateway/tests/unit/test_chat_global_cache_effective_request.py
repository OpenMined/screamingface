"""OME-305 ruling 57 — the global key is built from the EFFECTIVE request.

FEATURE: one globally shared exact-request cache. "Exact" has to mean the request
that actually reaches the provider, not the bytes the caller happened to type.

STORY: as an operator I store a per-profile ``system_prompt`` so my callers can send
a bare ``{model, messages}`` body. Two of my profiles carry DIFFERENT prompts. Each
must get an answer produced under its own prompt — never the other profile's answer
with its own prompt silently discarded.

INVARIANT under test (ruling 57): profile defaults are merged BEFORE the key is
built, so the key covers every value that reaches the provider. Profile identity, the
profile NAME, the account, and the fact that a value came from a profile are still
absent from the key — two profiles that resolve to the same effective request still
SHARE a row.

WHY this file exists at all: ``cache_behavior="keyed"`` disciplined only
CALLER-SUPPLIED values, because the merge ran after the lookup. A default filled only
an omitted path, so it was invisible to the key by construction — the one place where
"keyed" was a promise the code did not keep.

AIDEV-NOTE: the trap this change had to avoid is pinned by
``test_a_profile_that_cannot_authenticate_still_gets_a_hit``. Resolving the profile
early is fine; resolving the CREDENTIAL TARGET early is not, because that helper
raises 404/409/401 and those raises would preempt a cache hit — destroying the
inversion this whole ticket exists for. If you are tempted to reuse
``_credential_target_for_chat`` for the pre-cache read, that test is the one that
will stop you.
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal, cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aigateway.core.cache_ports import CACHE_UNAVAILABLE_REASON
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from aigateway.core.request_cache import GlobalRequestCacheWrite
from aigateway.plugins.anthropic_provider.auth import credential_service_for

_CHAT_PATH = "/v1/chat/completions"
_MODEL = "anthropic/claude-haiku-4-5"
_PATCH_TARGET = (
    "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion"
)

_WriteStatus = Literal["stored", "race_lost", "not_stored"]


# --- arrangement --------------------------------------------------------------


def _token_blob() -> str:
    return json.dumps(
        {
            "access_token": "sk-ant-oat01-subscription-token",
            "refresh_token": "rt",
            "expires_at_ms": int(time.time() * 1000) + 3_600_000,
            "token_type": "Bearer",
        }
    )


def _seed_credential(credential_blobs, account_id: str, *, name: str) -> None:
    """Give a profile NAME a dispatchable credential.

    WHY keyed on ``credential_name_for(account_id, name)``: once the profile exists in
    the index, ``_credential_target_for_chat`` resolves the PROFILE (not a connection),
    and injection reads the per-profile credential under that name. A miss has to
    reach a real dispatch for these tests to observe the body that was sent.
    """
    credential_blobs.write(
        credential_service_for(credential_name_for(account_id, name)),
        "default",
        _token_blob(),
    )


def _seed_profile(
    credential_blobs,
    account_id: str,
    *,
    name: str,
    defaults: ProfileDefaults,
    state: ProfileState = ProfileState.AUTHENTICATED,
) -> None:
    async def _upsert() -> None:
        idx = ProfileIndexStore(credential_store=credential_blobs.store)
        await idx.upsert(
            Profile(
                id=profile_id_for(account_id, "anthropic", name),
                account_id=account_id,
                provider="anthropic",
                name=name,
                state=state,
                defaults=defaults,
            )
        )

    import asyncio

    asyncio.run(_upsert())


def _bare_body(**overrides) -> dict[str, Any]:
    """The whole point: a body that names nothing but the model and the question."""
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": "how many primes below one hundred?"}],
    }
    body.update(overrides)
    return body


class _Dispatch:
    """Records every body that actually reached the provider."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, body):
        # An INSTANCE patched over the method is not a descriptor, so it is called
        # with the body alone — no ``self`` from the plugin.
        self.bodies.append(json.loads(json.dumps(body, default=str)))
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"resp-{len(self.bodies)}",
                "choices": [
                    {
                        "message": {"content": f"ANSWER-{len(self.bodies)}"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )


class _Store:
    """The frozen store contract, in memory (mirrors test_chat_global_cache_route)."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def cache_available(self) -> bool:
        return True

    async def get_global(self, key_hash: str) -> dict[str, Any] | None:
        return self.rows.get(key_hash)

    async def set_if_absent(self, entry: GlobalRequestCacheWrite) -> _WriteStatus:
        if entry.key_hash in self.rows:
            return "race_lost"
        self.rows[entry.key_hash] = entry.response
        return "stored"


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


def _install(client: TestClient, store: _Store) -> _Store:
    cast(Any, client.app).state.request_cache_store = store
    return store


def _post(client: TestClient, body: dict[str, Any], *, profile: str):
    return client.post(_CHAT_PATH, json=body, headers={"X-Profile": profile})


def _system_contents(body: dict[str, Any]) -> list[str]:
    return [m["content"] for m in body.get("messages", []) if m.get("role") == "system"]


# --- the wrong-hit class ruling 57 closes -------------------------------------


def test_two_profiles_with_different_system_prompts_do_not_share_a_key(
    credential_blobs, cache_client
) -> None:
    """THE test. Same bare body, different stored prompt, and the second must MISS.

    Before ruling 57 the merge ran AFTER the lookup, so both callers keyed on the
    identical bare body: the second got the first's answer and its own system prompt
    was silently dropped. That is a WRONG ANSWER, not a cheaper one — the caller
    cannot tell, because the response looks like a perfectly good completion.

    INVARIANT: the key covers the effective request, so a stored default that changes
    what the provider is asked also changes the key.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="pirate")
    _seed_credential(credential_blobs, account_id, name="legal")
    _seed_profile(
        credential_blobs,
        account_id,
        name="pirate",
        defaults=ProfileDefaults(system_prompt="you are a pirate"),
    )
    _seed_profile(
        credential_blobs,
        account_id,
        name="legal",
        defaults=ProfileDefaults(system_prompt="you are a formal legal assistant"),
    )
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with patch(_PATCH_TARGET, new=dispatch):
        first = _post(cache_client, _bare_body(), profile="pirate")
        second = _post(cache_client, _bare_body(), profile="legal")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.headers["X-AIGW-Cache"] == "miss"
    # The regression: this read "hit" before ruling 57.
    assert second.headers["X-AIGW-Cache"] == "miss", (
        "the second profile was served the first profile's answer; its own system "
        "prompt was discarded"
    )
    assert first.headers["X-AIGW-Cache-Key"] != second.headers["X-AIGW-Cache-Key"]
    assert len(store.rows) == 2

    # Each dispatch carried its OWN prompt — the half that makes the miss correct
    # rather than merely different.
    assert len(dispatch.bodies) == 2
    assert _system_contents(dispatch.bodies[0]) == ["you are a pirate"]
    assert _system_contents(dispatch.bodies[1]) == ["you are a formal legal assistant"]


def test_a_bare_row_filled_without_defaults_is_not_served_to_a_profile_that_has_them(
    credential_blobs, cache_client
) -> None:
    """The same defect from the other direction: the FIRST caller has no defaults.

    Order matters for a first-fill bug, so both directions are pinned. Here the row is
    filled by a profile with nothing stored, and the profile WITH a system prompt must
    not be served it.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="plain")
    _seed_credential(credential_blobs, account_id, name="pirate")
    _seed_profile(credential_blobs, account_id, name="plain", defaults=ProfileDefaults())
    _seed_profile(
        credential_blobs,
        account_id,
        name="pirate",
        defaults=ProfileDefaults(system_prompt="you are a pirate"),
    )
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with patch(_PATCH_TARGET, new=dispatch):
        first = _post(cache_client, _bare_body(), profile="plain")
        second = _post(cache_client, _bare_body(), profile="pirate")

    assert first.headers["X-AIGW-Cache"] == "miss"
    assert second.headers["X-AIGW-Cache"] == "miss"
    assert len(store.rows) == 2
    assert _system_contents(dispatch.bodies[0]) == []
    assert _system_contents(dispatch.bodies[1]) == ["you are a pirate"]


# --- the half that must NOT regress: sharing is still global ------------------


def test_the_same_effective_request_shares_a_row_however_the_value_arrived(
    credential_blobs, cache_client
) -> None:
    """Ruling 57 keys the EFFECTIVE request — not the provenance of its values.

    One caller types the system message into the body; the other has it in a stored
    default. The two requests are the same question, so they must SHARE the row. This
    is the test that would fail if the fix had keyed "which profile asked" instead of
    "what was asked" — the cheap wrong fix that also passes every test above.

    INVARIANT: profile identity, the profile NAME and the account are absent from the
    key. Only the resulting request is in it.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="explicit")
    _seed_credential(credential_blobs, account_id, name="stored")
    _seed_profile(credential_blobs, account_id, name="explicit", defaults=ProfileDefaults())
    _seed_profile(
        credential_blobs,
        account_id,
        name="stored",
        defaults=ProfileDefaults(system_prompt="be terse"),
    )
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    spelled_out = _bare_body()
    spelled_out["messages"] = [
        {"role": "system", "content": "be terse"},
        *spelled_out["messages"],
    ]

    with patch(_PATCH_TARGET, new=dispatch):
        first = _post(cache_client, spelled_out, profile="explicit")
        second = _post(cache_client, _bare_body(), profile="stored")

    assert first.headers["X-AIGW-Cache"] == "miss"
    assert second.headers["X-AIGW-Cache"] == "hit", (
        "two identical effective requests were keyed apart; the fix keyed provenance "
        "rather than the request"
    )
    assert first.headers["X-AIGW-Cache-Key"] == second.headers["X-AIGW-Cache-Key"]
    assert len(store.rows) == 1
    # The hit dispatched nothing — one provider call served both callers.
    assert len(dispatch.bodies) == 1


# --- the trap: a profile that cannot authenticate is still served -------------


@pytest.mark.parametrize(
    ("profile_name", "state"),
    [
        ("ghost", None),
        ("waiting", ProfileState.PENDING),
        ("broken", ProfileState.ERROR),
    ],
    ids=["absent", "pending", "errored"],
)
def test_a_profile_that_cannot_authenticate_still_gets_a_hit(
    credential_blobs, cache_client, profile_name: str, state: ProfileState | None
) -> None:
    """REGRESSION GUARD for the trap ruling 57 had to avoid.

    ``_credential_target_for_chat`` raises 404 for an absent profile, 409 for a PENDING
    one and 401 for an ERRORED one. Reusing it for the pre-cache read — the obvious
    implementation — would let all three PREEMPT a cache hit, and a caller who is
    served today would start getting an error. That is the headline invariant of the
    whole ticket, and before this test nothing in the suite covered it.

    The three cases are served here WITHOUT any credential of their own: the row was
    filled by a different profile entirely.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="plain")
    _seed_profile(credential_blobs, account_id, name="plain", defaults=ProfileDefaults())
    if state is not None:
        _seed_profile(
            credential_blobs,
            account_id,
            name=profile_name,
            defaults=ProfileDefaults(),
            state=state,
        )
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with patch(_PATCH_TARGET, new=dispatch):
        filled = _post(cache_client, _bare_body(), profile="plain")
        served = _post(cache_client, _bare_body(), profile=profile_name)

    assert filled.headers["X-AIGW-Cache"] == "miss"
    assert served.status_code == 200, served.text
    assert served.headers["X-AIGW-Cache"] == "hit"
    assert served.json()["choices"][0]["message"]["content"] == "ANSWER-1"
    assert len(store.rows) == 1
    assert len(dispatch.bodies) == 1


# --- transport-only defaults stay out of the key -----------------------------


def test_a_timeout_default_changes_no_key_and_causes_no_bypass(
    credential_blobs, cache_client
) -> None:
    """``timeout_seconds`` reaches the body as ``timeout``, which the key IGNORES.

    This is the one profile default that is transport rather than content, and it is
    the reason ruling 57 needed no new disposition: ``timeout`` is already in
    ``EXCLUDED_TRANSPORT_FIELDS``, so the key skips it with a ``continue`` instead of
    bypassing on it. Two callers who differ only in timeout are asking the same
    question and must share the answer.

    INVARIANT: the "zero ``transport_only`` cache dispositions" property still holds —
    nothing was added to the parameter contract to make this pass.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="plain")
    _seed_credential(credential_blobs, account_id, name="slow")
    _seed_profile(credential_blobs, account_id, name="plain", defaults=ProfileDefaults())
    _seed_profile(
        credential_blobs,
        account_id,
        name="slow",
        defaults=ProfileDefaults(timeout_seconds=9.0),
    )
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with patch(_PATCH_TARGET, new=dispatch):
        first = _post(cache_client, _bare_body(), profile="plain")
        second = _post(cache_client, _bare_body(), profile="slow")

    assert first.headers["X-AIGW-Cache"] == "miss"
    assert second.headers["X-AIGW-Cache"] == "hit"
    assert second.headers["X-AIGW-Cache-Reason"] == ""
    assert first.headers["X-AIGW-Cache-Key"] == second.headers["X-AIGW-Cache-Key"]
    assert len(store.rows) == 1


def test_a_timeout_default_still_reaches_the_provider_on_a_miss(
    credential_blobs, cache_client
) -> None:
    """Excluded from the KEY is not excluded from the REQUEST.

    A field the key ignores must still be dispatched, or "ignored" would quietly mean
    "dropped" — and the operator's configured timeout would stop applying.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="slow")
    _seed_profile(
        credential_blobs,
        account_id,
        name="slow",
        defaults=ProfileDefaults(timeout_seconds=9.0),
    )
    _install(cache_client, _Store())
    dispatch = _Dispatch()

    with patch(_PATCH_TARGET, new=dispatch):
        response = _post(cache_client, _bare_body(), profile="slow")

    assert response.headers["X-AIGW-Cache"] == "miss"
    assert dispatch.bodies[0]["timeout"] == 9.0


# --- the merge runs exactly once ---------------------------------------------


def test_a_miss_dispatches_exactly_one_system_message(credential_blobs, cache_client) -> None:
    """A tripwire for a SECOND merge, pinning idempotence that already holds.

    AIDEV-NOTE: this is not a live bug. ``_apply_defaults`` is already idempotent —
    ``_has_system_message`` blocks a second prepend and ``gateway_field not in body``
    blocks a second scalar write — so a stray re-merge would produce no visible change
    HERE. It is pinned because ruling 57 moved the merge, and a future author restoring
    the old Stage 2 call site without removing the new one would get no failure from
    the header assertions above.

    The sharper consequence of a double merge is already covered elsewhere: a second
    call returns an EMPTY written-paths set, which would overwrite ``default_paths``
    and misattribute a rejected profile default to the caller — the contract
    ``test_chat_profile_default_validation`` asserts.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="pirate")
    _seed_profile(
        credential_blobs,
        account_id,
        name="pirate",
        defaults=ProfileDefaults(system_prompt="you are a pirate"),
    )
    _install(cache_client, _Store())
    dispatch = _Dispatch()

    with patch(_PATCH_TARGET, new=dispatch):
        response = _post(cache_client, _bare_body(), profile="pirate")

    assert response.headers["X-AIGW-Cache"] == "miss"
    assert _system_contents(dispatch.bodies[0]) == ["you are a pirate"]


# --- the fail-safe direction --------------------------------------------------


def test_an_unreadable_profile_index_bypasses_the_cache_and_still_dispatches_defaults(
    credential_blobs, cache_client
) -> None:
    """A failed defaults read must cost a cache hit, never a wrong hit or a dropped default.

    Two halves, and both matter.

    BYPASS, not empty defaults: carrying on with ``ProfileDefaults()`` after a failed
    read would key the BARE body while dispatching the profile's real prompt — which is
    the wrong-hit class ruling 57 exists to close, manufactured by the error path. And
    a bypass rather than a miss, because v2 rows never expire: writing under a key
    built from an incomplete body would poison that key permanently.

    STILL DISPATCHES: the request must go out with the operator's defaults applied. A
    transient index fault may cost a cache hit; it may not silently change what the
    provider is asked.
    """
    account_id = cache_client.get("/v1/auth/me").json()["id"]
    _seed_credential(credential_blobs, account_id, name="pirate")
    _seed_profile(
        credential_blobs,
        account_id,
        name="pirate",
        defaults=ProfileDefaults(system_prompt="you are a pirate"),
    )
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    real_get = ProfileIndexStore.get
    calls = {"n": 0}

    async def _flaky_get(self, *args, **kwargs):
        # Fails the FIRST read only — the pre-cache one. Modelling a permanent fault
        # would only prove that Stage 2 also fails, which is a different test.
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the profile index blob could not be decoded")
        return await real_get(self, *args, **kwargs)

    with patch(_PATCH_TARGET, new=dispatch), patch.object(ProfileIndexStore, "get", _flaky_get):
        response = _post(cache_client, _bare_body(), profile="pirate")

    assert response.status_code == 200, response.text
    assert response.headers["X-AIGW-Cache"] == "bypass"
    assert response.headers["X-AIGW-Cache-Reason"] == CACHE_UNAVAILABLE_REASON
    # INVARIANT: a bypass never writes.
    assert store.rows == {}
    assert _system_contents(dispatch.bodies[0]) == ["you are a pirate"]
