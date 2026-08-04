"""OME-305 — what a MISS is allowed to make permanent, and why a closed gate closed.

FEATURE: one globally shared exact-request cache whose rows never expire. That single
design choice is what makes these two subjects worth their own module: with
``expires_at = NULL`` every fill decision is a permanent decision, so "should this be
stored" carries the weight that "how long should this live" used to.

STORY: as a benchmark operator a run that was cut off mid-answer does not poison the
shared corpus, and when the cache stops serving I can tell from the response header
whether I turned it off or my worker is broken.

AIDEV-NOTE: split out of ``test_chat_global_cache_route.py`` (already 724 lines)
rather than appended to it. The plain helpers are imported from there because the
fake store models the frozen contract and there must be exactly one of it — two
copies would drift, and the point of that fake is that it is the contract.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aigateway.core.request_cache.global_plan import BYPASS_DISABLED

from .test_chat_global_cache_route import (
    _CHAT_PATH,
    _PATCH_TARGET,
    _arrange_account,
    _chat_body,
    _ContractStore,
    _install,
)


@pytest.fixture
def _cache_env(monkeypatch) -> None:
    # AIDEV-NOTE: a SEPARATE fixture, not a setenv in ``cache_on``'s body. ``client``
    # builds the app and reads settings once, so an env var set after it is requested
    # has no effect — the switch would silently stay off and every reason assertion
    # below would read ``disabled`` and look correct. Declaring it as a
    # dependency is what orders it ahead of app construction.
    monkeypatch.setenv("AIGW_REQUEST_CACHE_ENABLED", "true")


@pytest.fixture
def cache_on(_cache_env, client: TestClient) -> TestClient:
    """An authenticated client whose OPERATOR switch is on."""
    return _login(client)


@pytest.fixture
def cache_off(client: TestClient) -> TestClient:
    """An authenticated client whose operator switch is at its default: OFF."""
    return _login(client)


def _login(client: TestClient) -> TestClient:
    response = client.post(
        "/v1/auth/login", json={"username": "admin", "password": "test-admin-password"}
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    return client


class _ShapedDispatch:
    """Returns one canned completion whose ``choices`` the caller dictates.

    A callable INSTANCE, not a function: patching a class attribute with a plain
    function makes it a descriptor that would also receive ``self``.
    """

    def __init__(self, choices: Any) -> None:
        self._choices = choices
        self.calls = 0

    async def __call__(self, body: dict[str, Any]) -> Any:
        self.calls += 1
        return SimpleNamespace(model_dump=lambda: {"id": "resp-1", "choices": self._choices})


# --- what a miss may make permanent -------------------------------------------

_WHOLE = [{"message": {"content": "42"}, "finish_reason": "stop"}]
_TRUNCATED = [{"message": {"content": "4"}, "finish_reason": "length"}]
_NULL_REASON = [{"message": {"content": "4"}, "finish_reason": None}]
_ABSENT_REASON = [{"message": {"content": "4"}}]
_NO_MESSAGE = [{"delta": {"content": "4"}, "finish_reason": "stop"}]


@pytest.mark.parametrize(
    ("choices", "expected_write", "expected_rows"),
    [
        (_WHOLE, "stored", 1),
        (_TRUNCATED, "stored", 1),
        (_NULL_REASON, "not_stored", 0),
        (_ABSENT_REASON, "not_stored", 0),
        (_NO_MESSAGE, "not_stored", 0),
        ([], "not_stored", 0),
        (None, "not_stored", 0),
        ("not-a-list", "not_stored", 0),
    ],
    ids=[
        "finish_reason-stop-is-a-whole-answer",
        "finish_reason-length-is-a-whole-answer",
        "explicit-null-finish_reason",
        "absent-finish_reason",
        "a-choice-carrying-no-message",
        "an-empty-choices-list",
        "no-choices-key-at-all",
        "choices-that-is-not-a-list",
    ],
)
def test_only_a_structurally_whole_answer_becomes_the_permanent_cache_entry(
    choices, expected_write, expected_rows, credential_blobs, cache_on
) -> None:
    """The owner's ruling on plan U5's "partial responses", as a BOUNDARY set.

    INVARIANT: a v2 row has ``expires_at = NULL``. A truncated or half-built
    completion stored once is served to every later caller of that body forever —
    under v1 the same mistake aged out within the hour, so this guard carries weight
    the v1 code path never had to.

    WHY both "stored" cases are here and not just the refusals: a guard that refused
    everything would pass a rejection-only suite while silently disabling the entire
    cache, which is the exact failure this ticket has already been bitten by. The
    ``stop`` case proves the guard admits a normal answer.

    WHY ``finish_reason: "length"`` IS stored: the truncation is the CORRECT answer to
    the request that was sent. The caller set ``max_tokens``; a later caller sending
    the identical body wants that same truncated answer.

    AIDEV-NOTE: the ``length`` case above is sound ONLY because ``max_tokens`` is
    KEYED (owner decision B). If a future change gives ``max_tokens``
    ``cache_behavior="bypass"``, two callers with different ceilings collapse onto one
    key and whoever asked for 4000 tokens is served the answer that stopped at 20 — a
    WRONG-HIT class. Un-keying ``max_tokens`` must revisit this case in the same
    commit; do not simply update the expectation here.

    INVARIANT in every case: the caller is SERVED. Refusing to store may never cost
    an answer, only an entry.
    """
    _arrange_account(cache_on, credential_blobs)
    store = _install(cache_on, _ContractStore())
    dispatch = _ShapedDispatch(choices)

    with patch(_PATCH_TARGET, dispatch):
        resp = cache_on.post(_CHAT_PATH, json=_chat_body())

    assert resp.status_code == 200, resp.text
    assert resp.json()["choices"] == choices
    assert dispatch.calls == 1
    assert resp.headers["X-AIGW-Cache"] == "miss"
    assert resp.headers["X-AIGW-Cache-Write"] == expected_write
    assert len(store.rows) == expected_rows


def test_an_incomplete_response_is_re_dispatched_rather_than_answered_from_cache(
    credential_blobs, cache_on
) -> None:
    """The consequence of the refusal, stated as behaviour rather than as a header.

    WHY this is a separate test from the boundary set above: ``not_stored`` on one
    request is only meaningful if the NEXT identical request still reaches the
    provider. A guard that reported ``not_stored`` while quietly filling anyway would
    pass every assertion in the parametrized case and be exactly wrong.
    """
    _arrange_account(cache_on, credential_blobs)
    store = _install(cache_on, _ContractStore())
    dispatch = _ShapedDispatch(_ABSENT_REASON)

    with patch(_PATCH_TARGET, dispatch):
        first = cache_on.post(_CHAT_PATH, json=_chat_body())
        second = cache_on.post(_CHAT_PATH, json=_chat_body())

    assert first.headers["X-AIGW-Cache"] == "miss"
    assert second.headers["X-AIGW-Cache"] == "miss", "an unstored answer must not become a hit"
    assert dispatch.calls == 2
    assert store.rows == {}


# --- why the gate is closed (E4) ----------------------------------------------


def test_an_enabled_cache_with_unavailable_store_reports_cache_unavailable_not_disabled(
    credential_blobs, cache_on
) -> None:
    _arrange_account(cache_on, credential_blobs)
    store = _install(cache_on, _ContractStore(available=False))

    with patch(_PATCH_TARGET, _ShapedDispatch(_WHOLE)):
        resp = cache_on.post(_CHAT_PATH, json=_chat_body())

    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "bypass"
    assert resp.headers["X-AIGW-Cache-Reason"] == "cache_unavailable"
    assert store.set_calls == []


def test_an_operator_who_turned_the_cache_off_still_reports_disabled(
    credential_blobs, cache_off
) -> None:
    """The other half of the pair, and the one that keeps the split honest.

    WHY a PAIR: a change that simply renamed the closed-gate reason to
    ``cache_unavailable`` would satisfy the degraded test on its own while telling
    every operator who deliberately switched the cache off that their worker is
    broken. Only the two together prove the reason DISCRIMINATES.
    """
    _arrange_account(cache_off, credential_blobs)
    store = _install(cache_off, _ContractStore(available=False))

    with patch(_PATCH_TARGET, _ShapedDispatch(_WHOLE)):
        resp = cache_off.post(_CHAT_PATH, json=_chat_body())

    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache"] == "bypass"
    assert resp.headers["X-AIGW-Cache-Reason"] == BYPASS_DISABLED
    assert store.set_calls == []


def test_a_missing_response_encryption_key_does_not_disable_an_enabled_cache(
    credential_blobs, cache_on
) -> None:
    _arrange_account(cache_on, credential_blobs)
    store = _install(cache_on, _ContractStore(available=False))
    settings = cast(Any, cache_on.app).state.settings
    assert settings.secret_provider == "local", "the refusal under test is local-provider only"
    settings.secret_key = None

    with patch(_PATCH_TARGET, _ShapedDispatch(_WHOLE)):
        resp = cache_on.post(_CHAT_PATH, json=_chat_body())

    assert resp.status_code == 200, resp.text
    assert resp.headers["X-AIGW-Cache-Reason"] == "cache_unavailable"
    assert store.set_calls == []
