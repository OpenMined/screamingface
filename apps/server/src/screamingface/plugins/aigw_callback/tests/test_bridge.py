from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from screamingface.plugins.aigw_callback.bridge import AigwCallbackBridge
from screamingface.plugins.aigw_callback.settings import AigwCallbackSettings


class _FakeServer:
    def __init__(self) -> None:
        self.closed = False
        self.waited = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


class _FakeReader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    async def readuntil(self, _separator: bytes) -> bytes:
        return self.data


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    @property
    def response(self) -> bytes:
        return b"".join(self.writes)

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _reader(data: bytes) -> asyncio.StreamReader:
    return cast(asyncio.StreamReader, _FakeReader(data))


def _writer(writer: _FakeWriter) -> asyncio.StreamWriter:
    return cast(asyncio.StreamWriter, writer)


def _request(target: str, *, method: str = "GET", host: str = "localhost") -> bytes:
    return f"{method} {target} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode("ascii")


@pytest.fixture
def bridge() -> AigwCallbackBridge:
    return AigwCallbackBridge(app=SimpleNamespace(), settings=AigwCallbackSettings())


@pytest.mark.asyncio
async def test_prepare_redirect_uri_starts_anthropic_listener(monkeypatch) -> None:
    server = _FakeServer()
    calls: list[tuple[str, int]] = []

    async def start_server(_handler, *, host: str, port: int):
        calls.append((host, port))
        return server

    monkeypatch.setattr(asyncio, "start_server", start_server)
    bridge = AigwCallbackBridge(app=SimpleNamespace(), settings=AigwCallbackSettings())

    redirect_uri = await bridge.prepare_redirect_uri(gateway_provider="anthropic")

    assert redirect_uri == "http://localhost:9105/callback"
    assert calls == [("localhost", 9105)]
    await bridge.shutdown()
    assert server.closed is True
    assert server.waited is True


@pytest.mark.asyncio
async def test_prepare_redirect_uri_brackets_ipv6_loopback_host(monkeypatch) -> None:
    server = _FakeServer()
    calls: list[tuple[str, int]] = []

    async def start_server(_handler, *, host: str, port: int):
        calls.append((host, port))
        return server

    monkeypatch.setattr(asyncio, "start_server", start_server)
    bridge = AigwCallbackBridge(
        app=SimpleNamespace(),
        settings=AigwCallbackSettings(host="::1"),
    )

    redirect_uri = await bridge.prepare_redirect_uri(gateway_provider="anthropic")

    assert redirect_uri == "http://[::1]:9105/callback"
    assert calls == [("::1", 9105)]
    await bridge.shutdown()


@pytest.mark.asyncio
async def test_prepare_redirect_uri_codex_tries_fallback_port(monkeypatch) -> None:
    server = _FakeServer()
    calls: list[int] = []

    async def start_server(_handler, *, host: str, port: int):  # noqa: ARG001
        calls.append(port)
        if port == 1455:
            raise OSError("busy")
        return server

    monkeypatch.setattr(asyncio, "start_server", start_server)
    bridge = AigwCallbackBridge(app=SimpleNamespace(), settings=AigwCallbackSettings())

    redirect_uri = await bridge.prepare_redirect_uri(gateway_provider="codex")

    assert redirect_uri == "http://localhost:1457/auth/callback"
    assert calls == [1455, 1457]
    await bridge.shutdown()


@pytest.mark.asyncio
async def test_prepare_redirect_uri_raises_when_port_busy(monkeypatch) -> None:
    async def start_server(_handler, *, host: str, port: int):  # noqa: ARG001
        raise OSError("busy")

    monkeypatch.setattr(asyncio, "start_server", start_server)
    bridge = AigwCallbackBridge(app=SimpleNamespace(), settings=AigwCallbackSettings())

    with pytest.raises(OSError):
        await bridge.prepare_redirect_uri(gateway_provider="anthropic")


@pytest.mark.asyncio
async def test_callback_forwards_code_to_gateway(monkeypatch, bridge: AigwCallbackBridge) -> None:
    captured: dict = {}

    async def request(self, method: str, path: str, *, json=None, **_kwargs):  # noqa: ANN001, ARG001
        captured["method"] = method
        captured["path"] = path
        captured["json"] = json
        return httpx.Response(200, json={"state": "authenticated"})

    monkeypatch.setattr(
        "screamingface.plugins.aigw_callback.bridge.AigwGatewayClient.request",
        request,
    )
    bridge.register_state(
        state="state-1",
        gateway_provider="anthropic",
        redirect_uri="http://localhost:9105/callback",
    )
    writer = _FakeWriter()

    await bridge._handle_connection(  # noqa: SLF001
        _reader(_request("/callback?code=provider-code&state=state-1")),
        _writer(writer),
    )

    assert writer.response.startswith(b"HTTP/1.1 200 OK\r\n")
    assert b"Authentication complete" in writer.response
    assert captured == {
        "method": "POST",
        "path": "/v1/auth/anthropic/exchange-code",
        "json": {"code": "provider-code", "state": "state-1"},
    }
    assert "state-1" not in bridge._pending  # noqa: SLF001
    await bridge.shutdown()


@pytest.mark.asyncio
async def test_callback_rejects_unknown_state(monkeypatch, bridge: AigwCallbackBridge) -> None:
    async def request(*_args, **_kwargs):
        raise AssertionError("gateway should not be called")

    monkeypatch.setattr(
        "screamingface.plugins.aigw_callback.bridge.AigwGatewayClient.request",
        request,
    )
    writer = _FakeWriter()

    await bridge._handle_connection(  # noqa: SLF001
        _reader(_request("/callback?code=provider-code&state=missing")),
        _writer(writer),
    )

    assert b"HTTP/1.1 400 Bad Request" in writer.response
    assert b"OAuth state not recognized or expired" in writer.response


@pytest.mark.asyncio
async def test_callback_rejects_path_mismatch(monkeypatch, bridge: AigwCallbackBridge) -> None:
    async def request(*_args, **_kwargs):
        raise AssertionError("gateway should not be called")

    monkeypatch.setattr(
        "screamingface.plugins.aigw_callback.bridge.AigwGatewayClient.request",
        request,
    )
    bridge.register_state(
        state="state-2",
        gateway_provider="anthropic",
        redirect_uri="http://localhost:9105/callback",
    )
    writer = _FakeWriter()

    await bridge._handle_connection(  # noqa: SLF001
        _reader(_request("/oauth2callback?code=provider-code&state=state-2")),
        _writer(writer),
    )

    assert b"HTTP/1.1 404 Not Found" in writer.response
    assert b"Unknown callback path" in writer.response
    assert "state-2" in bridge._pending  # noqa: SLF001
    await bridge.shutdown()


@pytest.mark.asyncio
async def test_callback_rejects_non_loopback_host(monkeypatch, bridge: AigwCallbackBridge) -> None:
    async def request(*_args, **_kwargs):
        raise AssertionError("gateway should not be called")

    monkeypatch.setattr(
        "screamingface.plugins.aigw_callback.bridge.AigwGatewayClient.request",
        request,
    )
    bridge.register_state(
        state="state-host",
        gateway_provider="anthropic",
        redirect_uri="http://localhost:9105/callback",
    )
    writer = _FakeWriter()

    await bridge._handle_connection(  # noqa: SLF001
        _reader(_request("/callback?code=provider-code&state=state-host", host="evil.test")),
        _writer(writer),
    )

    assert b"HTTP/1.1 403 Forbidden" in writer.response
    assert b"Forbidden callback host" in writer.response
    assert "state-host" in bridge._pending  # noqa: SLF001
    await bridge.shutdown()


@pytest.mark.asyncio
async def test_callback_gateway_failure_unregisters_state(
    monkeypatch,
    bridge: AigwCallbackBridge,
) -> None:
    async def request(self, method: str, path: str, *, json=None, **_kwargs):  # noqa: ANN001, ARG001
        return httpx.Response(400, json={"detail": {"code": "unknown_state"}})

    monkeypatch.setattr(
        "screamingface.plugins.aigw_callback.bridge.AigwGatewayClient.request",
        request,
    )
    bridge.register_state(
        state="state-3",
        gateway_provider="anthropic",
        redirect_uri="http://localhost:9105/callback",
    )
    writer = _FakeWriter()

    await bridge._handle_connection(  # noqa: SLF001
        _reader(_request("/callback?code=provider-code&state=state-3")),
        _writer(writer),
    )

    assert b"HTTP/1.1 400 Bad Request" in writer.response
    assert b"unknown_state" in writer.response
    assert "state-3" not in bridge._pending  # noqa: SLF001
    await bridge.shutdown()


@pytest.mark.asyncio
async def test_expired_state_closes_unused_listener(monkeypatch) -> None:
    real_sleep = asyncio.sleep

    async def immediate_sleep(_delay: float) -> None:
        return None

    now = 0.0

    monkeypatch.setattr("screamingface.plugins.aigw_callback.bridge.asyncio.sleep", immediate_sleep)
    monkeypatch.setattr("screamingface.plugins.aigw_callback.bridge.monotonic", lambda: now)

    bridge = AigwCallbackBridge(
        app=SimpleNamespace(),
        settings=AigwCallbackSettings(ttl_seconds=1),
    )
    server = _FakeServer()
    bridge._servers[9105] = cast(asyncio.AbstractServer, server)  # noqa: SLF001

    bridge.register_state(
        state="state-expired",
        gateway_provider="anthropic",
        redirect_uri="http://localhost:9105/callback",
    )
    now = 2.0

    await real_sleep(0)
    await real_sleep(0)

    assert "state-expired" not in bridge._pending  # noqa: SLF001
    assert 9105 not in bridge._servers  # noqa: SLF001
    assert server.closed is True
    assert server.waited is True
    await bridge.shutdown()
