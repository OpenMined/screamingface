"""Cloudflare Access browser-transfer authentication and transport propagation."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from collections.abc import AsyncGenerator, Generator, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest
from nacl.public import Box, PrivateKey, PublicKey
from protocol_server import protocol_server
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

import screamingface as sf
from screamingface._engine.auth import (
    _access_audience,
    _access_authorization_url,
    _access_logout_url,
    _access_token,
    _CloudflareAccessAuth,
    _decrypt_transfer,
    _LoginAttempt,
    _present_access_authorization,
    _present_access_logout,
    _require_positive_timeout,
    _TransportAuth,
)
from screamingface._engine.transport import AsyncUrl4CloudTransport, Url4CloudTransport
from screamingface._evaluation.model import (
    Candidate,
    _compiled_candidate,
    _compiled_operation,
)

_ENGINE = "https://engine.example"
_AUDIENCE = "a" * 64
_TRANSFER_STORE = "https://login.cloudflareaccess.org"


def _b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _jwt(exp: float, *, marker: int = 1) -> str:
    header = _b64u(json.dumps({"alg": "RS256"}).encode())
    payload = _b64u(json.dumps({"exp": exp, "marker": marker}).encode())
    return f"{header}.{payload}.signature-{marker}"


@dataclass
class _Clock:
    monotonic: float = 100.0
    wall: float = 1_800_000_000.0

    def now(self) -> float:
        return self.monotonic

    def wall_now(self) -> float:
        return self.wall

    def sleep(self, seconds: float) -> None:
        self.monotonic += seconds
        self.wall += seconds


@dataclass
class _AccessFixture:
    clock: _Clock = field(default_factory=_Clock)
    server_key: PrivateKey = field(default_factory=PrivateKey.generate)
    browser_urls: list[str] = field(default_factory=list)
    application_tokens: list[str] = field(default_factory=list)
    pending_polls: int = 0
    head_status: int = 302
    transfer_status: int = 200
    polls: int = 0

    def __post_init__(self) -> None:
        if not self.application_tokens:
            self.application_tokens.append(_jwt(self.clock.wall + 900))

    def handler(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        url = str(request.url)
        if url.rstrip("/") == _ENGINE and request.method == "HEAD":
            if self.head_status == 405:
                return httpx.Response(405)
            return self.redirect()
        if url.rstrip("/") == _ENGINE and request.method == "GET":
            return self.redirect()
        if url.startswith(f"{_TRANSFER_STORE}/transfer/"):
            self.polls += 1
            if self.pending_polls > 0:
                self.pending_polls -= 1
                return httpx.Response(404)
            if self.transfer_status != 200:
                return httpx.Response(self.transfer_status)
            public_text = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            public_bytes = base64.urlsafe_b64decode(public_text)
            peer = PublicKey(public_bytes)
            index = min(self.polls - 1, len(self.application_tokens) - 1)
            body = json.dumps({"app_token": self.application_tokens[index]}).encode()
            encrypted = bytes(Box(self.server_key, peer).encrypt(body))
            service_key = base64.urlsafe_b64encode(bytes(self.server_key.public_key)).decode()
            return httpx.Response(
                200,
                headers={"service-public-key": service_key},
                content=base64.b64encode(encrypted),
            )
        raise AssertionError(f"unexpected Access request: {request.method} {request.url}")

    def redirect(self) -> httpx.Response:
        location = f"https://team.cloudflareaccess.com/cdn-cgi/access/login?kid={_AUDIENCE}"
        return httpx.Response(302, headers={"location": location})

    def auth(self) -> _CloudflareAccessAuth:
        return _CloudflareAccessAuth(
            _ENGINE,
            access_transport=httpx.MockTransport(self.handler),
            browser_presenter=self.browser_urls.append,
            clock=self.clock.now,
            wall_clock=self.clock.wall_now,
            sleep=self.clock.sleep,
        )


def _capture_login(auth: _CloudflareAccessAuth, errors: list[BaseException]) -> None:
    try:
        auth.login()
    except BaseException as exc:
        errors.append(exc)


def test_explicit_login_uses_encrypted_access_transfer_and_keeps_token_in_memory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _AccessFixture(pending_polls=1)
    token = fixture.application_tokens[0]
    auth = fixture.auth()

    auth.login(timeout=10)

    assert auth.authenticated is True
    assert auth.websocket_headers() == {"Cf-Access-Token": token}
    assert fixture.polls == 2
    assert len(fixture.browser_urls) == 1
    query = parse_qs(urlsplit(fixture.browser_urls[0]).query)
    assert urlsplit(fixture.browser_urls[0]).path == "/cdn-cgi/access/cli"
    assert query["aud"] == [_AUDIENCE]
    assert query["send_org_token"] == ["true"]
    assert query["edge_token_transfer"] == ["true"]
    assert query["token"]
    redirect = parse_qs(urlsplit(query["redirect_url"][0]).query)
    assert redirect["token"] == query["token"]
    assert token not in repr(auth)
    assert capsys.readouterr().out == (
        "Waiting for Cloudflare Access login to complete...\nCloudflare Access login complete.\n"
    )

    auth.login()
    assert len(fixture.browser_urls) == 1
    auth.close()
    auth.close()


def test_logout_clears_the_token_and_opens_the_access_logout_endpoint() -> None:
    fixture = _AccessFixture()
    auth = fixture.auth()
    auth.login()

    auth.logout()

    assert auth.authenticated is False
    assert auth.websocket_headers() == {}
    assert fixture.browser_urls[-1] == f"{_ENGINE}/cdn-cgi/access/logout"
    assert len(fixture.browser_urls) == 2
    auth.close()


def test_protected_request_starts_login_and_retries_with_access_header() -> None:
    fixture = _AccessFixture()
    headers: list[str | None] = []

    def application(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("Cf-Access-Token")
        headers.append(token)
        return httpx.Response(200, json={"ok": True}) if token else fixture.redirect()

    auth = fixture.auth()
    with httpx.Client(transport=httpx.MockTransport(application), auth=auth) as client:
        response = client.get(f"{_ENGINE}/v1/models")

    assert response.json() == {"ok": True}
    assert headers == [None, fixture.application_tokens[0]]
    auth.close()


@pytest.mark.asyncio
async def test_async_protected_request_uses_the_same_login_flow() -> None:
    fixture = _AccessFixture()
    headers: list[str | None] = []

    def application(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("Cf-Access-Token")
        headers.append(token)
        return httpx.Response(200) if token else fixture.redirect()

    auth = fixture.auth()
    async with httpx.AsyncClient(transport=httpx.MockTransport(application), auth=auth) as client:
        assert (await client.get(f"{_ENGINE}/v1/models")).status_code == 200

    assert headers == [None, fixture.application_tokens[0]]
    assert await auth.websocket_headers_async() == {
        "Cf-Access-Token": fixture.application_tokens[0]
    }
    await auth.logout_async()
    assert auth.authenticated is False
    auth.close()


def test_rejected_and_expired_tokens_are_replaced() -> None:
    fixture = _AccessFixture()
    first = fixture.application_tokens[0]
    second = _jwt(fixture.clock.wall + 1_800, marker=2)
    fixture.application_tokens.append(second)
    auth = fixture.auth()
    auth.login()
    assert auth.websocket_headers()["Cf-Access-Token"] == first

    fixture.clock.sleep(871)
    assert auth.authenticated is False
    auth.login()

    assert auth.websocket_headers()["Cf-Access-Token"] == second
    assert len(fixture.browser_urls) == 2
    auth.close()


@pytest.mark.asyncio
async def test_access_discovery_and_explicit_reauthentication_refresh_credentials() -> None:
    fixture = _AccessFixture()
    fixture.application_tokens.extend(
        [
            _jwt(fixture.clock.wall + 1_800, marker=2),
            _jwt(fixture.clock.wall + 2_700, marker=3),
        ]
    )
    auth = fixture.auth()

    assert auth.access_required() is True
    auth.login()
    first = auth.websocket_headers()["Cf-Access-Token"]
    auth.reauthenticate(timeout=10)
    second = auth.websocket_headers()["Cf-Access-Token"]
    await auth.reauthenticate_async(timeout=10)
    third = auth.websocket_headers()["Cf-Access-Token"]

    assert len({first, second, third}) == 3
    auth.close()


def test_waiting_login_reports_timeout_worker_failure_and_missing_credentials() -> None:
    auth = _AccessFixture().auth()
    await_login = getattr(auth, "_await_login")
    pending = _LoginAttempt(threading.Event(), threading.Event())
    with pytest.raises(sf.AuthenticationError) as timeout:
        await_login(pending, 0)
    assert timeout.value.code == "access_login_timeout"

    failed = _LoginAttempt(threading.Event(), threading.Event())
    failed.error = RuntimeError("worker failed")
    failed.done.set()
    with pytest.raises(RuntimeError, match="worker failed"):
        await_login(failed, 0)

    empty = _LoginAttempt(threading.Event(), threading.Event())
    empty.done.set()
    with pytest.raises(sf.AuthenticationError) as invalid:
        await_login(empty, 0)
    assert invalid.value.code == "access_invalid_token"
    auth.close()


def test_server_rejected_unexpired_token_starts_one_fresh_login() -> None:
    fixture = _AccessFixture()
    first = fixture.application_tokens[0]
    second = _jwt(fixture.clock.wall + 1_800, marker=2)
    fixture.application_tokens.append(second)
    auth = fixture.auth()
    auth.login()
    headers: list[str | None] = []

    def application(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("Cf-Access-Token")
        headers.append(token)
        return httpx.Response(200) if token == second else fixture.redirect()

    with httpx.Client(transport=httpx.MockTransport(application), auth=auth) as client:
        response = client.get(f"{_ENGINE}/v1/models")

    assert response.status_code == 200
    assert headers == [first, second]
    assert len(fixture.browser_urls) == 2
    auth.close()


def test_concurrent_login_callers_join_one_browser_attempt() -> None:
    fixture = _AccessFixture()
    transfer_started = threading.Event()
    release_transfer = threading.Event()

    def blocking_transfer(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(_TRANSFER_STORE):
            transfer_started.set()
            assert release_transfer.wait(1)
        return fixture.handler(request)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(blocking_transfer),
        browser_presenter=fixture.browser_urls.append,
        clock=fixture.clock.now,
        wall_clock=fixture.clock.wall_now,
        sleep=fixture.clock.sleep,
    )
    errors: list[BaseException] = []

    first = threading.Thread(target=_capture_login, args=(auth, errors))
    second = threading.Thread(target=_capture_login, args=(auth, errors))
    first.start()
    assert transfer_started.wait(1)
    second.start()
    release_transfer.set()
    first.join(1)
    second.join(1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert auth.authenticated is True
    assert len(fixture.browser_urls) == 1
    auth.close()


@pytest.mark.asyncio
async def test_cancelling_async_login_stops_its_transfer_worker() -> None:
    transfer_started = threading.Event()

    def pending_transfer(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                302,
                headers={"location": f"https://access.example/login?kid={_AUDIENCE}"},
            )
        transfer_started.set()
        return httpx.Response(404)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(pending_transfer),
        browser_presenter=lambda url: None,
    )
    task = asyncio.create_task(auth.login_async(timeout=30))
    assert await asyncio.to_thread(transfer_started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    for _ in range(50):
        if not auth.authenticating:
            break
        await asyncio.sleep(0.01)
    stopped = not auth.authenticating
    auth.cancel_login()
    await asyncio.sleep(0.01)
    auth.close()

    assert stopped is True


def test_head_discovery_falls_back_to_get() -> None:
    fixture = _AccessFixture(head_status=405)
    auth = fixture.auth()
    auth.login()
    assert auth.authenticated is True
    auth.close()


def test_audience_discovery_accepts_header_or_redirect_and_rejects_bad_values() -> None:
    assert _access_audience(httpx.Response(401, headers={"cf-access-aud": _AUDIENCE})) == _AUDIENCE
    assert (
        _access_audience(
            httpx.Response(
                302, headers={"location": f"https://access.example/login?kid={_AUDIENCE}"}
            )
        )
        == _AUDIENCE
    )
    assert _access_audience(httpx.Response(302, headers={"location": "/login?kid=short"})) is None
    assert (
        _access_audience(
            httpx.Response(302, headers={"location": f"/login?kid={_AUDIENCE}&kid={'b' * 64}"})
        )
        is None
    )
    assert _access_audience(httpx.Response(200)) is None


def test_login_requires_an_access_audience() -> None:
    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        browser_presenter=lambda url: None,
    )
    with pytest.raises(sf.AuthenticationError, match="does not advertise") as caught:
        auth.login()
    assert caught.value.code == "access_not_advertised"
    assert caught.value.status == 200
    auth.close()


def test_discovery_and_transfer_network_failures_are_typed() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret network detail", request=request)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(unreachable),
        browser_presenter=lambda url: None,
    )
    with pytest.raises(sf.EngineUnavailableError) as discovery:
        auth.login()
    assert discovery.value.code == "engine_unreachable"
    assert discovery.value.permanent is False
    assert discovery.value.engine_url == _ENGINE
    assert "secret" not in str(discovery.value)
    auth.close()

    fixture = _AccessFixture()

    def transfer_unreachable(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(_TRANSFER_STORE):
            raise httpx.ConnectError("secret transfer detail", request=request)
        return fixture.handler(request)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(transfer_unreachable),
        browser_presenter=lambda url: None,
    )
    with pytest.raises(sf.AuthenticationError) as transfer:
        auth.login()
    assert transfer.value.code == "access_transfer_unreachable"
    assert transfer.value.permanent is False
    assert "secret" not in str(transfer.value)
    auth.close()


def test_access_discovery_and_close_are_one_atomic_auth_operation() -> None:
    entered = threading.Event()
    release = threading.Event()
    completed: list[bool] = []

    def blocking_discovery(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        entered.set()
        assert release.wait(1)
        return httpx.Response(200)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(blocking_discovery),
        browser_presenter=lambda url: None,
    )
    discovery = threading.Thread(target=lambda: completed.append(auth.access_required()))
    closing = threading.Thread(target=auth.close)
    discovery.start()
    assert entered.wait(1)
    closing.start()
    time.sleep(0.01)
    assert closing.is_alive()
    release.set()
    discovery.join(1)
    closing.join(1)

    assert completed == [False]
    assert not discovery.is_alive()
    assert not closing.is_alive()


@pytest.mark.asyncio
async def test_cancelled_auth_worker_preserves_cleanup_failure_as_a_note() -> None:
    auth = _AccessFixture().auth()
    started = threading.Event()
    release = threading.Event()

    def fail_during_cleanup() -> None:
        started.set()
        assert release.wait(1)
        raise RuntimeError("private cleanup detail")

    task = asyncio.create_task(auth._cancellable_thread_call(fail_during_cleanup))
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task

    assert caught.value.__notes__ == ["Background authentication cleanup raised RuntimeError"]
    auth.close()


def test_transfer_read_timeout_is_retried_within_the_login_deadline() -> None:
    fixture = _AccessFixture()
    transfer_attempts = 0

    def slow_transfer(request: httpx.Request) -> httpx.Response:
        nonlocal transfer_attempts
        if str(request.url).startswith(_TRANSFER_STORE):
            transfer_attempts += 1
            if transfer_attempts == 1:
                fixture.clock.sleep(15)
                raise httpx.ReadTimeout("The read operation timed out", request=request)
        return fixture.handler(request)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(slow_transfer),
        browser_presenter=lambda url: None,
        clock=fixture.clock.now,
        wall_clock=fixture.clock.wall_now,
        sleep=fixture.clock.sleep,
    )

    auth.login(timeout=30)

    assert transfer_attempts == 2
    assert auth.authenticated is True
    auth.close()


def test_logout_cancels_a_waiting_login_without_blocking() -> None:
    poll_started = threading.Event()
    browser_urls: list[str] = []

    def pending_transfer(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                302,
                headers={"location": f"https://access.example/login?kid={_AUDIENCE}"},
            )
        poll_started.set()
        return httpx.Response(404)

    auth = _CloudflareAccessAuth(
        _ENGINE,
        access_transport=httpx.MockTransport(pending_transfer),
        browser_presenter=browser_urls.append,
    )
    errors: list[sf.AuthenticationError] = []

    def login() -> None:
        try:
            auth.login(timeout=0.2)
        except sf.AuthenticationError as exc:
            errors.append(exc)

    worker = threading.Thread(target=login)
    worker.start()
    assert poll_started.wait(1)

    started = time.monotonic()
    auth.logout()
    elapsed = time.monotonic() - started
    worker.join(timeout=1)

    assert elapsed < 0.1
    assert not worker.is_alive()
    assert errors[0].code == "access_login_cancelled"
    assert auth.authenticating is False
    assert browser_urls[-1] == f"{_ENGINE}/cdn-cgi/access/logout"
    auth.close()


def test_transfer_timeout_and_rejection_are_typed() -> None:
    fixture = _AccessFixture(pending_polls=99)
    auth = fixture.auth()
    with pytest.raises(sf.AuthenticationError) as timeout:
        auth.login(timeout=3)
    assert timeout.value.code == "access_login_timeout"
    assert fixture.clock.monotonic == 103
    auth.close()

    fixture = _AccessFixture(transfer_status=403)
    auth = fixture.auth()
    with pytest.raises(sf.AuthenticationError) as rejected:
        auth.login()
    assert rejected.value.code == "access_transfer_rejected"
    assert rejected.value.status == 403
    assert rejected.value.permanent is True
    auth.close()


@pytest.mark.parametrize(
    ("headers", "content"),
    [
        ({}, b"ciphertext"),
        ({"service-public-key": "invalid!"}, b"ciphertext"),
        ({"service-public-key": base64.urlsafe_b64encode(b"x" * 32).decode()}, b"not-base64"),
    ],
)
def test_malformed_encrypted_transfers_are_rejected(
    headers: dict[str, str], content: bytes
) -> None:
    response = httpx.Response(200, headers=headers, content=content)
    with pytest.raises(sf.AuthenticationError) as caught:
        _decrypt_transfer(response, PrivateKey.generate())
    assert caught.value.code == "access_invalid_transfer"


def test_transfer_rejects_oversized_decrypted_or_missing_token_payloads() -> None:
    private = PrivateKey.generate()
    peer = PrivateKey.generate()

    oversized = httpx.Response(
        200,
        headers={"service-public-key": base64.urlsafe_b64encode(bytes(peer.public_key)).decode()},
        content=b"x" * 1_000_001,
    )
    with pytest.raises(sf.AuthenticationError, match="invalid encrypted"):
        _decrypt_transfer(oversized, private)

    encrypted = bytes(
        Box(peer, private.public_key).encrypt(json.dumps({"wrong": "field"}).encode())
    )
    response = httpx.Response(
        200,
        headers={"service-public-key": base64.urlsafe_b64encode(bytes(peer.public_key)).decode()},
        content=base64.b64encode(encrypted),
    )
    with pytest.raises(sf.AuthenticationError, match="invalid encrypted"):
        _decrypt_transfer(response, private)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-jwt",
        "a.!.c",
        f"a.{_b64u(json.dumps({'sub': 'user'}).encode())}.c",
        f"a.{_b64u(json.dumps({'exp': True}).encode())}.c",
    ],
)
def test_invalid_access_tokens_are_rejected(value: str) -> None:
    with pytest.raises(sf.AuthenticationError) as caught:
        _access_token(value, 100, 1_800_000_000)
    assert caught.value.code == "access_invalid_token"


def test_expired_access_token_is_rejected() -> None:
    with pytest.raises(sf.AuthenticationError, match="expired"):
        _access_token(_jwt(1_800_000_030), 100, 1_800_000_000)


def test_browser_url_is_printed_and_notebook_does_not_open_browser(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class NotebookShell:
        __module__ = "ipykernel.zmqshell"

    monkeypatch.setattr("builtins.get_ipython", lambda: NotebookShell(), raising=False)
    monkeypatch.setattr(
        "screamingface._engine.access_contract.webbrowser.open",
        lambda *args, **kwargs: pytest.fail("notebooks should use the displayed URL"),
    )
    _present_access_authorization("https://access.example/login")
    assert "https://access.example/login" in capsys.readouterr().out


def test_desktop_browser_failure_keeps_the_printed_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delattr("builtins.get_ipython", raising=False)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("no browser")

    monkeypatch.setattr("screamingface._engine.access_contract.webbrowser.open", fail)
    _present_access_authorization("https://access.example/login")
    assert "https://access.example/login" in capsys.readouterr().out


def test_logout_opens_the_access_endpoint_even_from_a_notebook(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class NotebookShell:
        __module__ = "ipykernel.zmqshell"

    opened: list[str] = []
    monkeypatch.setattr("builtins.get_ipython", lambda: NotebookShell(), raising=False)
    monkeypatch.setattr(
        "screamingface._engine.access_contract.webbrowser.open",
        lambda url, *, new: opened.append(url),
    )

    _present_access_logout("https://engine.example/cdn-cgi/access/logout")

    assert opened == ["https://engine.example/cdn-cgi/access/logout"]
    assert "Completing Cloudflare Access logout" in capsys.readouterr().out


def test_logout_without_an_access_login_does_not_open_a_browser() -> None:
    fixture = _AccessFixture()
    auth = fixture.auth()

    auth.logout()

    assert fixture.browser_urls == []
    auth.close()


@pytest.mark.parametrize("timeout", [0, -1, True, "1", None])
def test_login_timeout_must_be_positive(timeout: object) -> None:
    with pytest.raises(ValueError, match="positive"):
        _require_positive_timeout(cast(Any, timeout))


def test_closed_authentication_rejects_login_and_requests() -> None:
    fixture = _AccessFixture()
    auth = fixture.auth()
    auth.close()
    with pytest.raises(RuntimeError, match="closed"):
        auth.login()
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    with httpx.Client(transport=transport, auth=auth) as client:
        with pytest.raises(RuntimeError, match="closed"):
            client.get(_ENGINE)


def test_authorization_url_preserves_engine_path_without_existing_query() -> None:
    url = _access_authorization_url(f"{_ENGINE}/tenant", _AUDIENCE, "public-key==")
    query = parse_qs(urlsplit(url).query)
    redirect = urlsplit(query["redirect_url"][0])
    assert urlsplit(url).path == "/cdn-cgi/access/cli"
    assert redirect.path == "/tenant"
    assert parse_qs(redirect.query)["aud"] == [_AUDIENCE]
    assert _access_logout_url(f"{_ENGINE}/tenant") == f"{_ENGINE}/cdn-cgi/access/logout"


class _StaticCallerAuth(_TransportAuth):
    def __init__(self) -> None:
        self.reauthentications = 0

    def reauthenticate(self, *, timeout: float = 300.0) -> None:
        del timeout
        self.reauthentications += 1

    async def reauthenticate_async(self, *, timeout: float = 300.0) -> None:
        self.reauthenticate(timeout=timeout)

    def websocket_headers(self) -> Mapping[str, str]:
        return {"Cf-Access-Token": "caller-token"}

    async def websocket_headers_async(self) -> Mapping[str, str]:
        return self.websocket_headers()

    def close(self) -> None:
        pass

    def sync_auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers.update(self.websocket_headers())
        yield request

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        request.headers.update(self.websocket_headers())
        yield request


def _candidate() -> Candidate:
    return _compiled_candidate(
        name="auth-test",
        kind="model",
        models=("provider/model",),
        url4="(@)!'hello'",
        operations=(
            _compiled_operation(
                id="op_auth_test",
                kind="model",
                label="auth test",
                depends_on=(),
            ),
        ),
    )


def test_access_token_reaches_http_and_websocket_without_replacing_capability() -> None:
    with protocol_server() as engine:
        with closing(Url4CloudTransport(engine.url, _StaticCallerAuth())) as transport:
            transport.run(_candidate(), None)

    assert engine.state.http_auth_schemes == ["Cf-Access-Token"]
    assert engine.state.websocket_auth_scheme == "Cf-Access-Token"


@pytest.mark.asyncio
async def test_async_transport_passes_access_token_to_the_websocket() -> None:
    with protocol_server() as engine:
        transport = AsyncUrl4CloudTransport(engine.url, _StaticCallerAuth())
        try:
            await transport.run(_candidate(), None)
        finally:
            await transport.close()

    assert engine.state.http_auth_schemes == ["Cf-Access-Token"]
    assert engine.state.websocket_auth_scheme == "Cf-Access-Token"


def test_websocket_access_rejection_reauthenticates_and_retries_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from screamingface._engine import transport as _transport

    real_connect = _transport.sync_ws.connect
    calls = 0

    def reject_once(uri: str, **kwargs: Any):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InvalidStatus(
                Response(
                    302,
                    "Found",
                    Headers({"Location": (f"https://access.example/login?kid={_AUDIENCE}")}),
                )
            )
        return real_connect(uri, **kwargs)

    monkeypatch.setattr(_transport.sync_ws, "connect", reject_once)
    auth = _StaticCallerAuth()
    with protocol_server() as engine:
        with closing(Url4CloudTransport(engine.url, auth)) as transport:
            transport.run(_candidate(), None)

    assert calls == 2
    assert auth.reauthentications == 1


@pytest.mark.asyncio
async def test_async_websocket_access_rejection_has_the_same_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from screamingface._engine import transport as _transport

    real_connect = _transport.async_ws.connect
    calls = 0

    def reject_once(uri: str, **kwargs: Any):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InvalidStatus(
                Response(
                    302,
                    "Found",
                    Headers({"cf-access-aud": _AUDIENCE}),
                )
            )
        return real_connect(uri, **kwargs)

    monkeypatch.setattr(_transport.async_ws, "connect", reject_once)
    auth = _StaticCallerAuth()
    with protocol_server() as engine:
        transport = AsyncUrl4CloudTransport(engine.url, auth)
        try:
            await transport.run(_candidate(), None)
        finally:
            await transport.close()

    assert calls == 2
    assert auth.reauthentications == 1
