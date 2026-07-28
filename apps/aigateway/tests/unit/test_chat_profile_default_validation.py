"""OME-638: a stored profile default passes the SAME contract as a caller value.

FEATURE: one effective parameter contract. The provider rule set that drives the
``/v1/models`` summary and the ``/v1/model-parameters`` detail decides what may be
dispatched — no matter whether the value came from the request or from the
operator's stored profile defaults.

STORY: as an operator I learn immediately that a profile default is not
dispatchable for this provider, instead of the gateway forwarding it past the
contract and the provider quietly discarding it; and as a caller I am never shown
a rejection for a field I did not send.

INVARIANT: profile defaults are classified against the provider's enabled rules,
schemas and resolved auth mode BEFORE provider preparation, cache planning,
credential access and dispatch — the same gate, on the same side of it, as a
caller-supplied field.
INVARIANT: the body still wins per field. A default only ever occupies a request
path the caller omitted, which is exactly what makes a rejection attributable to
the profile rather than to the request.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from aigateway.plugins.anthropic_provider.auth import credential_service_for
from aigateway.plugins.codex_provider.auth import (
    credential_service_for as codex_credential_service_for,
)
from aigateway.routes.chat import _parameter_rejection_exception

_ANTHROPIC_MODEL = "anthropic/claude-haiku-4-5"
_CODEX_MODEL = "codex/gpt-5.4-mini"


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def _token_blob() -> str:
    return json.dumps(
        {
            "access_token": "tok",
            "refresh_token": "rt",
            "id_token": "id",
            "expires_at_ms": int(time.time() * 1000) + 3_600_000,
            "token_type": "Bearer",
        }
    )


def _seed_anthropic_credential(credential_blobs, account_id: str) -> None:
    credential_blobs.write(
        credential_service_for(credential_name_for(account_id, "default")),
        "default",
        _token_blob(),
    )


def _seed_codex_credential(credential_blobs, account_id: str) -> None:
    credential_blobs.write(
        codex_credential_service_for(credential_name_for(account_id, "default")),
        "default",
        _token_blob(),
    )


async def _seed_profile(
    credential_blobs, account_id: str, *, provider: str, defaults: ProfileDefaults
) -> None:
    idx = ProfileIndexStore(credential_store=credential_blobs.store)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, provider, "default"),
            account_id=account_id,
            provider=provider,
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=defaults,
        )
    )


def _capture(store: dict[str, Any]):
    async def _fake_chat_completion(_self, body):
        store.update(body)
        return SimpleNamespace(
            model_dump=lambda: {"id": "x", "choices": [{"message": {"content": "ok"}}]}
        )

    return _fake_chat_completion


_ANTHROPIC_PLUGIN = "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin"
_CODEX_PLUGIN = "aigateway.plugins.codex_provider.plugin.CodexProviderPlugin"
_ANTHROPIC_DISPATCH = f"{_ANTHROPIC_PLUGIN}.chat_completion"
_CODEX_DISPATCH = f"{_CODEX_PLUGIN}.chat_completion"


# --- a default the provider does not enable -----------------------------------


@pytest.mark.asyncio
async def test_a_default_the_provider_does_not_enable_is_refused(
    credential_blobs, authenticated_client
) -> None:
    # Codex enables exactly ONE field, reasoning_effort (OME-634), and its
    # Responses payload builder copies a fixed key list — so before this unit a
    # default `temperature` was merged past the contract and then silently
    # discarded. A caller sending the same field has always received a 400; the
    # operator-configured path now gets the same honest answer.
    account_id = _account_id(authenticated_client)
    _seed_codex_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs, account_id, provider="codex", defaults=ProfileDefaults(temperature=0.5)
    )

    captured: dict[str, Any] = {}
    with patch(_CODEX_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _CODEX_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_profile_defaults"
    assert detail["provider"] == "codex"
    assert detail["profile"] == "default"
    assert detail["rejected"] == {"temperature": "unknown"}
    assert captured == {}


# --- a default outside the provider's own schema ------------------------------


@pytest.mark.asyncio
async def test_a_default_outside_the_provider_narrowed_schema_is_refused(
    credential_blobs, authenticated_client
) -> None:
    # 1.5 is inside the SHARED temperature schema [0, 2] and outside Anthropic's
    # real [0, 1] (OME-579). Rejecting it proves the default is validated by the
    # PROVIDER's rule — not by a generic range check that happens to exist.
    account_id = _account_id(authenticated_client)
    _seed_anthropic_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs,
        account_id,
        provider="anthropic",
        defaults=ProfileDefaults(temperature=1.5),
    )

    captured: dict[str, Any] = {}
    with patch(_ANTHROPIC_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _ANTHROPIC_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_profile_defaults"
    assert detail["rejected"] == {"temperature": "malformed"}
    assert captured == {}


@pytest.mark.asyncio
async def test_a_default_outside_the_schema_enum_is_refused(
    credential_blobs, authenticated_client
) -> None:
    # ProfileDefaults.reasoning_effort is a bare `str | None`, so the persisted
    # model accepts a value the ladder does not. The contract is what refuses it.
    account_id = _account_id(authenticated_client)
    _seed_codex_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs,
        account_id,
        provider="codex",
        defaults=ProfileDefaults(reasoning_effort="extreme"),
    )

    captured: dict[str, Any] = {}
    with patch(_CODEX_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _CODEX_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["rejected"] == {"reasoning_effort": "malformed"}
    assert captured == {}


# --- attribution ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_caller_fault_outranks_a_profile_fault(
    credential_blobs, authenticated_client
) -> None:
    # Both are broken. The caller-facing error names ONLY the caller's own field:
    # showing them `temperature`, which they never sent, would send them hunting
    # through a request that does not contain it.
    account_id = _account_id(authenticated_client)
    _seed_anthropic_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs,
        account_id,
        provider="anthropic",
        defaults=ProfileDefaults(temperature=1.5),
    )

    captured: dict[str, Any] = {}
    with patch(_ANTHROPIC_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": _ANTHROPIC_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "not_a_parameter": 1,
            },
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {"not_a_parameter": "unknown"}
    assert captured == {}


def test_the_rejection_is_attributed_to_its_real_source() -> None:
    # The attribution rule in isolation, over the three shapes the classifier can
    # produce. Keeps the route test above from being the only thing pinning it.
    from aigateway.core.parameter_projection import UnsupportedParametersError

    def _render(rejected: dict[str, str], injected: frozenset[str]) -> dict[str, Any]:
        exc = _parameter_rejection_exception(
            UnsupportedParametersError(rejected),
            provider="p",
            profile_name="default",
            default_paths=injected,
        )
        assert isinstance(exc.detail, dict)
        return exc.detail

    caller_only = _render({"a": "unknown"}, frozenset())
    assert caller_only["code"] == "unsupported_parameters"
    assert caller_only["rejected"] == {"a": "unknown"}

    profile_only = _render({"temperature": "malformed"}, frozenset({"temperature"}))
    assert profile_only["code"] == "invalid_profile_defaults"
    assert profile_only["profile"] == "default"
    assert profile_only["rejected"] == {"temperature": "malformed"}

    mixed = _render({"a": "unknown", "temperature": "malformed"}, frozenset({"temperature"}))
    assert mixed["code"] == "unsupported_parameters"
    assert mixed["rejected"] == {"a": "unknown"}


# --- ordering ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_refusal_precedes_provider_preparation_and_everything_after_it(
    credential_blobs, authenticated_client
) -> None:
    # prepare_chat_body is the EARLIEST of the four downstream steps the contract
    # must precede (chat.py: prepare < cache plan < credential injection <
    # dispatch), so a tripwire there establishes the whole ordering claim at once.
    # It is deliberately outside the route's dispatch try/except, so reaching it
    # would surface as an error rather than a sanitized 502.
    account_id = _account_id(authenticated_client)
    _seed_codex_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs, account_id, provider="codex", defaults=ProfileDefaults(temperature=0.5)
    )

    def _tripwire(_self, body):
        raise AssertionError("provider preparation ran before the parameter contract")

    with patch(f"{_CODEX_PLUGIN}.prepare_chat_body", _tripwire):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _CODEX_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_profile_defaults"


@pytest.mark.asyncio
async def test_the_refusal_precedes_credential_access(
    credential_blobs, authenticated_client
) -> None:
    # No instrumentation: the profile is AUTHENTICATED but its credential blob is
    # deliberately never written. Reaching credential injection would raise
    # CredentialNotFoundError and render 401 auth_required, so observing the 400
    # is direct evidence that no credential was read.
    account_id = _account_id(authenticated_client)
    await _seed_profile(
        credential_blobs, account_id, provider="codex", defaults=ProfileDefaults(temperature=0.5)
    )

    resp = authenticated_client.post(
        "/v1/chat/completions",
        json={"model": _CODEX_MODEL, "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_profile_defaults"


# --- the valid path is unchanged -----------------------------------------------


@pytest.mark.asyncio
async def test_a_valid_default_still_merges_and_dispatches(
    credential_blobs, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    _seed_anthropic_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs,
        account_id,
        provider="anthropic",
        defaults=ProfileDefaults(temperature=0.5, max_tokens=4096),
    )

    captured: dict[str, Any] = {}
    with patch(_ANTHROPIC_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _ANTHROPIC_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert captured["temperature"] == 0.5
    assert captured["max_tokens"] == 4096


@pytest.mark.asyncio
async def test_a_valid_default_survives_the_gate_and_its_downstream_rename(
    credential_blobs, authenticated_client
) -> None:
    # The gate runs on the REQUEST path (`reasoning_effort`); the provider's own
    # transform then renames it. Passing classification must not disturb that —
    # the default lands on the wire in the provider's shape, not the caller's.
    account_id = _account_id(authenticated_client)
    _seed_codex_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs,
        account_id,
        provider="codex",
        defaults=ProfileDefaults(reasoning_effort="medium"),
    )

    captured: dict[str, Any] = {}
    with patch(_CODEX_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _CODEX_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert captured["reasoning"] == {"effort": "medium"}
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_structural_defaults_still_need_no_rule(
    credential_blobs, authenticated_client
) -> None:
    # system_prompt -> messages and timeout_seconds -> timeout both resolve to
    # GATEWAY_OWNED_FIELDS, which the classifier authorizes structurally. Moving
    # the merge in front of classification must not start demanding rules for them.
    account_id = _account_id(authenticated_client)
    _seed_anthropic_credential(credential_blobs, account_id)
    await _seed_profile(
        credential_blobs,
        account_id,
        provider="anthropic",
        defaults=ProfileDefaults(system_prompt="be terse", timeout_seconds=12.5),
    )

    captured: dict[str, Any] = {}
    with patch(_ANTHROPIC_DISPATCH, _capture(captured)):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={"model": _ANTHROPIC_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert captured["messages"][0] == {"role": "system", "content": "be terse"}
    assert captured["timeout"] == 12.5
