"""Validated process settings for the ScreamingFace engine application."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from urllib.parse import urlsplit


class SettingsError(ValueError):
    """The engine process configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 4404
    gateway_url: str = "http://127.0.0.1:9105"
    gateway_timeout: float = 120.0
    evaluation_timeout: float = 120.0
    max_inflight: int = 16
    searxng_url: str | None = None
    web_timeout: float = 20.0
    web_max_results: int = 5
    web_max_tool_calls: int = 12
    web_max_content_chars: int = 20_000
    web_max_fetch_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        if not self.host:
            raise SettingsError("URL4_HOST cannot be empty")
        if not 1 <= self.port <= 65535:
            raise SettingsError(f"URL4_PORT must be between 1 and 65535, got {self.port}")
        parsed = urlsplit(self.gateway_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SettingsError(
                f"AIGATEWAY_URL must be an absolute http(s) URL, got {self.gateway_url!r}"
            )
        if not isfinite(self.gateway_timeout) or self.gateway_timeout <= 0:
            raise SettingsError(
                f"AIGATEWAY_TIMEOUT must be a positive finite number, got {self.gateway_timeout}"
            )
        if not isfinite(self.evaluation_timeout) or self.evaluation_timeout <= 0:
            raise SettingsError(
                "SCREAMINGFACE_ENGINE_TIMEOUT must be a positive finite number, "
                f"got {self.evaluation_timeout}"
            )
        if self.max_inflight < 1:
            raise SettingsError(
                f"SCREAMINGFACE_ENGINE_MAX_INFLIGHT must be at least 1, got {self.max_inflight}"
            )
        if self.searxng_url is not None:
            _absolute_url(self.searxng_url, "SCREAMINGFACE_SEARXNG_URL")
        if not isfinite(self.web_timeout) or self.web_timeout <= 0:
            raise SettingsError(
                "SCREAMINGFACE_WEB_TIMEOUT must be a positive finite number, "
                f"got {self.web_timeout}"
            )
        _at_least_one(self.web_max_results, "SCREAMINGFACE_WEB_MAX_RESULTS")
        _at_least_one(self.web_max_tool_calls, "SCREAMINGFACE_WEB_MAX_TOOL_CALLS")
        _at_least_one(self.web_max_content_chars, "SCREAMINGFACE_WEB_MAX_CONTENT_CHARS")
        _at_least_one(self.web_max_fetch_bytes, "SCREAMINGFACE_WEB_MAX_FETCH_BYTES")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        return cls(
            host=values.get("URL4_HOST", "127.0.0.1"),
            port=_integer(values, "URL4_PORT", 4404),
            gateway_url=values.get("AIGATEWAY_URL", "http://127.0.0.1:9105").rstrip("/"),
            gateway_timeout=_number(values, "AIGATEWAY_TIMEOUT", 120.0),
            evaluation_timeout=_number(values, "SCREAMINGFACE_ENGINE_TIMEOUT", 120.0),
            max_inflight=_integer(values, "SCREAMINGFACE_ENGINE_MAX_INFLIGHT", 16),
            searxng_url=_optional_url(values, "SCREAMINGFACE_SEARXNG_URL"),
            web_timeout=_number(values, "SCREAMINGFACE_WEB_TIMEOUT", 20.0),
            web_max_results=_integer(values, "SCREAMINGFACE_WEB_MAX_RESULTS", 5),
            web_max_tool_calls=_integer(values, "SCREAMINGFACE_WEB_MAX_TOOL_CALLS", 12),
            web_max_content_chars=_integer(values, "SCREAMINGFACE_WEB_MAX_CONTENT_CHARS", 20_000),
            web_max_fetch_bytes=_integer(values, "SCREAMINGFACE_WEB_MAX_FETCH_BYTES", 2_000_000),
        )


def _integer(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise SettingsError(f"{name} must be an integer, got {value!r}") from None


def _number(env: Mapping[str, str], name: str, default: float) -> float:
    value = env.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise SettingsError(f"{name} must be a number, got {value!r}") from None


def _optional_url(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None or not value.strip():
        return None
    return value.rstrip("/")


def _absolute_url(value: str, name: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SettingsError(f"{name} must be an absolute http(s) URL, got {value!r}")


def _at_least_one(value: int, name: str) -> None:
    if value < 1:
        raise SettingsError(f"{name} must be at least 1, got {value}")


__all__ = ["Settings", "SettingsError"]
