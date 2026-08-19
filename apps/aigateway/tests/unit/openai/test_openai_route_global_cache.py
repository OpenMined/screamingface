"""OME-884 — direct OpenAI through the global exact-request cache, at the ROUTE.

FEATURE: `openai/*` traffic participates in the one globally shared exact-request
cache. Two callers whose EFFECTIVE requests are identical share one stored OpenAI
response; two whose are not, never do.

STORY: as a benchmark operator I re-run a suite from a second account and the identical
calls are served from the first run's responses — the second account holds no OpenAI
key, is never asked for one, and no OpenAI credential is read or decrypted to serve it.

INVARIANT under test (owner-approved MVP): ``default_models`` is the BOOTSTRAP CATALOG,
not an allowlist. Publication governs ``/v1/models`` and nothing else — an unlisted
route-valid model dispatches and caches exactly like a published one, and unpublishing
a model neither refuses a direct call nor destroys a stored row.

AIDEV-NOTE: these are the ROUTE proofs, and only those. The pure key material lives in
``test_openai_global_cache_projection.py`` and the wire in ``test_openai_dispatch.py``;
nothing here asserts on a projection dict or an HTTP payload, and nothing there builds
an app. Split from ``test_openai_gateway_acceptance.py`` — that file owns the catalog
and pre-credential rejection contract, which is a different responsibility and would
have been pushed past the repo's file-size guidance by this suite.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from litellm.exceptions import NotFoundError

from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.core.request_cache import RequestCacheWrite
from aigateway.core.request_cache.global_controls import BYPASS_OPTED_OUT

_CHAT_PATH = "/v1/chat/completions"
_KEY = "sk-openai-synthetic-route-cache-key-1234"

# A model the bootstrap catalog publishes, and one that is route-valid but absent from
# it. The whole point of this suite is that the cache cannot tell them apart.
_PUBLISHED = "openai/gpt-5.6-sol"
_UNLISTED = "openai/gpt-4o-2024-11-20"

_WriteStatus = Literal["stored", "race_lost", "not_stored"]


# --- arrangement --------------------------------------------------------------


@dataclass
class _ValidValidationService:
    async def validate(self, _plugin, _provider: str, _api_key: str) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
            probe_model="openai/gpt-5-nano",
        )


class _Store:
    """The frozen store contract in memory, recording every read and write.

    WHY the reads are recorded and not just the rows: "did not store" and "never
    looked" are different failures. A bypass must do NEITHER, and only the read log
    can tell a bypass apart from a miss that stored nothing.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.reads: list[str] = []
        self.writes: list[RequestCacheWrite] = []

    def cache_available(self) -> bool:
        return True

    async def get(self, key_hash: str) -> dict[str, Any] | None:
        self.reads.append(key_hash)
        return self.rows.get(key_hash)

    async def set_if_absent(self, entry: RequestCacheWrite) -> _WriteStatus:
        self.writes.append(entry)
        if entry.key_hash in self.rows:
            return "race_lost"
        self.rows[entry.key_hash] = entry.response
        return "stored"


class _Dispatch:
    """Records every body that actually reached the provider, and answers uniquely."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, body):
        # An INSTANCE patched over the method is not a descriptor, so it is called with
        # the body alone — no ``self`` from the plugin.
        self.bodies.append(json.loads(json.dumps(body, default=str)))
        payload = {
            "id": f"resp-{len(self.bodies)}",
            "choices": [
                {
                    "message": {"content": f"ANSWER-{len(self.bodies)}"},
                    "finish_reason": "stop",
                }
            ],
        }
        return SimpleNamespace(model_dump=lambda: payload)


@pytest.fixture
def _cache_env(monkeypatch):
    # INVARIANT: listed BEFORE ``client`` in every dependent fixture, so the operator
    # switch is in the environment before the app is constructed. Set afterwards it
    # would be read as off and every test below would pass for the wrong reason —
    # which is why each one also positively asserts a non-``bypass`` status.
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


def _dispatching(client: TestClient, dispatch: Any):
    """Patch ``chat_completion`` on the exact plugin INSTANCE the app dispatches through.

    AIDEV-NOTE: resolving the plugin from the registry, rather than patching
    ``OpenAIProviderPlugin.chat_completion`` on the class, is what makes these tests say
    what they mean — the object under test is the one the route will actually call, not
    every instance that happens to share its class.

    It also stays immune to a hazard this directory has already hit once: the registry
    holds a single module-level ``PLUGIN`` singleton, and
    ``monkeypatch.setattr(plugin, "chat_completion", ...)`` on it does NOT undo cleanly —
    pytest reads the old value with ``getattr`` (which resolves through the class) and
    restores it with ``setattr``, permanently installing the original bound method as an
    instance attribute that shadows any later class-level patch. That leak has since been
    fixed at its source (``test_openai_persistence`` now uses scoped ``patch.object`` and
    asserts ``"chat_completion" not in vars(plugin)`` afterwards), so this helper no
    longer works around anything — but ``patch.object`` is still the right tool, because
    it inspects ``__dict__`` and removes exactly what it added.
    """
    plugin = cast(Any, client.app).state.providers.get("openai")
    return patch.object(plugin, "chat_completion", new=dispatch)


def _seed_profile(
    client: TestClient, *, name: str = "default", defaults: dict[str, Any] | None = None
) -> None:
    """Give the caller a dispatchable direct-OpenAI profile, optionally with defaults."""
    cast(Any, client.app).state.api_key_validation_service = _ValidValidationService()
    payload: dict[str, Any] = {"api_key": _KEY}
    if defaults is not None:
        payload["defaults"] = defaults
    created = client.put(f"/v1/auth/openai/profiles/{name}/api-key", json=payload)
    assert created.status_code == 200, created.text


def _body(
    *, model: str = _PUBLISHED, question: str = "how many primes below one hundred?", **extra
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
    }
    body.update(extra)
    return body


def _post(client: TestClient, body: dict[str, Any], *, profile: str | None = None):
    headers = {"X-Profile": profile} if profile is not None else {}
    return client.post(_CHAT_PATH, json=body, headers=headers)


def _system_contents(body: dict[str, Any]) -> list[str]:
    return [m["content"] for m in body.get("messages", []) if m.get("role") == "system"]


def _listed_models(client: TestClient) -> set[str]:
    listing = client.get("/v1/models")
    assert listing.status_code == 200, listing.text
    return {row["id"] for row in listing.json()["data"]}


# --- the ordinary lane: miss, store, replay -----------------------------------


def test_a_published_model_misses_stores_and_then_replays(cache_client) -> None:
    """The headline behavior: one OpenAI call answers two identical requests.

    Before OME-884 direct OpenAI inherited the base ``CacheBypass``, so this second
    request always dispatched. The row's provenance columns are asserted too — a row
    filed under the wrong provider or model is unreachable by every future replay.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        first = _post(cache_client, _body())
        second = _post(cache_client, _body())

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert first.headers["X-AIGW-Cache-Write"] == "stored"
    assert second.headers["X-AIGW-Cache"] == "hit"
    assert first.headers["X-AIGW-Cache-Key"] == second.headers["X-AIGW-Cache-Key"]
    assert len(dispatch.bodies) == 1, "the replay dispatched to OpenAI"
    assert len(store.rows) == 1
    assert [(write.provider, write.model) for write in store.writes] == [("openai", _PUBLISHED)]
    assert second.json()["choices"][0]["message"]["content"] == "ANSWER-1"


def test_a_model_outside_the_published_catalog_caches_exactly_like_a_published_one(
    cache_client,
) -> None:
    """Catalog != allowlist, in the cache as well as at dispatch.

    INVARIANT: ``default_models`` decides what ``/v1/models`` advertises. It decides
    nothing about what may be sent, dispatched, keyed or replayed.
    """
    assert _UNLISTED not in _listed_models(cache_client)
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        first = _post(cache_client, _body(model=_UNLISTED))
        second = _post(cache_client, _body(model=_UNLISTED))

    assert first.status_code == 200, first.text
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert first.headers["X-AIGW-Cache-Write"] == "stored"
    assert second.headers["X-AIGW-Cache"] == "hit"
    assert len(dispatch.bodies) == 1
    assert dispatch.bodies[0]["model"] == _UNLISTED
    assert [write.model for write in store.writes] == [_UNLISTED]


def test_different_models_and_different_questions_never_share_a_row(cache_client) -> None:
    """Three requests that differ in exactly one place each get three keys."""
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    variants = [_body(), _body(model=_UNLISTED), _body(question="an entirely different question")]

    with _dispatching(cache_client, dispatch):
        responses = [_post(cache_client, variant) for variant in variants]

    assert [r.status_code for r in responses] == [200, 200, 200]
    assert [r.headers["X-AIGW-Cache"] for r in responses] == ["miss", "miss", "miss"]
    assert len({r.headers["X-AIGW-Cache-Key"] for r in responses}) == 3
    assert len(store.rows) == 3
    assert len(dispatch.bodies) == 3


def test_two_max_tokens_ceilings_never_share_a_row(cache_client) -> None:
    """``max_tokens`` is KEYED, so a truncated answer never answers a roomier request.

    INVARIANT (the reason the rule may not go back to ``bypass``): the cache stage
    deliberately stores a ``finish_reason: "length"`` response, because a truncation is
    the correct answer to the request that asked for it. Un-key the ceiling and the
    caller asking for 4000 tokens is served the answer that stopped at 64.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        tight = _post(cache_client, _body(max_tokens=64))
        roomy = _post(cache_client, _body(max_tokens=4000))
        again = _post(cache_client, _body(max_tokens=64))

    assert [tight.headers["X-AIGW-Cache"], roomy.headers["X-AIGW-Cache"]] == ["miss", "miss"]
    assert tight.headers["X-AIGW-Cache-Key"] != roomy.headers["X-AIGW-Cache-Key"]
    assert again.headers["X-AIGW-Cache"] == "hit"
    assert again.headers["X-AIGW-Cache-Key"] == tight.headers["X-AIGW-Cache-Key"]
    assert len(store.rows) == 2
    assert [body["max_tokens"] for body in dispatch.bodies] == [64, 4000]


def test_unpublishing_a_model_hides_the_listing_without_disabling_calls_or_replay(
    cache_client, monkeypatch
) -> None:
    """The MVP semantics an operator can actually observe.

    ``/v1/models`` reads ``register_models()`` live, so removing a seed takes effect at
    once. What must NOT take effect is any change to dispatch or to the cache: the row
    stored while the model was published still replays, and a brand-new request for the
    same unpublished model still reaches OpenAI.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        filled = _post(cache_client, _body())
    assert filled.headers["X-AIGW-Cache"] == "miss"
    assert _PUBLISHED in _listed_models(cache_client)

    plugin = cast(Any, cache_client.app).state.providers.get("openai")
    monkeypatch.setattr(
        plugin.settings,
        "default_models",
        [model for model in plugin.settings.default_models if model != _PUBLISHED],
    )

    assert _PUBLISHED not in _listed_models(cache_client)

    with _dispatching(cache_client, dispatch):
        replayed = _post(cache_client, _body())
        fresh = _post(cache_client, _body(question="asked only after unpublishing"))

    assert replayed.headers["X-AIGW-Cache"] == "hit"
    assert replayed.headers["X-AIGW-Cache-Key"] == filled.headers["X-AIGW-Cache-Key"]
    assert fresh.status_code == 200, fresh.text
    assert fresh.headers["X-AIGW-Cache"] == "miss"
    assert len(dispatch.bodies) == 2
    assert len(store.rows) == 2


# --- refusals: what must never reach, or leave, a row -------------------------


def test_a_malformed_model_never_reads_or_writes_the_cache(cache_client) -> None:
    """A model id the grammar rejects is refused locally and is invisible to the store.

    INVARIANT: the projection and ``prepare_chat_body`` share ONE predicate, so a
    request the cache would key is necessarily one dispatch would forward. This is the
    other half — an id neither will accept must not produce a read or a row.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        response = _post(cache_client, _body(model="openai/gpt 5"))

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "invalid_model"
    assert store.reads == []
    assert store.writes == []
    assert dispatch.bodies == []


def test_a_route_valid_unsupported_model_misses_is_refused_by_openai_and_stores_nothing(
    cache_client,
) -> None:
    """OpenAI is the authority on existence, and its refusal is not an answer.

    The request is eligible — it IS read from the cache — so the gateway asks OpenAI
    rather than guessing from a catalog. A 404 must leave the store exactly as it was:
    caching a refusal would make a transient or account-scoped rejection permanent for
    every caller in the deployment.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    rejection = NotFoundError(
        message="The model `gpt-does-not-exist` does not exist or you do not have access to it.",
        llm_provider="openai",
        model="gpt-does-not-exist",
        response=httpx.Response(
            404, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        ),
    )

    async def _reject(**_kwargs):
        raise rejection

    with patch("litellm.acompletion", new=_reject):
        response = _post(cache_client, _body(model="openai/gpt-does-not-exist"))

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "provider_error"
    # Sanitized: the raw provider text never reaches the caller.
    assert "gpt-does-not-exist" not in response.text
    assert len(store.reads) == 1, "the request was not even looked up"
    assert store.writes == []
    assert store.rows == {}


def test_caller_opt_out_bypasses_neither_reading_nor_filling(cache_client) -> None:
    """``cache: {"use-cache": false}`` means both directions, and leaves no trace."""
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        filled = _post(cache_client, _body())
        opted_out = _post(cache_client, {**_body(), "cache": {"use-cache": False}})

    assert filled.headers["X-AIGW-Cache"] == "miss"
    assert opted_out.status_code == 200, opted_out.text
    assert opted_out.headers["X-AIGW-Cache"] == "bypass"
    assert opted_out.headers["X-AIGW-Cache-Reason"] == BYPASS_OPTED_OUT
    assert len(store.reads) == 1, "the opt-out read the cache anyway"
    assert len(store.rows) == 1, "the opt-out filled the cache anyway"
    assert len(dispatch.bodies) == 2
    # INVARIANT: the gateway control object never reaches the provider as a parameter.
    assert "cache" not in dispatch.bodies[1]


def test_an_ambient_alias_refuses_replay_of_that_model_alone_and_preserves_the_row(
    cache_client, monkeypatch
) -> None:
    """The fill-then-poison tripwire: the row survives, but is no longer reachable.

    An entry in ``litellm.model_alias_map`` silently redirects one id to another, so a
    row stored under the requested id would be replayed while a miss dispatched
    something different — the wrong-hit class. The cache stage runs before model
    resolution and before any credential is read, so the dispatch-side 503 alone cannot
    deliver this: participation has to refuse it too.

    INVARIANT: the refusal is EXACTLY as wide as the alias. Every other model keeps its
    cache, and the poisoned model's row is left intact rather than deleted.
    """
    import litellm

    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        _post(cache_client, _body())
        _post(cache_client, _body(model=_UNLISTED))
    assert len(store.rows) == 2
    reads_before = len(store.reads)

    monkeypatch.setattr(litellm, "model_alias_map", {_PUBLISHED: "openai/gpt-4o"})

    # No dispatch patch: the request must be REFUSED by the real dispatch guard rather
    # than quietly sent into a runtime this plugin's adapter revision does not describe.
    refused = _post(cache_client, _body())
    # Snapshot BEFORE the next request: the unaffected model legitimately reads.
    reads_after_refusal = len(store.reads)
    with _dispatching(cache_client, dispatch):
        unaffected = _post(cache_client, _body(model=_UNLISTED))

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "unsafe_openai_environment"
    assert reads_after_refusal == reads_before, "the aliased model was still looked up"
    assert len(store.rows) == 2, "the stored row was destroyed rather than made unreachable"
    assert unaffected.headers["X-AIGW-Cache"] == "hit"


# --- profile defaults enter the key, provenance does not ----------------------


def test_a_profile_default_max_tokens_isolates_and_an_explicit_equal_value_shares(
    cache_client,
) -> None:
    """Two ceilings, two rows — and a caller who types the ceiling joins the row.

    INVARIANT (OME-305 ruling 57): the key covers the EFFECTIVE request, so a stored
    default is in it. It does NOT cover where the value came from, so an explicit 64
    and a defaulted 64 are one request.
    """
    _seed_profile(cache_client, name="tight", defaults={"max_tokens": 64})
    _seed_profile(cache_client, name="roomy", defaults={"max_tokens": 4000})
    _seed_profile(cache_client, name="plain")
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        tight = _post(cache_client, _body(), profile="tight")
        roomy = _post(cache_client, _body(), profile="roomy")
        explicit = _post(cache_client, _body(max_tokens=64), profile="plain")

    assert [tight.headers["X-AIGW-Cache"], roomy.headers["X-AIGW-Cache"]] == ["miss", "miss"]
    assert tight.headers["X-AIGW-Cache-Key"] != roomy.headers["X-AIGW-Cache-Key"]
    assert explicit.headers["X-AIGW-Cache"] == "hit", (
        "an explicitly sent ceiling was keyed apart from the identical stored default; "
        "the key captured provenance rather than the request"
    )
    assert explicit.headers["X-AIGW-Cache-Key"] == tight.headers["X-AIGW-Cache-Key"]
    assert len(store.rows) == 2
    assert [body["max_tokens"] for body in dispatch.bodies] == [64, 4000]


def test_two_stored_system_prompts_isolate_through_the_effective_messages(cache_client) -> None:
    """Different stored prompts ask OpenAI two different questions, so two rows."""
    _seed_profile(cache_client, name="pirate", defaults={"system_prompt": "you are a pirate"})
    _seed_profile(cache_client, name="lawyer", defaults={"system_prompt": "you are a lawyer"})
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        pirate = _post(cache_client, _body(), profile="pirate")
        lawyer = _post(cache_client, _body(), profile="lawyer")

    assert [pirate.headers["X-AIGW-Cache"], lawyer.headers["X-AIGW-Cache"]] == ["miss", "miss"]
    assert pirate.headers["X-AIGW-Cache-Key"] != lawyer.headers["X-AIGW-Cache-Key"]
    assert len(store.rows) == 2
    # The half that makes the miss CORRECT rather than merely different.
    assert _system_contents(dispatch.bodies[0]) == ["you are a pirate"]
    assert _system_contents(dispatch.bodies[1]) == ["you are a lawyer"]


# --- identity is structurally absent from the key -----------------------------


def test_a_second_account_replays_the_first_accounts_row_without_a_key_of_its_own(
    cache_client, provisioned_user_factory
) -> None:
    """The inversion this ticket exists for, across an account boundary.

    The replaying account has no OpenAI profile and no OpenAI credential. It is served
    anyway, because neither the account, the profile name nor the credential is in the
    key — the accepted, documented consequence of a globally shared cache.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        filled = _post(cache_client, _body())
    assert filled.headers["X-AIGW-Cache"] == "miss"

    provisioned_user_factory("second-account")
    login = cache_client.post(
        "/v1/auth/login",
        json={"username": "second-account", "password": "test-user-password"},
    )
    assert login.status_code == 200, login.text
    cache_client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})

    with _dispatching(cache_client, dispatch):
        replayed = _post(cache_client, _body())

    assert replayed.status_code == 200, replayed.text
    assert replayed.headers["X-AIGW-Cache"] == "hit"
    assert replayed.headers["X-AIGW-Cache-Key"] == filled.headers["X-AIGW-Cache-Key"]
    assert replayed.json()["choices"][0]["message"]["content"] == "ANSWER-1"
    assert len(dispatch.bodies) == 1
    assert len(store.rows) == 1


def test_a_hit_reads_no_openai_credential_dispatches_nothing_and_reports_no_accounting(
    cache_client, monkeypatch, caplog
) -> None:
    """What a hit must NOT do — the whole point of placing the stage before Stage 2.

    The guard allows ``aigateway:index`` because ``profile_defaults_for_key`` reads the
    profile index to build the EFFECTIVE request, which is a documented, accepted read.
    Everything under ``aigateway:openai:`` is a provider credential: reading it would
    mean decrypting a secret to serve a response that needs none.

    Also pinned here: the accounting a hit reports. Direct OpenAI contributes no usage
    strategy, so ``accounting_not_supported`` is the honest answer, and its explicit
    ``cache_reference_from_cached_response`` returning ``None`` must not be mistaken for
    a mapper FAILURE — a missing attribute would log one on every single hit.
    """
    _seed_profile(cache_client)
    store = _install(cache_client, _Store())
    dispatch = _Dispatch()

    with _dispatching(cache_client, dispatch):
        filled = _post(cache_client, _body())
    assert filled.headers["X-AIGW-Cache"] == "miss"

    credential_store = cast(Any, cache_client.app).state.credential_store
    real_read = credential_store.read

    async def guarded_read(service: str, account: str) -> str | None:
        if service.startswith("aigateway:openai:"):
            raise AssertionError("a cache hit read the OpenAI provider credential")
        return await real_read(service, account)

    monkeypatch.setattr(credential_store, "read", guarded_read)

    def _refuse(*_args, **_kwargs):
        raise AssertionError("a cache hit dispatched to OpenAI")

    with caplog.at_level(logging.WARNING, logger="aigateway.plugins.taxonomy.session"):
        with _dispatching(cache_client, _refuse):
            served = _post(cache_client, _body())

    assert served.status_code == 200, served.text
    assert served.headers["X-AIGW-Cache"] == "hit"
    assert served.json()["choices"][0]["message"]["content"] == "ANSWER-1"
    assert len(store.rows) == 1
    assert len(dispatch.bodies) == 1

    accounting = served.json()["_aigw"]["usage_accounting"]
    assert accounting["capture_status"] == "accounting_not_supported"
    assert accounting["cache"] == {"status": "hit", "reference": None}
    assert accounting["attempts"] == []
    assert accounting["observed_attempts"] == 0
    assert "cache-reference mapper" not in caplog.text
