"""Caller authentication for Cloudflare Access-protected hosted SF Engines."""

from __future__ import annotations

import asyncio
import base64
import builtins
import json
import re
import threading
import time
import webbrowser
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable, Generator, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

import httpx
from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey

from screamingface.errors import AuthenticationError

_ACCESS_TRANSFER_STORE = "https://login.cloudflareaccess.org"
_ACCESS_USER_AGENT = "screamingface-python/0.2"
_DEFAULT_LOGIN_TIMEOUT = 300.0
_MAX_TRANSFER_BYTES = 1_000_000
_REFRESH_SKEW_SECONDS = 30.0
_TRANSFER_POLL_SECONDS = 2.0
_VALID_AUDIENCE = re.compile(r"[A-Za-z0-9_-]{16,256}\Z")


class _CallerAuth(httpx.Auth, ABC):
    """Shared HTTPX/WebSocket authentication boundary."""

    requires_request_body = True

    @property
    @abstractmethod
    def authenticated(self) -> bool: ...

    @property
    @abstractmethod
    def authenticating(self) -> bool: ...

    @abstractmethod
    def login(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None: ...

    @abstractmethod
    async def login_async(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None: ...

    @abstractmethod
    def cancel_login(self) -> None: ...

    @abstractmethod
    def access_required(self) -> bool: ...

    @abstractmethod
    def reauthenticate(self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT) -> None: ...

    @abstractmethod
    async def reauthenticate_async(
        self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT
    ) -> None: ...

    @abstractmethod
    def logout(self) -> None: ...

    @abstractmethod
    async def logout_async(self) -> None: ...

    @abstractmethod
    def websocket_headers(self) -> Mapping[str, str]: ...

    @abstractmethod
    async def websocket_headers_async(self) -> Mapping[str, str]: ...

    @abstractmethod
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True, repr=False)
class _AccessToken:
    value: str
    expires_at: float


@dataclass(slots=True, repr=False)
class _LoginAttempt:
    cancel: threading.Event
    done: threading.Event
    error: BaseException | None = None


_BrowserPresenter = Callable[[str], None]


class _CloudflareAccessAuth(_CallerAuth):
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

    async def reauthenticate_async(
        self, *, timeout: float = _DEFAULT_LOGIN_TIMEOUT
    ) -> None:
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
            raise _auth_error(
                "Could not reach the SF Engine to discover Cloudflare Access authentication",
                code="access_discovery_unreachable",
                permanent=False,
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


def _access_audience(response: httpx.Response) -> str | None:
    audience = response.headers.get("cf-access-aud")
    if audience is None:
        location = response.headers.get("location")
        if location:
            values = parse_qs(urlsplit(location).query).get("kid", [])
            audience = values[0] if len(values) == 1 else None
    if audience is None:
        return None
    audience = audience.strip()
    return audience if _VALID_AUDIENCE.fullmatch(audience) else None


def _raise_if_cancelled(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise _auth_error(
            "Cloudflare Access login was cancelled",
            code="access_login_cancelled",
            permanent=False,
        )


def _access_authorization_url(engine_url: str, audience: str, public_key: str) -> str:
    parts = urlsplit(engine_url)
    transfer = {
        "token": public_key,
        "aud": audience,
        "send_org_token": "true",
        "edge_token_transfer": "true",
    }
    transfer["redirect_url"] = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(transfer), "")
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/cdn-cgi/access/cli",
            urlencode(transfer),
            "",
        )
    )


def _access_logout_url(engine_url: str) -> str:
    parts = urlsplit(engine_url)
    return urlunsplit((parts.scheme, parts.netloc, "/cdn-cgi/access/logout", "", ""))


def _present_access_authorization(authorization_url: str) -> None:
    print(f"Complete Cloudflare Access login in your browser:\n\n{authorization_url}\n")
    if _running_in_notebook():
        return
    try:
        webbrowser.open(authorization_url, new=2)
    except (OSError, webbrowser.Error):
        # The URL is already visible for terminals without a browser integration.
        return


def _present_access_logout(logout_url: str) -> None:
    print(f"Completing Cloudflare Access logout in your browser:\n\n{logout_url}\n")
    try:
        webbrowser.open(logout_url, new=2)
    except (OSError, webbrowser.Error):
        # The URL is already visible for environments without browser integration.
        return


def _decrypt_transfer(response: httpx.Response, private_key: PrivateKey) -> str:
    if len(response.content) > _MAX_TRANSFER_BYTES:
        raise _invalid_transfer()
    service_key = response.headers.get("service-public-key")
    if not service_key:
        raise _invalid_transfer()
    try:
        peer = PublicKey(_base64url_decode(service_key))
        encrypted = base64.b64decode(response.content, validate=True)
        decrypted = Box(private_key, peer).decrypt(encrypted)
        payload = json.loads(decrypted)
    except (ValueError, TypeError, json.JSONDecodeError, CryptoError) as exc:
        raise _invalid_transfer() from exc
    token = payload.get("app_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise _invalid_transfer()
    return token


def _access_token(value: str, monotonic_now: float, wall_now: float) -> _AccessToken:
    parts = value.split(".")
    if len(parts) != 3:
        raise _invalid_token()
    try:
        payload = json.loads(_base64url_decode(parts[1]))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _invalid_token() from exc
    expires = payload.get("exp") if isinstance(payload, dict) else None
    if not isinstance(expires, int | float) or isinstance(expires, bool):
        raise _invalid_token()
    lifetime = float(expires) - wall_now
    if lifetime <= _REFRESH_SKEW_SECONDS:
        raise _invalid_token()
    return _AccessToken(value, monotonic_now + lifetime)


def _base64url_padded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(f"{value}{padding}", altchars=b"-_", validate=True)


def _invalid_transfer() -> AuthenticationError:
    return _auth_error(
        "Cloudflare Access returned an invalid encrypted login transfer",
        code="access_invalid_transfer",
    )


def _invalid_token() -> AuthenticationError:
    return _auth_error(
        "Cloudflare Access returned an invalid or expired application token",
        code="access_invalid_token",
    )


def _running_in_notebook() -> bool:
    get_ipython = getattr(builtins, "get_ipython", None)
    if not callable(get_ipython):
        return False
    try:
        shell = get_ipython()
    except Exception:  # pragma: no cover - defensive around a host-provided hook
        return False
    return shell is not None and shell.__class__.__module__.startswith("ipykernel")


def _auth_error(
    message: str,
    *,
    code: str,
    status: int | None = None,
    permanent: bool = True,
) -> AuthenticationError:
    return AuthenticationError(message, code=code, status=status, permanent=permanent)


def _require_positive_timeout(timeout: float) -> None:
    if not isinstance(timeout, int | float) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout must be a positive number")


def _default_caller_auth(engine_url: str) -> _CallerAuth:
    return _CloudflareAccessAuth(engine_url)


__all__: list[str] = []
