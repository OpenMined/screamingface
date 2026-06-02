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
