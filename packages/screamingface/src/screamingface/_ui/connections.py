"""Engine connection-panel controller, independent of notebook rendering details."""

from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import urlsplit

from screamingface._ui.connection_state import _ConnectionPanelState
from screamingface._ui.connection_view import (
    _NotebookConnectionView,
    static_panel_html,
)
from screamingface.errors import ScreamingFaceError

if TYPE_CHECKING:
    from screamingface.connections import Connection


class _ConnectionCatalog(Protocol):
    def list(self) -> tuple[Connection, ...]: ...


class _Client(Protocol):
    @property
    def engine_url(self) -> str: ...

    @property
    def connections(self) -> _ConnectionCatalog: ...

    @property
    def authenticated(self) -> bool: ...

    @property
    def authenticating(self) -> bool: ...

    def login(self, *, timeout: float = 300.0) -> None: ...

    def _cancel_login(self) -> None: ...

    def _subscribe_auth(self, callback: Callable[[], None]) -> Callable[[], None]: ...

    def _access_required(self) -> bool: ...

    def logout(self) -> None: ...

    def connect(self, provider: str, *, api_key: str) -> Connection: ...

    def disconnect(self, provider: str) -> Connection: ...


class ConnectionPanel:
    """A fresh Engine-scoped connection view with optional notebook controls."""

    def __init__(self, client: _Client) -> None:
        self.engine = client.engine_url
        self._client = client
        hosted = _is_hosted_engine(client.engine_url)
        self._state = _ConnectionPanelState(
            hosted=hosted,
            access_check_pending=(
                hosted
                and not client.authenticated
                and callable(getattr(client, "_access_required", None))
            ),
        )
        if not hosted or client.authenticated:
            try:
                self._state.connections = client.connections.list()
            except (ScreamingFaceError, ValueError) as exc:
                self._state.notice = _user_message(exc)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._access_check_thread: threading.Thread | None = None
        self._login_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._unsubscribe_auth: Callable[[], None] | None = None
        self._view: _NotebookConnectionView | None = None
        self._closed = False

    @property
    def connections(self) -> tuple[Connection, ...]:
        return self._state.connections

    @property
    def authenticated(self) -> bool:
        return self._client.authenticated

    @property
    def authenticating(self) -> bool:
        return self._client.authenticating

    def refresh(self) -> tuple[Connection, ...]:
        self._state.connections = (
            self._client.connections.list()
            if not self._state.hosted or self._client.authenticated
            else ()
        )
        self._render_rows()
        return self._state.connections

    def widget(self):
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        subscribe = getattr(self._client, "_subscribe_auth", None)
        if callable(subscribe) and self._unsubscribe_auth is None:
            typed_subscribe = cast(
                Callable[[Callable[[], None]], Callable[[], None]],
                subscribe,
            )
            self._unsubscribe_auth = typed_subscribe(self._auth_state_changed)
        self._view = _NotebookConnectionView(self, self._state)
        self._start_access_check()
        return self._view.root

    def _repr_html_(self) -> str:
        return static_panel_html(
            self.engine,
            self._state,
            authenticated=self._client.authenticated if self._state.hosted else False,
            authenticating=self._client.authenticating if self._state.hosted else False,
        )

    def _ipython_display_(self) -> None:
        from IPython.display import display

        display(self.widget())

    def __repr__(self) -> str:
        statuses = ", ".join(f"{item.provider}={item.status}" for item in self._state.connections)
        access = (
            f", access={'authenticated' if self._client.authenticated else 'login_required'}"
            if self._state.hosted
            else ""
        )
        return f"ConnectionPanel(engine={self.engine!r}{access}, {statuses})"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._unsubscribe_auth is not None:
            self._unsubscribe_auth()
            self._unsubscribe_auth = None
        self._login_thread = None
        self._access_check_thread = None
        for task in tuple(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    def _render_rows(self) -> None:
        if self._view is not None:
            self._view.render()

    def _show_methods(self, provider: str) -> None:
        self._state.modes[provider] = "methods"
        self._render_rows()

    def _show_api_key(self, provider: str) -> None:
        self._state.modes[provider] = "api_key"
        self._render_rows()

    def _cancel_mode(self, provider: str) -> None:
        self._state.modes.pop(provider, None)
        self._render_rows()

    def _attempt(self, action: Callable[[], Any]) -> None:
        self._set_notice(None)
        try:
            action()
        except (ScreamingFaceError, ValueError) as exc:
            self._set_notice(_user_message(exc))

    def _set_notice(self, message: str | None) -> None:
        self._state.notice = message
        if self._view is not None:
            self._view.render_notice()

    def _submit_api_key(self, provider: str, api_key: str) -> None:
        self._client.connect(provider, api_key=api_key)
        self._state.modes.pop(provider, None)
        self.refresh()

    def _login_access(self) -> None:
        self._client.login()

    def _access_waiting(self) -> bool:
        return self._state.access_pending or self._client.authenticating

    def _start_login_access(self) -> None:
        self._set_notice(None)
        if self._access_waiting():
            self._render_rows()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._attempt(self._login_access)
            if self._client.authenticated:
                self.refresh()
            else:
                self._render_rows()
            return

        self._state.access_pending = True
        self._render_rows()
        self._start_login_thread(loop)

    def _start_access_check(self) -> None:
        if not self._state.access_check_pending or self._state.access_check_started:
            return
        check = getattr(self._client, "_access_required", None)
        if not callable(check):
            self._state.access_check_pending = False
            self._render_rows()
            return
        self._state.access_check_started = True
        typed_check = cast(Callable[[], bool], check)
        if self._loop is None:
            self._run_access_check_sync(typed_check)
            return
        self._start_access_check_thread(typed_check, self._loop)

    def _run_access_check_sync(self, check: Callable[[], bool]) -> None:
        try:
            required = check()
        except Exception as exc:
            self._complete_access_check(True, exc)
        else:
            self._complete_access_check(required, None)

    def _start_access_check_thread(
        self,
        check: Callable[[], bool],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        panel_ref = weakref.ref(self)

        def run() -> None:
            required = True
            error: Exception | None = None
            try:
                required = check()
            except Exception as exc:
                error = exc
            panel = panel_ref()
            if panel is None or panel._closed:
                return
            try:
                loop.call_soon_threadsafe(panel._complete_access_check, required, error)
            except RuntimeError:
                return

        self._access_check_thread = threading.Thread(
            target=run,
            name="screamingface-access-discovery",
            daemon=True,
        )
        self._access_check_thread.start()

    def _complete_access_check(self, required: bool, error: Exception | None) -> None:
        if self._closed:
            return
        self._state.access_check_pending = False
        self._access_check_thread = None
        if error is not None:
            self._set_notice(_user_message(error))
        elif not required:
            self._state.hosted = False
            try:
                self._state.connections = self._client.connections.list()
            except (ScreamingFaceError, ValueError) as exc:
                self._state.connections = ()
                self._set_notice(_user_message(exc))
        self._render_rows()

    def _start_login_thread(self, loop: asyncio.AbstractEventLoop) -> None:
        client = self._client
        panel_ref = weakref.ref(self)

        def run() -> None:
            error: Exception | None = None
            try:
                client.login()
            except Exception as exc:
                error = exc
            panel = panel_ref()
            if panel is None or panel._closed:
                return
            try:
                loop.call_soon_threadsafe(panel._complete_login_access, error)
            except RuntimeError:
                return

        self._login_thread = threading.Thread(
            target=run,
            name="screamingface-access-login",
            daemon=True,
        )
        self._login_thread.start()

    def _complete_login_access(self, error: Exception | None) -> None:
        if self._closed:
            return
        self._state.access_pending = False
        self._login_thread = None
        if error is not None and getattr(error, "code", None) != "access_login_cancelled":
            self._set_notice(_user_message(error))
        if self._client.authenticated:
            try:
                self.refresh()
            except (ScreamingFaceError, ValueError) as exc:
                self._set_notice(_user_message(exc))
                self._render_rows()
        else:
            self._render_rows()

    def _auth_state_changed(self) -> None:
        if self._closed:
            return
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._apply_auth_state)
            except RuntimeError:
                return
        else:
            self._apply_auth_state()

    def _apply_auth_state(self) -> None:
        if self._closed:
            return
        self._state.access_pending = self._client.authenticating
        if self._client.authenticated:
            try:
                self._state.connections = self._client.connections.list()
            except (ScreamingFaceError, ValueError) as exc:
                self._state.connections = ()
                self._set_notice(_user_message(exc))
        else:
            self._state.connections = ()
        self._render_rows()

    def _logout_access(self) -> None:
        self._client.logout()
        self._state.access_pending = False
        self._state.connections = ()
        self._render_rows()

    def _cancel_access_login(self) -> None:
        self._client._cancel_login()
        self._state.access_pending = False
        self._state.connections = ()
        self._render_rows()

    def _disconnect(self, provider: str) -> None:
        self._client.disconnect(provider)
        self._state.modes.pop(provider, None)
        self._cancel_flow(provider)
        self.refresh()

    def _cancel_flow(self, provider: str) -> None:
        flow = self._state.flows.pop(provider, None)
        cancel = getattr(flow, "cancel", None)
        if callable(cancel):
            cancel()
        task = self._tasks.pop(provider, None)
        if task is not None:
            task.cancel()


def _is_hosted_engine(engine_url: str) -> bool:
    hostname = urlsplit(engine_url).hostname
    if hostname == "localhost":
        return False
    try:
        address = ip_address(hostname or "")
    except ValueError:
        return True
    return not (address.is_loopback or address.is_unspecified)


def _user_message(error: Exception) -> str:
    message = getattr(error, "user_message", None)
    return message if isinstance(message, str) else str(error)


__all__ = ["ConnectionPanel"]
