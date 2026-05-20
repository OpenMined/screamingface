"""Shared SF-to-AIGateway HTTP client and external-session state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .config import is_runner_disabled, resolve_aigw_runtime_config

HttpClientFactory = Callable[[float], httpx.AsyncClient]
SyncHttpClientFactory = Callable[[float], httpx.Client]

_SESSION_TTL_CEILING = timedelta(hours=1)


class AigwGatewayClientError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class AigwGatewayAuthRequired(AigwGatewayClientError):
    def __init__(self) -> None:
        super().__init__(401, {"code": "login_gateway", "message": "AIGateway login required"})


class AigwGatewayUnavailable(AigwGatewayClientError):
    def __init__(self) -> None:
        super().__init__(503, {"code": "aigateway_disabled", "message": "AIGateway is disabled"})


class AigwGatewaySessionState:
    def __init__(self) -> None:
        self.token: str | None = None
        self.expires_at: datetime | None = None
        self._cancel_event: asyncio.Event = asyncio.Event()

    @property
    def authenticated(self) -> bool:
        return self.valid_token() is not None

    def valid_token(self) -> str | None:
        if self.token is None:
            return None
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            self.clear()
            return None
        return self.token

    def set_token(self, token: str, expires_at: datetime | None) -> None:
        ceiling = datetime.now(UTC) + _SESSION_TTL_CEILING
        if expires_at is None or expires_at > ceiling:
            expires_at = ceiling
        self.token = token
        self.expires_at = expires_at
        self._cancel_event = asyncio.Event()

    def clear(self) -> None:
        self.token = None
        self.expires_at = None
        self.cancel_active()

    def cancel_active(self) -> None:
        self._cancel_event.set()
        self._cancel_event = asyncio.Event()

    def cancellation_event(self) -> asyncio.Event:
        return self._cancel_event


def gateway_session_state(app: Any) -> AigwGatewaySessionState:
    app_state = getattr(app, "state", None)
    if app_state is None:
        return AigwGatewaySessionState()
    state = getattr(app_state, "_aigw_gateway_session", None)
    if not isinstance(state, AigwGatewaySessionState):
        state = AigwGatewaySessionState()
        app_state._aigw_gateway_session = state
    return state


def clear_gateway_session(app: Any) -> None:
    gateway_session_state(app).clear()


def cancel_gateway_requests(app: Any) -> None:
    gateway_session_state(app).cancel_active()


class AigwGatewayClient:
    def __init__(
        self,
        app: Any,
        *,
        http_client_factory: HttpClientFactory | None = None,
        sync_http_client_factory: SyncHttpClientFactory | None = None,
    ) -> None:
        self._app = app
        self._http_factory = http_client_factory or (
            lambda timeout: httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        )
        self._sync_http_factory = sync_http_client_factory or (
            lambda timeout: httpx.Client(timeout=httpx.Timeout(timeout))
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
        allow_unauthenticated: bool = False,
    ) -> httpx.Response:
        if is_runner_disabled():
            cancel_gateway_requests(self._app)
            raise AigwGatewayUnavailable()

        config = resolve_aigw_runtime_config(self._app)
        url = f"{config.gateway_url}{path}"
        request_headers = dict(headers or {})
        session = gateway_session_state(self._app)
        cancel_event = session.cancellation_event()

        if config.mode == "external" and not allow_unauthenticated:
            token = session.valid_token()
            if token is None:
                raise AigwGatewayAuthRequired()
            request_headers["Authorization"] = f"Bearer {token}"

        async with self._http_factory(timeout_seconds) as client:
            response = await _with_cancellation(
                client.request(method, url, json=json, headers=request_headers),
                cancel_event,
            )

        if config.mode == "external" and not allow_unauthenticated and response.status_code == 401:
            clear_gateway_session(self._app)
        return response

    def request_sync(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
        allow_unauthenticated: bool = False,
    ) -> httpx.Response:
        if is_runner_disabled():
            cancel_gateway_requests(self._app)
            raise AigwGatewayUnavailable()

        config = resolve_aigw_runtime_config(self._app)
        url = f"{config.gateway_url}{path}"
        request_headers = dict(headers or {})
        session = gateway_session_state(self._app)

        if config.mode == "external" and not allow_unauthenticated:
            token = session.valid_token()
            if token is None:
                raise AigwGatewayAuthRequired()
            request_headers["Authorization"] = f"Bearer {token}"

        with self._sync_http_factory(timeout_seconds) as client:
            response = client.request(method, url, json=json, headers=request_headers)

        if config.mode == "external" and not allow_unauthenticated and response.status_code == 401:
            clear_gateway_session(self._app)
        return response


async def _with_cancellation(
    request_coro: Any,
    cancel_event: asyncio.Event,
) -> httpx.Response:
    request_task = asyncio.create_task(request_coro)
    cancel_task = asyncio.create_task(_wait_for_abort(cancel_event))
    done, pending = await asyncio.wait(
        {request_task, cancel_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    if cancel_task in done:
        request_task.cancel()
        raise AigwGatewayUnavailable()
    return await request_task


async def _wait_for_abort(cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        if is_runner_disabled():
            return
        await asyncio.sleep(0.25)


def parse_gateway_expires_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
