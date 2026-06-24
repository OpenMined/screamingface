"""Loopback OAuth callback bridge for hosted AIGateway auth flows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html import escape
from ipaddress import ip_address
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from screamingface.plugins.aigw_base.client import AigwGatewayClient, AigwGatewayClientError

from .settings import AigwCallbackSettings

_SUCCESS_HTML = """<!doctype html>
<html><body><p>Authentication complete. You may close this window.</p></body></html>
"""


@dataclass(frozen=True)
class _CallbackRoute:
    path: str
    ports: tuple[int, ...]


@dataclass(frozen=True)
class _PendingCallback:
    gateway_provider: str
    expected_path: str
    redirect_uri: str
    expires_at: float


class DisabledAigwCallbackBridge:
    async def prepare_redirect_uri(self, *, gateway_provider: str) -> str | None:  # noqa: ARG002
        return None

    def register_state(self, *, state: str, gateway_provider: str, redirect_uri: str) -> None:  # noqa: ARG002
        return None

    def release_redirect_uri(self, redirect_uri: str) -> None:  # noqa: ARG002
        return None

    def unregister_state(self, state: str) -> None:  # noqa: ARG002
        return None

    async def shutdown(self) -> None:
        return None


class AigwCallbackBridge:
    def __init__(self, *, app: Any, settings: AigwCallbackSettings) -> None:
        self._app = app
        self._settings = settings
        self._servers: dict[int, asyncio.AbstractServer] = {}
        self._pending: dict[str, _PendingCallback] = {}
        self._reservations: dict[str, int] = {}
        self._expiry_tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def prepare_redirect_uri(self, *, gateway_provider: str) -> str | None:
        if not self._settings.enabled:
            return None
        route = self._route_for(gateway_provider)
        if route is None:
            return None

        last_error: OSError | None = None
        async with self._lock:
            self._prune_expired()
            for port in route.ports:
                redirect_uri = (
                    f"http://{_redirect_uri_host(self._settings.host)}:{port}{route.path}"
                )
                try:
                    await self._ensure_server(port)
                except OSError as exc:
                    last_error = exc
                    continue
                self._reservations[redirect_uri] = self._reservations.get(redirect_uri, 0) + 1
                return redirect_uri

        if last_error is not None:
            raise OSError("Local OAuth callback port is unavailable") from last_error
        return None

    def register_state(self, *, state: str, gateway_provider: str, redirect_uri: str) -> None:
        route = self._route_for(gateway_provider)
        if route is None:
            self.release_redirect_uri(redirect_uri)
            return
        parsed = urlsplit(redirect_uri)
        expected_path = parsed.path or route.path
        self._pending[state] = _PendingCallback(
            gateway_provider=gateway_provider,
            expected_path=expected_path,
            redirect_uri=redirect_uri,
            expires_at=monotonic() + self._settings.ttl_seconds,
        )
        self._schedule_state_expiry(state)
        self._decrement_reservation(redirect_uri)
        self._schedule_close_unused_servers()

    def release_redirect_uri(self, redirect_uri: str) -> None:
        self._decrement_reservation(redirect_uri)
        self._schedule_close_unused_servers()

    def unregister_state(self, state: str) -> None:
        self._drop_state(state)
        self._schedule_close_unused_servers()

    async def shutdown(self) -> None:
        async with self._lock:
            servers = list(self._servers.values())
            expiry_tasks = list(self._expiry_tasks.values())
            self._servers.clear()
            self._pending.clear()
            self._reservations.clear()
            self._expiry_tasks.clear()
        for task in expiry_tasks:
            task.cancel()
        if expiry_tasks:
            await asyncio.gather(*expiry_tasks, return_exceptions=True)
        for server in servers:
            server.close()
        for server in servers:
            await server.wait_closed()

    async def _ensure_server(self, port: int) -> None:
        if port in self._servers:
            return
        server = await asyncio.start_server(
            self._handle_connection,
            host=self._settings.host,
            port=port,
        )
        self._servers[port] = server

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            status, body = await self._handle_request(reader)
        except Exception as exc:
            status = 500
            body = _failure_html("Authentication failed", _safe_message(exc))
        finally:
            writer.write(_http_response(status, body))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

    async def _handle_request(self, reader: asyncio.StreamReader) -> tuple[int, str]:
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            return 400, _failure_html("Authentication failed", "Malformed callback request")

        lines = raw.decode("iso-8859-1", errors="replace").split("\r\n")
        request_line = lines[0].split()
        if len(request_line) < 2:
            return 400, _failure_html("Authentication failed", "Malformed callback request")

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        if not _loopback_host_allowed(headers.get("host")):
            return 403, _failure_html("Authentication failed", "Forbidden callback host")

        method, target = request_line[0], request_line[1]
        if method != "GET":
            return 405, _failure_html("Authentication failed", "Unsupported callback method")

        parsed = urlsplit(target)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        if not code or not state:
            return 400, _failure_html("Authentication failed", "Missing callback code or state")

        pending = self._pending_for_state(state)
        if pending is None:
            return 400, _failure_html(
                "Authentication failed",
                "OAuth state not recognized or expired",
            )
        if parsed.path != pending.expected_path:
            return 404, _failure_html("Authentication failed", "Unknown callback path")

        status, body = await self._forward_callback(pending, code, state)
        self.unregister_state(state)
        return status, body

    async def _forward_callback(
        self,
        pending: _PendingCallback,
        code: str,
        state: str,
    ) -> tuple[int, str]:
        try:
            resp = await AigwGatewayClient(self._app).request(
                "POST",
                f"/v1/auth/{pending.gateway_provider}/exchange-code",
                json={"code": code, "state": state},
            )
        except AigwGatewayClientError as exc:
            return exc.status_code, _failure_html("Authentication failed", _safe_detail(exc.detail))
        except httpx.RequestError as exc:
            return 502, _failure_html("Authentication failed", _safe_message(exc))

        if resp.status_code >= 400:
            status = 502 if resp.status_code >= 500 else resp.status_code
            return status, _failure_html("Authentication failed", _safe_response_detail(resp))
        return 200, _SUCCESS_HTML

    def _pending_for_state(self, state: str) -> _PendingCallback | None:
        pending = self._pending.get(state)
        if pending is None:
            return None
        if pending.expires_at <= monotonic():
            self._drop_state(state)
            self._schedule_close_unused_servers()
            return None
        return pending

    def _prune_expired(self) -> None:
        now = monotonic()
        for state, pending in list(self._pending.items()):
            if pending.expires_at <= now:
                self._drop_state(state)

    def _drop_state(self, state: str) -> None:
        self._pending.pop(state, None)
        task = self._expiry_tasks.pop(state, None)
        if task is not None:
            task.cancel()

    def _schedule_state_expiry(self, state: str) -> None:
        old_task = self._expiry_tasks.pop(state, None)
        if old_task is not None:
            old_task.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._expiry_tasks[state] = loop.create_task(
            self._expire_state_after(state, self._settings.ttl_seconds)
        )

    async def _expire_state_after(self, state: str, ttl_seconds: int) -> None:
        try:
            await asyncio.sleep(ttl_seconds)
        except asyncio.CancelledError:
            return
        pending = self._pending.get(state)
        if pending is None or pending.expires_at > monotonic():
            return
        self._pending.pop(state, None)
        self._expiry_tasks.pop(state, None)
        await self._close_unused_servers()

    def _decrement_reservation(self, redirect_uri: str) -> None:
        count = self._reservations.get(redirect_uri, 0)
        if count <= 1:
            self._reservations.pop(redirect_uri, None)
            return
        self._reservations[redirect_uri] = count - 1

    def _schedule_close_unused_servers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._close_unused_servers())

    async def _close_unused_servers(self) -> None:
        async with self._lock:
            self._prune_expired()
            to_close: list[asyncio.AbstractServer] = []
            for port, server in list(self._servers.items()):
                if self._port_has_work(port):
                    continue
                self._servers.pop(port, None)
                to_close.append(server)
        for server in to_close:
            server.close()
        for server in to_close:
            await server.wait_closed()

    def _port_has_work(self, port: int) -> bool:
        for pending in self._pending.values():
            if _redirect_uri_port(pending.redirect_uri) == port:
                return True
        for redirect_uri, count in self._reservations.items():
            if count > 0 and _redirect_uri_port(redirect_uri) == port:
                return True
        return False

    def _route_for(self, gateway_provider: str) -> _CallbackRoute | None:
        if gateway_provider == "anthropic":
            return _CallbackRoute("/callback", (self._settings.anthropic_port,))
        if gateway_provider == "gemini-cli":
            return _CallbackRoute("/oauth2callback", (self._settings.gemini_port,))
        if gateway_provider == "antigravity":
            # Antigravity reuses Gemini's loopback callback path AND port. A
            # 2026-06-19 probe confirmed Google validates only the loopback host
            # (not the path) for the antigravity installed-app client, so no new
            # path/port/setting is needed (zero redirect delta).
            return _CallbackRoute("/oauth2callback", (self._settings.gemini_port,))
        if gateway_provider == "codex":
            return _CallbackRoute("/auth/callback", tuple(self._settings.codex_ports))
        return None


def _redirect_uri_port(redirect_uri: str) -> int | None:
    try:
        return urlsplit(redirect_uri).port
    except ValueError:
        return None


def _redirect_uri_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _loopback_host_allowed(host_header: str | None) -> bool:
    if host_header is None:
        return False
    try:
        hostname = urlsplit(f"//{host_header.strip()}").hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _http_response(status: int, body: str) -> bytes:
    reason = {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        502: "Bad Gateway",
    }.get(status, "Internal Server Error")
    data = body.encode("utf-8")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        "content-type: text/html; charset=utf-8\r\n"
        f"content-length: {len(data)}\r\n"
        "connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return headers + data


def _failure_html(title: str, message: str) -> str:
    return (
        f"<!doctype html><html><body><h2>{escape(title)}</h2><p>{escape(message)}</p></body></html>"
    )


def _safe_detail(detail: Any) -> str:
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        parts = [str(part) for part in (code, message) if isinstance(part, str) and part]
        if parts:
            return ": ".join(parts)[:500]
    return str(detail)[:500]


def _safe_response_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return f"Gateway returned HTTP {resp.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return _safe_detail(detail if detail is not None else payload)


def _safe_message(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]
