"""Validated process settings for the ScreamingFace engine application."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from math import isfinite
from urllib.parse import urlsplit

MAX_REQUEST_TARGET_BYTES = 61_440
H11_MAX_INCOMPLETE_EVENT_SIZE = 131_072


class SettingsError(ValueError):
    """The engine process configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 4404
    gateway_url: str = "http://127.0.0.1:9105"
    gateway_timeout: float = 120.0
    codex_oauth_redirect_uri: str = "http://localhost:1455/auth/callback"
    evaluation_timeout: float = 900.0
    tavily_timeout: float = 75.0
    max_inflight: int = 16
    max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES

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
        _codex_oauth_redirect(self.codex_oauth_redirect_uri)
        if not isfinite(self.evaluation_timeout) or self.evaluation_timeout <= 0:
            raise SettingsError(
                "SCREAMINGFACE_ENGINE_TIMEOUT must be a positive finite number, "
                f"got {self.evaluation_timeout}"
            )
        if not isfinite(self.tavily_timeout) or self.tavily_timeout <= 0:
            raise SettingsError(
                "SCREAMINGFACE_TAVILY_TIMEOUT must be a positive finite number, "
                f"got {self.tavily_timeout}"
            )
        if self.max_inflight < 1:
            raise SettingsError(
                f"SCREAMINGFACE_ENGINE_MAX_INFLIGHT must be at least 1, got {self.max_inflight}"
            )
        _at_least_one(
            self.max_request_target_bytes,
            "SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES",
        )
        if self.max_request_target_bytes > MAX_REQUEST_TARGET_BYTES:
            raise SettingsError(
                "SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES must not exceed "
                f"{MAX_REQUEST_TARGET_BYTES}, got {self.max_request_target_bytes}"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        return cls(
            host=values.get("URL4_HOST", "127.0.0.1"),
            port=_integer(values, "URL4_PORT", 4404),
            gateway_url=values.get("AIGATEWAY_URL", "http://127.0.0.1:9105").rstrip("/"),
            gateway_timeout=_number(values, "AIGATEWAY_TIMEOUT", 120.0),
            codex_oauth_redirect_uri=values.get(
                "SCREAMINGFACE_CODEX_OAUTH_REDIRECT_URI",
                "http://localhost:1455/auth/callback",
            ),
            evaluation_timeout=_number(values, "SCREAMINGFACE_ENGINE_TIMEOUT", 900.0),
            tavily_timeout=_number(values, "SCREAMINGFACE_TAVILY_TIMEOUT", 75.0),
            max_inflight=_integer(values, "SCREAMINGFACE_ENGINE_MAX_INFLIGHT", 16),
            max_request_target_bytes=_integer(
                values,
                "SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES",
                MAX_REQUEST_TARGET_BYTES,
            ),
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


def _codex_oauth_redirect(value: str) -> None:
    name = "SCREAMINGFACE_CODEX_OAUTH_REDIRECT_URI"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SettingsError(f"{name} must be a valid loopback URL, got {value!r}") from exc
    hostname = (parsed.hostname or "").rstrip(".").lower()
    loopback = hostname == "localhost"
    if not loopback:
        try:
            loopback = ip_address(hostname).is_loopback
        except ValueError:
            loopback = False
    valid = (
        parsed.scheme == "http"
        and parsed.username is None
        and parsed.password is None
        and loopback
        and port in {1455, 1457}
        and parsed.path == "/auth/callback"
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise SettingsError(
            f"{name} must be http://localhost:1455/auth/callback or the equivalent "
            f"loopback URL on port 1457, got {value!r}"
        )


def _at_least_one(value: int, name: str) -> None:
    if value < 1:
        raise SettingsError(f"{name} must be at least 1, got {value}")


__all__ = [
    "H11_MAX_INCOMPLETE_EVENT_SIZE",
    "MAX_REQUEST_TARGET_BYTES",
    "Settings",
    "SettingsError",
]
