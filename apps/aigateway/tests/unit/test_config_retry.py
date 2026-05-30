from __future__ import annotations

from aigateway.config import Settings


def test_retry_settings_defaults() -> None:
    s = Settings()
    assert s.retry_max_attempts == 3
    assert s.retry_backoff_base_seconds == 0.5
    assert s.retry_backoff_max_seconds == 8.0
    assert s.retry_max_total_wait_seconds == 30.0
    assert s.retry_jitter_seconds == 0.25


def test_retry_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIGW_RETRY_MAX_ATTEMPTS", "0")
    monkeypatch.setenv("AIGW_RETRY_MAX_WAIT", "12.5")
    s = Settings()
    assert s.retry_max_attempts == 0
    assert s.retry_max_total_wait_seconds == 12.5


def test_provider_max_concurrency_default() -> None:
    assert Settings().provider_max_concurrency == 4


def test_provider_max_concurrency_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIGW_PROVIDER_MAX_CONCURRENCY", "0")
    assert Settings().provider_max_concurrency == 0


def test_provider_concurrency_overrides_default_empty() -> None:
    assert Settings().provider_max_concurrency_overrides == {}


def test_provider_concurrency_overrides_env_json(monkeypatch) -> None:
    monkeypatch.setenv(
        "AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES",
        '{"gemini": 1, "anthropic": 8}',
    )
    s = Settings()
    assert s.provider_max_concurrency_overrides == {"gemini": 1, "anthropic": 8}
