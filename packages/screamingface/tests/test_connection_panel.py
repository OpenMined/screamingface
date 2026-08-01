from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable

import httpx
import ipywidgets as widgets
import pytest

import screamingface as sf

SECRET = "sk-or-v1-widget-secret"


class Engine:
    def __init__(self) -> None:
        self.connected = False
        self.reject = False
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        self.calls.append(request)
        row = {
            "object": "connection",
            "provider": "openrouter",
            "display_name": "OpenRouter",
            "auth_methods": ["api_key"],
            "status": "connected" if self.connected else "not_connected",
            "auth_method": "api_key" if self.connected else None,
            "account_label": None,
        }
        if request.method == "GET":
            return httpx.Response(200, json={"object": "list", "data": [row]})
        if request.method == "PUT":
            if self.reject:
                return httpx.Response(
                    401,
                    json={
                        "type": "about:blank",
                        "title": "Unauthorized",
                        "status": 401,
                        "detail": "private " + SECRET,
                    },
                )
            assert json.loads(request.content) == {"api_key": SECRET}
            self.connected = True
            return httpx.Response(
                200,
                json={**row, "status": "connected", "auth_method": "api_key"},
            )
        self.connected = False
        return httpx.Response(200, json={**row, "status": "not_connected", "auth_method": None})


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    return sf.Client(
        engine_url="http://127.0.0.1:9108",
        http_transport=httpx.MockTransport(handler),
    )


def _walk(widget: widgets.Widget) -> tuple[widgets.Widget, ...]:
    children = getattr(widget, "children", ())
    return (widget, *(item for child in children for item in _walk(child)))


def _buttons(widget: widgets.Widget) -> list[widgets.Button]:
    return [item for item in _walk(widget) if isinstance(item, widgets.Button)]


def _button(widget: widgets.Widget, description: str) -> widgets.Button:
    return next(item for item in _buttons(widget) if item.description == description)


def _password(widget: widgets.Widget) -> widgets.Password:
    return next(item for item in _walk(widget) if isinstance(item, widgets.Password))


def _text(widget: widgets.Widget) -> str:
    return "\n".join(
        value
        for item in _walk(widget)
        for attribute in ("value", "description", "tooltip")
        if isinstance((value := getattr(item, attribute, None)), str)
    )


async def _wait_for_button(widget: widgets.Widget, description: str) -> None:
    for _ in range(100):
        if [button.description for button in _buttons(widget)] == [description]:
            return
        await asyncio.sleep(0.01)


class _EmptyConnections:
    def list(self) -> tuple[sf.Connection, ...]:
        return ()


class _SharedAuthClient:
    engine_url = "https://fusion.dev.screamingface.ai"
    authenticated = False
    authenticating = False
    connections = _EmptyConnections()

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.listeners: list[Callable[[], None]] = []

    def _subscribe_auth(self, listener: Callable[[], None]) -> Callable[[], None]:
        self.listeners.append(listener)

        def unsubscribe() -> None:
            self.listeners.remove(listener)

        return unsubscribe

    def _notify(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    def login(self, *, timeout: float = 300.0) -> None:
        del timeout
        self.authenticating = True
        self._notify()
        self.started.set()
        assert self.release.wait(1)
        self.authenticating = False
        self.authenticated = True
        self._notify()

    def _cancel_login(self) -> None:
        self.authenticating = False
        self.release.set()
        self._notify()

    def logout(self) -> None:
        self.authenticated = False
        self._notify()


def test_panel_keeps_the_full_collapsed_api_key_ui_and_only_one_openrouter_row() -> None:
    engine = Engine()
    client = _client(engine)
    panel = client.connect()
    root = panel.widget()

    assert [item.provider for item in panel.connections] == ["openrouter"]
    assert "Connections" in _text(root)
    assert "OpenRouter" in _text(root)
    assert "Engine access" not in _text(root)
    assert "http://127.0.0.1:9108" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Connect"]

    _button(root, "Connect").click()
    assert [button.description for button in _buttons(root)] == ["API key", "Cancel"]
    _button(root, "API key").click()
    password = _password(root)
    password.value = SECRET
    _button(root, "Save").click()

    assert password.value == ""
    assert [button.description for button in _buttons(root)] == ["Disconnect"]
    assert panel.connections[0].status == "connected"
    assert SECRET not in _text(root)
    assert SECRET not in panel._repr_html_()

    _button(root, "Disconnect").click()
    assert panel.connections[0].status == "not_connected"
    assert [button.description for button in _buttons(root)] == ["Connect"]
    root.close()
    client.close()


def test_panel_displays_safe_inline_errors_and_always_clears_the_password() -> None:
    engine = Engine()
    engine.reject = True
    client = _client(engine)
    root = client.connect().widget()

    _button(root, "Connect").click()
    _button(root, "API key").click()
    password = _password(root)
    password.value = SECRET
    _button(root, "Save").click()

    assert password.value == ""
    assert "Provider connection was rejected" in _text(root)
    assert SECRET not in _text(root)
    root.close()
    client.close()


def test_local_panel_renders_engine_unavailability_inline() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private socket detail", request=request)

    client = _client(unreachable)
    panel = client.connect()
    root = panel.widget()

    assert panel.connections == ()
    assert "Could not reach the SF Engine provider connections" in _text(root)
    assert "Start the local Engine" in _text(root)
    assert "private socket detail" not in _text(root)
    root.close()
    client.close()


def test_panel_retains_dormant_oauth_pending_and_cancel_controls() -> None:
    connection = sf.Connection(
        provider="future",
        display_name="Future Provider",
        auth_methods=("oauth", "api_key"),
        status="not_connected",
        auth_method=None,
        account_label=None,
    )

    class Connections:
        def __init__(self) -> None:
            self.current = connection

        def list(self) -> tuple[sf.Connection, ...]:
            return (self.current,)

    class FutureClient:
        engine_url = "http://127.0.0.1:9108"
        connections = Connections()

    panel = sf.ConnectionPanel(FutureClient())  # type: ignore[arg-type]
    root = panel.widget()

    _button(root, "Connect").click()
    assert [button.description for button in _buttons(root)] == ["OAuth", "API key", "Cancel"]

    pending = sf.Connection(
        provider="future",
        display_name="Future Provider",
        auth_methods=("oauth", "api_key"),
        status="pending",
        auth_method="oauth",
        account_label=None,
    )
    FutureClient.connections.current = pending
    panel.refresh()
    assert [button.description for button in _buttons(root)] == ["Cancel"]
    root.close()


def test_hosted_panel_prompts_for_engine_login_before_loading_providers() -> None:
    connection = sf.Connection(
        provider="openrouter",
        display_name="OpenRouter",
        auth_methods=("api_key",),
        status="not_connected",
        auth_method=None,
        account_label=None,
    )

    class HostedConnections:
        calls = 0

        def list(self) -> tuple[sf.Connection, ...]:
            self.calls += 1
            return (connection,)

    class HostedClient:
        engine_url = "https://fusion.dev.screamingface.ai"
        connections = HostedConnections()

        def __init__(self) -> None:
            self.authenticated = False
            self.authenticating = False
            self.logins = 0
            self.logouts = 0

        def login(self, *, timeout: float = 300.0) -> None:
            assert timeout == 300
            self.logins += 1
            self.authenticated = True

        def logout(self) -> None:
            self.logouts += 1
            self.authenticated = False

    client = HostedClient()
    panel = sf.ConnectionPanel(client)  # type: ignore[arg-type]
    root = panel.widget()

    assert panel.connections == ()
    assert client.connections.calls == 0
    assert "Engine access" in _text(root)
    assert "login required" in _text(root)
    assert "OpenRouter" not in panel._repr_html_()
    assert [button.description for button in _buttons(root)] == ["Log in"]

    _button(root, "Log in").click()

    assert client.logins == 1
    assert client.connections.calls == 1
    assert panel.connections == (connection,)
    assert "authenticated" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Log out", "Connect"]

    _button(root, "Log out").click()

    assert client.logouts == 1
    assert panel.connections == ()
    assert client.connections.calls == 1
    assert [button.description for button in _buttons(root)] == ["Log in"]
    root.close()


def test_hosted_panel_shows_login_errors_without_loading_providers() -> None:
    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            raise AssertionError("providers must not load after a failed login")

    class RejectingClient:
        engine_url = "https://fusion.dev.screamingface.ai"
        authenticated = False
        authenticating = False
        connections = Connections()

        def login(self, *, timeout: float = 300.0) -> None:
            del timeout
            raise sf.AuthenticationError("Cloudflare Access login failed")

        def logout(self) -> None:
            self.authenticated = False

    panel = sf.ConnectionPanel(RejectingClient())  # type: ignore[arg-type]
    root = panel.widget()

    _button(root, "Log in").click()

    assert "Cloudflare Access login failed" in _text(root)
    assert "login required" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Log in"]
    root.close()


@pytest.mark.asyncio
async def test_hosted_panel_login_is_non_blocking_and_waiting_can_be_cancelled() -> None:
    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            return ()

    class WaitingClient:
        engine_url = "https://fusion.dev.screamingface.ai"
        authenticated = False
        authenticating = False
        connections = Connections()

        def __init__(self) -> None:
            self.started = threading.Event()
            self.cancelled = threading.Event()
            self.cancellations = 0
            self.logouts = 0

        def login(self, *, timeout: float = 300.0) -> None:
            del timeout
            self.authenticating = True
            self.started.set()
            self.cancelled.wait(1)
            self.authenticating = False
            raise sf.AuthenticationError(
                "Cloudflare Access login was cancelled",
                code="access_login_cancelled",
                permanent=False,
            )

        def _cancel_login(self) -> None:
            self.cancellations += 1
            self.authenticating = False
            self.cancelled.set()

        def logout(self) -> None:
            self.logouts += 1
            self.authenticated = False

    client = WaitingClient()
    panel = sf.ConnectionPanel(client)  # type: ignore[arg-type]
    root = panel.widget()

    started = time.monotonic()
    _button(root, "Log in").click()
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert client.started.wait(1)
    assert [button.description for button in _buttons(root)] == ["Cancel"]

    second_root = sf.ConnectionPanel(client).widget()  # type: ignore[arg-type]
    assert [button.description for button in _buttons(second_root)] == ["Cancel"]

    _button(second_root, "Cancel").click()
    for _ in range(100):
        if [button.description for button in _buttons(root)] == ["Log in"]:
            break
        await asyncio.sleep(0.01)

    assert client.authenticating is False
    assert client.cancellations == 1
    assert client.logouts == 0
    assert "cancelled" not in _text(root)
    assert [button.description for button in _buttons(root)] == ["Log in"]
    assert [button.description for button in _buttons(second_root)] == ["Log in"]
    root.close()
    second_root.close()


@pytest.mark.asyncio
async def test_hosted_panel_returns_to_login_after_cloudflare_denial() -> None:
    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            raise AssertionError("providers must not load after a denied login")

    class DeniedClient:
        engine_url = "https://fusion.dev.screamingface.ai"
        authenticated = False
        authenticating = False
        connections = Connections()

        def login(self, *, timeout: float = 300.0) -> None:
            del timeout
            self.authenticating = True
            self.authenticating = False
            raise sf.AuthenticationError(
                "Cloudflare Access rejected the browser login transfer",
                code="access_transfer_rejected",
                status=403,
            )

        def logout(self) -> None:
            self.authenticated = False

    panel = sf.ConnectionPanel(DeniedClient())  # type: ignore[arg-type]
    root = panel.widget()
    _button(root, "Log in").click()

    for _ in range(100):
        if "rejected" in _text(root):
            break
        await asyncio.sleep(0.01)

    assert "rejected" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Log in"]
    root.close()


@pytest.mark.asyncio
async def test_hosted_panel_shows_authenticated_when_provider_loading_fails() -> None:
    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            raise sf.ScreamingFaceError("The provider is not available on this SF Engine")

    class AuthenticatedClient:
        engine_url = "https://fusion.dev.screamingface.ai"
        authenticated = False
        authenticating = False
        connections = Connections()

        def login(self, *, timeout: float = 300.0) -> None:
            del timeout
            self.authenticated = True

        def _cancel_login(self) -> None:
            self.authenticating = False

        def logout(self) -> None:
            self.authenticated = False

    client = AuthenticatedClient()
    panel = sf.ConnectionPanel(client)  # type: ignore[arg-type]
    root = panel.widget()
    _button(root, "Log in").click()

    for _ in range(100):
        if "provider is not available" in _text(root):
            break
        await asyncio.sleep(0.01)

    assert client.authenticated is True
    assert "authenticated" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Log out"]
    root.close()


def test_authenticated_panel_renders_even_when_initial_provider_loading_fails() -> None:
    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            raise sf.ScreamingFaceError("Provider discovery is unavailable")

    class AuthenticatedClient:
        engine_url = "https://fusion.dev.screamingface.ai"
        authenticated = True
        authenticating = False
        connections = Connections()

        def logout(self) -> None:
            self.authenticated = False

    panel = sf.ConnectionPanel(AuthenticatedClient())  # type: ignore[arg-type]
    root = panel.widget()

    assert "Provider discovery is unavailable" in _text(root)
    assert "authenticated" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Log out"]
    root.close()


@pytest.mark.asyncio
async def test_all_open_panels_follow_shared_login_and_logout_state() -> None:
    client = _SharedAuthClient()
    first = sf.ConnectionPanel(client)  # type: ignore[arg-type]
    first_root = first.widget()
    _button(first_root, "Log in").click()
    assert client.started.wait(1)
    second = sf.ConnectionPanel(client)  # type: ignore[arg-type]
    second_root = second.widget()
    assert [button.description for button in _buttons(second_root)] == ["Cancel"]

    client.release.set()
    await _wait_for_button(second_root, "Log out")

    assert [button.description for button in _buttons(first_root)] == ["Log out"]
    assert [button.description for button in _buttons(second_root)] == ["Log out"]
    _button(first_root, "Log out").click()
    await _wait_for_button(second_root, "Log in")
    assert [button.description for button in _buttons(first_root)] == ["Log in"]
    assert [button.description for button in _buttons(second_root)] == ["Log in"]
    first_root.close()
    second_root.close()
    assert client.listeners == []


@pytest.mark.asyncio
async def test_unprotected_remote_engine_skips_the_access_login_row() -> None:
    connection = sf.Connection(
        provider="openrouter",
        display_name="OpenRouter",
        auth_methods=("api_key",),
        status="not_connected",
        auth_method=None,
        account_label=None,
    )

    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            return (connection,)

    class RemoteClient:
        engine_url = "https://remote-engine.example"
        authenticated = False
        authenticating = False
        connections = Connections()

        def _access_required(self) -> bool:
            return False

    panel = sf.ConnectionPanel(RemoteClient())  # type: ignore[arg-type]
    root = panel.widget()
    for _ in range(100):
        if "OpenRouter" in _text(root):
            break
        await asyncio.sleep(0.01)

    assert "Engine access" not in _text(root)
    assert "OpenRouter" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Connect"]
    root.close()


@pytest.mark.asyncio
async def test_unexpected_login_failure_does_not_leave_panel_waiting() -> None:
    class Client:
        engine_url = "https://fusion.dev.screamingface.ai"
        authenticated = False
        authenticating = False
        connections = _EmptyConnections()

        def login(self, *, timeout: float = 300.0) -> None:
            del timeout
            raise RuntimeError("Client closed during login")

    panel = sf.ConnectionPanel(Client())  # type: ignore[arg-type]
    root = panel.widget()
    _button(root, "Log in").click()
    await _wait_for_button(root, "Log in")

    assert "Client closed during login" in _text(root)
    root.close()
