"""Caller authentication for Cloudflare Access-protected hosted SF Engines."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncGenerator, Callable, Generator, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import quote

import httpx
from nacl.public import PrivateKey

from screamingface._engine.access_contract import (
    _REFRESH_SKEW_SECONDS,
    _access_audience,
    _access_authorization_url,
    _access_logout_url,
    _access_token,
    _AccessToken,
    _auth_error,
    _base64url_padded,
    _decrypt_transfer,
    _present_access_authorization,
    _present_access_logout,
    _raise_if_cancelled,
    _require_positive_timeout,
)
from screamingface._engine.auth_base import _TransportAuth
from screamingface.errors import EngineUnavailableError

_ACCESS_TRANSFER_STORE = "https://login.cloudflareaccess.org"
_ACCESS_USER_AGENT = "screamingface-python/0.2"
_DEFAULT_LOGIN_TIMEOUT = 300.0
_TRANSFER_POLL_SECONDS = 2.0


@dataclass(slots=True, repr=False)
class _LoginAttempt:
    cancel: threading.Event
    done: threading.Event
    error: BaseException | None = None


_BrowserPresenter = Callable[[str], None]


class _CloudflareAccessAuth(_TransportAuth):
    """Automatic encrypted browser login for a Cloudflare Access application."""

    def __init__(
        self,
        engine_url: str,
        *,
        access_transport: httpx.BaseTransport | None = None,
        browser_presenter: _BrowserPresenter | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._engine_url = engine_url
        self._access_http = httpx.Client(
            timeout=15.0,
            follow_redirects=False,
            headers={"User-Agent": _ACCESS_USER_AGENT},
            transport=access_transport,
        )
        self._present_browser = browser_presenter or _present_access_authorization
        self._present_logout = browser_presenter or _present_access_logout
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._lock = threading.RLock()
        self._token: _AccessToken | None = None
        self._generation = 0
        self._browser_session_started = False
        self._login_attempt: _LoginAttempt | None = None
        self._closed = False

    @property
    def authenticated(self) -> bool:
        with self._lock:
            return not self._closed and self._usable_token() is not None

    @property
    def authenticating(self) -> bool:
        with self._lock:
            return not self._closed and self._login_attempt is not None

    def login(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None:
        _require_positive_timeout(timeout)
        attempt, owner = self._begin_login()
        if attempt is None:
            return
        if not owner:
            self._await_login(attempt, timeout)
            return
        error: BaseException | None = None
        try:
            response = self._discovery_response()
            _raise_if_cancelled(attempt.cancel)
            audience = _access_audience(response)
            if audience is None:
                raise _auth_error(
                    "The SF Engine does not advertise Cloudflare Access browser authentication",
                    code="access_not_advertised",
                    status=response.status_code,
                )
            self._interactive_login(audience, timeout, attempt)
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._finish_login(attempt, error)

    async def login_async(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None:
        await self._cancellable_thread_call(self.login, timeout=timeout)

    def cancel_login(self) -> None:
        with self._lock:
            attempt = self._login_attempt
            if attempt is not None:
                attempt.cancel.set()
                self._login_attempt = None

    def access_required(self) -> bool:
        with self._lock:
            self._require_open()
        return _access_audience(self._discovery_response()) is not None

    def reauthenticate(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None:
        with self._lock:
            self._require_open()
            if self._token is not None:
                self._token = None
                self._generation += 1
        self.login(timeout=timeout)

    async def reauthenticate_async(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None:
        await self._cancellable_thread_call(self.reauthenticate, timeout=timeout)

    def logout(self) -> None:
        with self._lock:
            attempt = self._login_attempt
            if attempt is not None:
                attempt.cancel.set()
                self._login_attempt = None
            present_logout = self._browser_session_started or self._token is not None
            self._token = None
            self._generation += 1
            self._browser_session_started = False
        if present_logout:
            self._present_logout(_access_logout_url(self._engine_url))

    async def logout_async(self) -> None:
        await asyncio.to_thread(self.logout)

    def websocket_headers(self) -> Mapping[str, str]:
        with self._lock:
            token = self._usable_token()
            return {} if token is None else {"Cf-Access-Token": token}

    async def websocket_headers_async(self) -> Mapping[str, str]:
        return await asyncio.to_thread(self.websocket_headers)

    def close(self) -> None:
        attempt: _LoginAttempt | None
        with self._lock:
            if self._closed:
                return
            attempt = self._login_attempt
            if attempt is not None:
                attempt.cancel.set()
                self._login_attempt = None
            self._token = None
            self._generation += 1
            self._browser_session_started = False
            self._closed = True
        if attempt is not None:
            attempt.done.wait(_TRANSFER_POLL_SECONDS + 0.5)
        self._access_http.close()

    def sync_auth_flow(
        self,
        request: httpx.Request,
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.read()
        generation = self._authorize_request(request)
        response = yield request
        audience = _access_audience(response)
        if audience is None:
            return
        response.read()
        self._authenticate_after_redirect(audience, generation, _DEFAULT_LOGIN_TIMEOUT)
        self._set_access_token(request)
        yield request

    async def async_auth_flow(
        self,
        request: httpx.Request,
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        await request.aread()
        generation = await asyncio.to_thread(self._authorize_request, request)
        response = yield request
        audience = _access_audience(response)
        if audience is None:
            return
        await response.aread()
        await self._cancellable_thread_call(
            self._authenticate_after_redirect,
            audience,
            generation,
            _DEFAULT_LOGIN_TIMEOUT,
        )
        self._set_access_token(request)
        yield request

    def _authorize_request(self, request: httpx.Request) -> int:
        with self._lock:
            self._require_open()
            token = self._usable_token()
            if token is not None:
                request.headers["Cf-Access-Token"] = token
            return self._generation

    def _set_access_token(self, request: httpx.Request) -> None:
        with self._lock:
            token = self._usable_token()
            if token is None:
                raise _auth_error(
                    "Cloudflare Access login completed without a usable application token",
                    code="access_invalid_token",
                )
            request.headers["Cf-Access-Token"] = token

    def _usable_token(self) -> str | None:
        token = self._token
        if token is None or self._clock() + _REFRESH_SKEW_SECONDS >= token.expires_at:
            return None
        return token.value

    def _authenticate_after_redirect(
        self,
        audience: str,
        generation: int,
        timeout: float,
    ) -> None:
        with self._lock:
            self._require_open()
            if generation != self._generation and self._usable_token() is not None:
                return
            if generation == self._generation and self._token is not None:
                self._token = None
                self._generation += 1
        attempt, owner = self._begin_login()
        if attempt is None:
            return
        if not owner:
            self._await_login(attempt, timeout)
            return
        error: BaseException | None = None
        try:
            self._interactive_login(audience, timeout, attempt)
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._finish_login(attempt, error)

    def _begin_login(self) -> tuple[_LoginAttempt | None, bool]:
        with self._lock:
            self._require_open()
            if self._usable_token() is not None:
                return None, False
            if self._login_attempt is not None:
                return self._login_attempt, False
            attempt = _LoginAttempt(threading.Event(), threading.Event())
            self._login_attempt = attempt
            return attempt, True

    def _finish_login(
        self,
        attempt: _LoginAttempt,
        error: BaseException | None,
    ) -> None:
        with self._lock:
            attempt.error = error
            if self._login_attempt is attempt:
                self._login_attempt = None
            attempt.done.set()

    def _await_login(self, attempt: _LoginAttempt, timeout: float) -> None:
        if not attempt.done.wait(timeout):
            raise _auth_error(
                "Timed out waiting for the active Cloudflare Access login",
                code="access_login_timeout",
                permanent=False,
            )
        if attempt.error is not None:
            raise attempt.error
        with self._lock:
            self._require_open()
            if self._usable_token() is None:
                raise _auth_error(
                    "Cloudflare Access login completed without a usable application token",
                    code="access_invalid_token",
                )

    async def _cancellable_thread_call(
        self,
        operation: Callable[..., None],
        /,
        *args: object,
        **kwargs: object,
    ) -> None:
        worker = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            self.cancel_login()
            try:
                await asyncio.shield(worker)
            except BaseException:
                pass
            raise

    def _discovery_response(self) -> httpx.Response:
        try:
            response = self._access_http.head(self._engine_url)
            if response.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
                response = self._access_http.get(self._engine_url)
            return response
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(
                "Could not reach the SF Engine to discover Cloudflare Access authentication",
                engine_url=self._engine_url,
            ) from exc

    def _interactive_login(
        self,
        audience: str,
        timeout: float,
        attempt: _LoginAttempt,
    ) -> None:
        _raise_if_cancelled(attempt.cancel)
        private_key = PrivateKey.generate()
        public_key = _base64url_padded(bytes(private_key.public_key))
        authorization_url = _access_authorization_url(self._engine_url, audience, public_key)
        with self._lock:
            _raise_if_cancelled(attempt.cancel)
            self._require_open()
            self._browser_session_started = True
        self._present_browser(authorization_url)
        print("Waiting for Cloudflare Access login to complete...")
        token = self._poll_transfer(private_key, public_key, timeout, attempt.cancel)
        access_token = _access_token(token, self._clock(), self._wall_clock())
        with self._lock:
            _raise_if_cancelled(attempt.cancel)
            self._require_open()
            if self._login_attempt is not attempt:
                _raise_if_cancelled(attempt.cancel)
                raise _auth_error(
                    "Cloudflare Access login was superseded",
                    code="access_login_cancelled",
                    permanent=False,
                )
            self._token = access_token
            self._generation += 1
        print("Cloudflare Access login complete.")

    def _poll_transfer(
        self,
        private_key: PrivateKey,
        public_key: str,
        timeout: float,
        cancel: threading.Event,
    ) -> str:
        deadline = self._clock() + timeout
        transfer_url = f"{_ACCESS_TRANSFER_STORE}/transfer/{quote(public_key, safe='')}"
        while self._clock() < deadline:
            _raise_if_cancelled(cancel)
            try:
                remaining = max(0.0, deadline - self._clock())
                response = self._access_http.get(
                    transfer_url,
                    timeout=min(_TRANSFER_POLL_SECONDS, remaining),
                )
            except httpx.TimeoutException:
                # Cloudflare may hold a transfer poll open while the user completes OTP.
                # The caller's login deadline, rather than one socket read, owns the wait.
                _raise_if_cancelled(cancel)
                remaining = max(0.0, deadline - self._clock())
                self._wait_for_next_poll(cancel, min(_TRANSFER_POLL_SECONDS, remaining))
                continue
            except httpx.HTTPError as exc:
                _raise_if_cancelled(cancel)
                raise _auth_error(
                    "Could not reach the Cloudflare Access login transfer service",
                    code="access_transfer_unreachable",
                    permanent=False,
                ) from exc
            _raise_if_cancelled(cancel)
            if response.status_code == HTTPStatus.OK and response.content:
                return _decrypt_transfer(response, private_key)
            if response.status_code not in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_FOUND}:
                raise _auth_error(
                    "Cloudflare Access rejected the browser login transfer",
                    code="access_transfer_rejected",
                    status=response.status_code,
                    permanent=response.status_code < 500,
                )
            remaining = max(0.0, deadline - self._clock())
            self._wait_for_next_poll(cancel, min(_TRANSFER_POLL_SECONDS, remaining))
        _raise_if_cancelled(cancel)
        raise _auth_error(
            "Timed out waiting for Cloudflare Access login",
            code="access_login_timeout",
            permanent=False,
        )

    def _wait_for_next_poll(self, cancel: threading.Event, seconds: float) -> None:
        if self._sleep is time.sleep:
            if cancel.wait(seconds):
                _raise_if_cancelled(cancel)
            return
        self._sleep(seconds)
        _raise_if_cancelled(cancel)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("ScreamingFace caller authentication is closed")


def _default_caller_auth(engine_url: str) -> _CloudflareAccessAuth:
    return _CloudflareAccessAuth(engine_url)


__all__: list[str] = []
