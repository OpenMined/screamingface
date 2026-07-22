from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from uuid import UUID

import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.core.oauth.store import OAuthConnectionStore, credential_key_for
from aigateway.plugins.anthropic_provider.auth import (
    credential_service_for as anthropic_service_for,
)

_KEY_A = "sk-ant-api03-race-existing-key"
_KEY_B = "sk-ant-api03-race-replacement-key"


@dataclass
class _BlockingValidationService:
    started: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)

    async def validate(self, _plugin, _provider: str, api_key: str) -> ApiKeyValidationResult:
        if api_key == _KEY_B:
            self.started.set()
            if not await asyncio.to_thread(self.release.wait, 5):
                raise TimeoutError("replacement validation was not released")
        return ApiKeyValidationResult(
            ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )


def _connection_blob(credential_blobs, data: dict) -> dict | None:
    service = anthropic_service_for(credential_key_for(data["account_id"], data["id"]))
    raw = credential_blobs.read(service, "default")
    return None if raw is None else json.loads(raw)


def test_delete_wins_over_inflight_key_replacement(
    authenticated_client,
    credential_blobs,
) -> None:
    service = _BlockingValidationService()
    authenticated_client.app.state.api_key_validation_service = service
    created_response = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "anthropic", "label": "race", "api_key": _KEY_A},
    )
    assert created_response.status_code == 201
    created = created_response.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        replacement = executor.submit(
            authenticated_client.put,
            f"/v1/oauth/connections/{created['id']}/api-key",
            json={"api_key": _KEY_B},
        )
        assert service.started.wait(5), "replacement never reached validation"

        deleted = authenticated_client.delete(f"/v1/oauth/connections/{created['id']}")
        service.release.set()
        replaced = replacement.result(timeout=5)

    assert deleted.status_code == 204
    assert replaced.status_code == 409
    assert replaced.json()["detail"]["code"] == "connection_conflict"
    after = authenticated_client.get(f"/v1/oauth/connections/{created['id']}").json()
    # INVARIANT: an older validation result cannot undo a completed delete.
    assert after["status"] == "revoked"
    assert _connection_blob(credential_blobs, created) is None


def test_reactivation_conflict_rolls_back_replacement_blob(
    authenticated_client,
    credential_blobs,
    monkeypatch,
) -> None:
    service = _BlockingValidationService()
    service.release.set()
    authenticated_client.app.state.api_key_validation_service = service
    created_response = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "anthropic", "label": "rollback", "api_key": _KEY_A},
    )
    assert created_response.status_code == 201
    created = created_response.json()

    async def lose_reactivation_race(
        _self: OAuthConnectionStore,
        _connection,
    ) -> None:
        return None

    monkeypatch.setattr(OAuthConnectionStore, "reactivate", lose_reactivation_race)

    replaced = authenticated_client.put(
        f"/v1/oauth/connections/{created['id']}/api-key",
        json={"api_key": _KEY_B},
    )

    assert replaced.status_code == 409
    assert replaced.json()["detail"]["code"] == "connection_conflict"
    # INVARIANT: transaction rollback restores the exact pre-replacement credential.
    assert _connection_blob(credential_blobs, created) == {
        "auth_type": "api_key",
        "api_key": _KEY_A,
    }


def test_create_connection_cancelled_after_blob_write_commits_neither_row_nor_blob(
    authenticated_client,
    credential_blobs,
    monkeypatch,
) -> None:
    """OME-307 Unit 4: create persists the key and creates the connection row in ONE
    transaction, so a cancellation AFTER the blob write but before the row commits rolls
    BOTH back.

    INVARIANT: transaction rollback — not best-effort ``except`` cleanup — is the atomicity
    mechanism. ``asyncio.CancelledError`` is a ``BaseException`` in 3.12, so an
    ``except Exception`` compensation could never drop the orphan blob; only unwinding the
    transaction boundary can. Neither an active connection-without-credential nor an orphan
    credential-without-connection may ever commit.
    """
    service = _BlockingValidationService()
    service.release.set()
    authenticated_client.app.state.api_key_validation_service = service
    account_id = authenticated_client.get("/v1/auth/me").json()["id"]

    captured: dict[str, UUID] = {}

    async def _cancel_after_blob(_self, **kwargs) -> None:
        # Row creation runs only AFTER the in-transaction credential write, so cancelling
        # here models "cancelled after the blob write, before the row commits".
        captured["connection_id"] = kwargs["connection_id"]
        raise asyncio.CancelledError

    monkeypatch.setattr(OAuthConnectionStore, "create_api_key", _cancel_after_blob)

    # The sync TestClient surfaces an in-request asyncio.CancelledError as the
    # concurrent.futures variant once it crosses the blocking-portal boundary.
    with pytest.raises(concurrent.futures.CancelledError):
        authenticated_client.post(
            "/v1/oauth/connections/api-key",
            json={"provider": "anthropic", "label": "cancelled", "api_key": _KEY_A},
        )
    assert "connection_id" in captured, "row creation never ran after the blob write"

    # Rollback dropped the in-transaction blob write — no orphan credential survived.
    blob_service = anthropic_service_for(credential_key_for(account_id, captured["connection_id"]))
    assert credential_blobs.read(blob_service, "default") is None
    # And no connection row committed (it rolled back with the blob).
    assert (
        authenticated_client.get(f"/v1/oauth/connections/{captured['connection_id']}").status_code
        == 404
    )
