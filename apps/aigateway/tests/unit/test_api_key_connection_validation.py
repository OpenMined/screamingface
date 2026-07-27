from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.core.credential_strategy_cache import credential_strategy_cache

_KEY = "sk-ant-api03-synthetic-connection-secret"


@dataclass
class _StubValidationService:
    result: ApiKeyValidationResult | None
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def validate(self, _plugin, provider: str, api_key: str):
        self.calls.append((provider, api_key))
        return self.result


@pytest.mark.parametrize(
    ("state", "status_code", "code"),
    [
        (ApiKeyValidationState.INVALID, 422, "api_key_invalid"),
        (ApiKeyValidationState.EXPIRED, 422, "api_key_expired"),
        (ApiKeyValidationState.NO_QUOTA, 402, "api_key_no_quota"),
        (ApiKeyValidationState.PERMISSION_DENIED, 403, "api_key_permission_denied"),
        (ApiKeyValidationState.RATE_LIMITED, 429, "api_key_validation_rate_limited"),
        (ApiKeyValidationState.UNAVAILABLE, 503, "api_key_validation_unavailable"),
        (ApiKeyValidationState.MISCONFIGURED, 503, "api_key_validation_misconfigured"),
    ],
)
def test_create_maps_every_non_valid_state_without_persistence(
    authenticated_client,
    state: ApiKeyValidationState,
    status_code: int,
    code: str,
) -> None:
    retry_after = 23 if state is ApiKeyValidationState.RATE_LIMITED else None
    service = _StubValidationService(
        ApiKeyValidationResult(
            state=state,
            stage=ApiKeyValidationStage.AUTHENTICATION,
            retry_after_seconds=retry_after,
        )
    )
    authenticated_client.app.state.api_key_validation_service = service

    response = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "anthropic", "label": f"state-{state}", "api_key": _KEY},
    )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert response.headers.get("retry-after") == ("23" if retry_after is not None else None)
    assert service.calls == [("anthropic", _KEY)]
    assert authenticated_client.get("/v1/oauth/connections").json()["connections"] == []


def test_create_runs_label_conflict_gate_before_validation(authenticated_client) -> None:
    service = _StubValidationService(
        ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )
    )
    authenticated_client.app.state.api_key_validation_service = service
    first = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "anthropic", "label": "duplicate", "api_key": _KEY},
    )
    assert first.status_code == 201
    service.calls.clear()

    second = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "anthropic", "label": "duplicate", "api_key": _KEY},
    )

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "label_conflict"
    assert service.calls == []


def test_unsupported_provider_gate_precedes_validation(authenticated_client) -> None:
    service = _StubValidationService(
        ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )
    )
    authenticated_client.app.state.api_key_validation_service = service

    response = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "codex", "label": "unsupported", "api_key": _KEY},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "api_key_not_supported"
    assert service.calls == []


def test_create_validation_failure_precedes_blob_and_cache_mutation(
    authenticated_client,
    monkeypatch,
) -> None:
    service = _StubValidationService(
        ApiKeyValidationResult(
            state=ApiKeyValidationState.INVALID,
            stage=ApiKeyValidationStage.AUTHENTICATION,
        )
    )
    authenticated_client.app.state.api_key_validation_service = service

    async def forbidden_write(*_args, **_kwargs):
        raise AssertionError("validation failure must not write credentials")

    def forbidden_evict(*_args, **_kwargs):
        raise AssertionError("validation failure must not evict credential cache")

    monkeypatch.setattr(authenticated_client.app.state.credential_store, "write", forbidden_write)
    monkeypatch.setattr(
        credential_strategy_cache(authenticated_client.app),
        "evict",
        forbidden_evict,
    )

    response = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "anthropic", "label": "no-side-effects", "api_key": _KEY},
    )

    assert response.status_code == 422
