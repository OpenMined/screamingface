from __future__ import annotations

import ipaddress
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
POSITIVE_DISCOVERY_TTL_SECONDS = 10.0
NEGATIVE_DISCOVERY_TTL_SECONDS = 2.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CacheEntry:
    models: list[str]
    expires_at: float


_CACHE: dict[str, _CacheEntry] = {}
_IN_FLIGHT: set[str] = set()
_CACHE_CONDITION = threading.Condition()


def clear_ollama_discovery_cache() -> None:
    with _CACHE_CONDITION:
        _CACHE.clear()
        _IN_FLIGHT.clear()
        _CACHE_CONDITION.notify_all()


def resolve_ollama_host(environ: Mapping[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = env.get("AIGW_OLLAMA_HOST") or env.get("OLLAMA_API_BASE") or DEFAULT_OLLAMA_HOST
    return _normalize_ollama_host(raw, env)


def discover_ollama_models(
    host: str | None = None,
    *,
    http_client_factory: Callable[[float], httpx.Client] | None = None,
    timeout_seconds: float = 2.0,
) -> list[str]:
    resolved_host = _normalize_ollama_host(host, os.environ) if host else resolve_ollama_host()

    while True:
        now = time.monotonic()
        with _CACHE_CONDITION:
            entry = _CACHE.get(resolved_host)
            if entry is not None and entry.expires_at > now:
                return list(entry.models)
            if resolved_host not in _IN_FLIGHT:
                _IN_FLIGHT.add(resolved_host)
                break
            _CACHE_CONDITION.wait()

    try:
        models = _fetch_ollama_models(
            resolved_host,
            http_client_factory=http_client_factory,
            timeout_seconds=timeout_seconds,
        )
        ttl = POSITIVE_DISCOVERY_TTL_SECONDS if models else NEGATIVE_DISCOVERY_TTL_SECONDS
        with _CACHE_CONDITION:
            _CACHE[resolved_host] = _CacheEntry(
                models=list(models),
                expires_at=time.monotonic() + ttl,
            )
        return models
    finally:
        with _CACHE_CONDITION:
            _IN_FLIGHT.discard(resolved_host)
            _CACHE_CONDITION.notify_all()


def _normalize_ollama_host(raw: str | None, environ: Mapping[str, str]) -> str:
    host = (raw or DEFAULT_OLLAMA_HOST).strip().rstrip("/") or DEFAULT_OLLAMA_HOST
    try:
        parsed = urlparse(host)
        parsed.port
    except ValueError:
        logger.warning(
            "Invalid Ollama host %r; falling back to %s",
            raw,
            DEFAULT_OLLAMA_HOST,
        )
        return DEFAULT_OLLAMA_HOST
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        logger.warning(
            "Invalid Ollama host %r; falling back to %s",
            raw,
            DEFAULT_OLLAMA_HOST,
        )
        return DEFAULT_OLLAMA_HOST

    hostname = parsed.hostname
    if _is_loopback_hostname(hostname):
        return host

    if environ.get("AIGW_OLLAMA_ALLOW_REMOTE") == "1":
        logger.warning(
            "Using non-loopback Ollama host %s; prompts and process-owned OLLAMA_API_KEY "
            "may be sent as a bearer token",
            host,
        )
        return host

    logger.warning(
        "Non-loopback Ollama host %s requires AIGW_OLLAMA_ALLOW_REMOTE=1; falling back to %s",
        host,
        DEFAULT_OLLAMA_HOST,
    )
    return DEFAULT_OLLAMA_HOST


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _fetch_ollama_models(
    host: str,
    *,
    http_client_factory: Callable[[float], httpx.Client] | None,
    timeout_seconds: float,
) -> list[str]:
    factory = http_client_factory or (lambda timeout: httpx.Client(timeout=timeout))
    try:
        with factory(timeout_seconds) as client:
            response = client.get(f"{host}/api/tags")
    except (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.RequestError,
        httpx.InvalidURL,
    ) as exc:
        logger.warning(
            "Ollama not reachable at %s; provider loaded with no models: %s",
            host,
            exc,
        )
        return []

    if response.status_code < 200 or response.status_code >= 300:
        logger.warning(
            "Ollama not reachable at %s; provider loaded with no models: status %s",
            host,
            response.status_code,
        )
        return []

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning(
            "Ollama not reachable at %s; provider loaded with no models: malformed JSON: %s",
            host,
            exc,
        )
        return []

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []
    return _model_names_from_payload(models)


def _model_names_from_payload(models: list[Any]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for entry in models:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
