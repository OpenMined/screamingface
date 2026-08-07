from __future__ import annotations

from aigateway.config import Settings
from aigateway.main import create_app


def _settings(*, enabled: bool) -> Settings:
    return Settings(
        **{
            "_env_file": None,
            "AIGW_REQUEST_CACHE_ENABLED": str(enabled).lower(),
        }
    )


def test_enabled_cache_is_available_without_a_response_encryption_key() -> None:
    app = create_app(settings=_settings(enabled=True))

    assert app.state.request_cache_store.cache_available() is True


def test_disabled_cache_is_unavailable() -> None:
    app = create_app(settings=_settings(enabled=False))

    assert app.state.request_cache_store.cache_available() is False


def test_response_cache_has_no_unprotected_key_acknowledgement_setting() -> None:
    assert not hasattr(_settings(enabled=True), "request_cache_accept_unprotected_key")
