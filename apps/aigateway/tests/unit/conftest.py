from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

_UNIT_ROOT = Path(__file__).resolve().parent
# AIDEV-NOTE: keep new API-key validation tests in new modules outside this frozen allowlist
# so they exercise the real validation service unless they install an explicit test double.
_LEGACY_API_KEY_ROUTE_MODULES = frozenset(
    {
        "test_api_key_routes.py",
        "test_auth_routes.py",
        "test_oauth_connection_api_key_routes.py",
        "huggingface/test_huggingface_gateway_acceptance.py",
        "openrouter/test_chat_debug_control_strip.py",
        "openrouter/test_chat_exception_boundary.py",
        "openrouter/test_openrouter_benign_error.py",
        "openrouter/test_openrouter_control_plane_isolation.py",
        "openrouter/test_openrouter_dispatch.py",
        "openrouter/test_openrouter_embedded_retry.py",
        "openrouter/test_openrouter_embedded_retry_conversion.py",
        "openrouter/test_openrouter_error_policy.py",
        "openrouter/test_openrouter_litellm_contract.py",
        "openrouter/test_openrouter_security.py",
        "openrouter/test_openrouter_toplevel_conversion_retry.py",
    }
)


@pytest.fixture(autouse=True)
def _legacy_api_key_validation_success(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative_path = Path(request.node.path).resolve().relative_to(_UNIT_ROOT).as_posix()
    if relative_path not in _LEGACY_API_KEY_ROUTE_MODULES:
        return

    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(
        _self: ApiKeyValidationService,
        _plugin: Any,
        _provider: str,
        _api_key: str,
    ) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )

    # INVARIANT: only frozen pre-OME-307 modules receive this compatibility success.
    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)
