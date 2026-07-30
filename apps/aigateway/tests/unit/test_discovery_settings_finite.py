"""Discovery timing controls must remain finite operational bounds."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.config import Settings


@pytest.mark.parametrize(
    "field_name",
    [
        "discovery_cache_ttl_seconds",
        "discovery_cache_stale_ttl_seconds",
        "discovery_cache_failure_ttl_seconds",
        "discovery_timeout_seconds",
    ],
)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_discovery_duration_rejects_non_finite_values(field_name: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field_name: value})


@pytest.mark.parametrize(
    "environment_name",
    [
        "AIGW_DISCOVERY_CACHE_TTL_SECONDS",
        "AIGW_DISCOVERY_CACHE_STALE_TTL_SECONDS",
        "AIGW_DISCOVERY_CACHE_FAILURE_TTL_SECONDS",
        "AIGW_DISCOVERY_TIMEOUT_SECONDS",
    ],
)
def test_discovery_duration_rejects_infinity_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
) -> None:
    monkeypatch.setenv(environment_name, "Infinity")

    with pytest.raises(ValidationError):
        Settings()


def test_discovery_zero_boundaries_match_operational_semantics() -> None:
    settings = Settings.model_validate(
        {
            "discovery_cache_stale_ttl_seconds": 0,
            "discovery_cache_failure_ttl_seconds": 0,
        }
    )

    assert settings.discovery_cache_stale_ttl_seconds == 0
    assert settings.discovery_cache_failure_ttl_seconds == 0
    with pytest.raises(ValidationError):
        Settings.model_validate({"discovery_cache_ttl_seconds": 0})
    with pytest.raises(ValidationError):
        Settings.model_validate({"discovery_timeout_seconds": 0})
