from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest

from aigateway.plugins.ollama_provider import discovery
from aigateway.plugins.ollama_provider.discovery import (
    DEFAULT_OLLAMA_HOST,
    clear_ollama_discovery_cache,
    discover_ollama_models,
    resolve_ollama_host,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_ollama_discovery_cache()
    yield
    clear_ollama_discovery_cache()


def _factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(timeout: float) -> httpx.Client:
        return httpx.Client(transport=transport, timeout=timeout)

    return factory


def _response(models: list[Any]) -> httpx.Response:
    return httpx.Response(200, json={"models": models})


def test_discover_ollama_models_reads_api_tags_in_order() -> None:
    factory = _factory(
        lambda _request: _response([{"name": "llama3:8b"}, {"name": "qwen2.5-coder:7b"}])
    )

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == [
        "llama3:8b",
        "qwen2.5-coder:7b",
    ]


def test_discover_ollama_models_deduplicates_and_ignores_malformed_entries() -> None:
    factory = _factory(
        lambda _request: _response(
            [
                {"name": "llama3:8b"},
                {"name": "llama3:8b"},
                {"model": "missing-name"},
                {"name": 123},
                "bad-entry",
                {"name": "qwen2.5-coder:7b"},
            ]
        )
    )

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == [
        "llama3:8b",
        "qwen2.5-coder:7b",
    ]


def test_discover_ollama_models_connection_error_returns_empty_and_logs(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=_factory(handler)) == []
    assert "Ollama not reachable at http://localhost:11434" in caplog.text


def test_discover_ollama_models_timeout_returns_empty_and_logs(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=_factory(handler)) == []
    assert "Ollama not reachable at http://localhost:11434" in caplog.text


def test_discover_ollama_models_non_success_returns_empty_and_logs_status(caplog) -> None:
    factory = _factory(lambda _request: httpx.Response(503, json={"error": "busy"}))

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == []
    assert "status 503" in caplog.text


def test_discover_ollama_models_malformed_json_returns_empty_and_logs(caplog) -> None:
    factory = _factory(lambda _request: httpx.Response(200, content=b"{"))

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == []
    assert "malformed JSON" in caplog.text


def test_discover_ollama_models_invalid_url_returns_empty_and_logs(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.InvalidURL("bad url")

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=_factory(handler)) == []
    assert "Ollama not reachable at http://localhost:11434" in caplog.text


def test_resolve_ollama_host_env_priority_and_ignores_sf_env() -> None:
    assert (
        resolve_ollama_host(
            {
                "AIGW_OLLAMA_HOST": "http://127.0.0.1:11435/",
                "OLLAMA_API_BASE": "http://localhost:11436",
                "SF_OLLAMA__HOST": "http://ignored.example.test",
            }
        )
        == "http://127.0.0.1:11435"
    )
    assert (
        resolve_ollama_host(
            {
                "OLLAMA_API_BASE": "http://localhost:11436/",
                "SF_OLLAMA__HOST": "http://ignored.example.test",
            }
        )
        == "http://localhost:11436"
    )
    assert resolve_ollama_host({"SF_OLLAMA__HOST": "http://ignored.example.test"}) == (
        DEFAULT_OLLAMA_HOST
    )


def test_resolve_ollama_host_invalid_scheme_falls_back_to_default(caplog) -> None:
    assert resolve_ollama_host({"AIGW_OLLAMA_HOST": "ftp://example.test"}) == DEFAULT_OLLAMA_HOST
    assert "Invalid Ollama host" in caplog.text


@pytest.mark.parametrize(
    "host",
    ["http://localhost:bad", "http://localhost:99999", "http://[::1"],
)
def test_resolve_ollama_host_invalid_port_falls_back_to_default(host: str, caplog) -> None:
    assert resolve_ollama_host({"AIGW_OLLAMA_HOST": host}) == DEFAULT_OLLAMA_HOST
    assert "Invalid Ollama host" in caplog.text


def test_resolve_ollama_host_non_loopback_requires_explicit_opt_in(caplog) -> None:
    assert (
        resolve_ollama_host({"AIGW_OLLAMA_HOST": "http://192.168.1.10:11434"})
        == DEFAULT_OLLAMA_HOST
    )
    assert "AIGW_OLLAMA_ALLOW_REMOTE=1" in caplog.text


def test_resolve_ollama_host_remote_allowed_warns_about_ollama_api_key(caplog) -> None:
    host = resolve_ollama_host(
        {
            "AIGW_OLLAMA_HOST": "http://192.168.1.10:11434/",
            "AIGW_OLLAMA_ALLOW_REMOTE": "1",
            "OLLAMA_API_KEY": "secret",
        }
    )

    assert host == "http://192.168.1.10:11434"
    assert "192.168.1.10" in caplog.text
    assert "OLLAMA_API_KEY" in caplog.text


def test_concurrent_discovery_uses_single_upstream_probe() -> None:
    calls = 0
    lock = threading.Lock()

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return _response([{"name": "llama3:8b"}])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _index: discover_ollama_models(
                    DEFAULT_OLLAMA_HOST,
                    http_client_factory=_factory(handler),
                ),
                range(4),
            )
        )

    assert results == [["llama3:8b"]] * 4
    assert calls == 1


def test_positive_cache_expiry_triggers_one_reprobe(monkeypatch) -> None:
    now = 100.0
    calls = 0
    monkeypatch.setattr(discovery.time, "monotonic", lambda: now)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response([{"name": f"model-{calls}"}])

    factory = _factory(handler)

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == ["model-1"]
    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == ["model-1"]
    assert calls == 1

    now = 111.0
    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == ["model-2"]
    assert calls == 2


def test_negative_cache_expiry_uses_short_ttl(monkeypatch) -> None:
    now = 100.0
    calls = 0
    monkeypatch.setattr(discovery.time, "monotonic", lambda: now)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused", request=request)

    factory = _factory(handler)

    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == []
    now = 101.0
    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == []
    assert calls == 1

    now = 102.1
    assert discover_ollama_models(DEFAULT_OLLAMA_HOST, http_client_factory=factory) == []
    assert calls == 2
