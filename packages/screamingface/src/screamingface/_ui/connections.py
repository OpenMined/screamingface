"""Engine connection-panel controller, independent of notebook rendering details."""

from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast, overload

from screamingface._ui.connection_state import (
    _ConnectionPanelState,
    _sync_access_probe,
    _user_message,
)
from screamingface._ui.connection_view import (
    _NotebookConnectionView,
    _provider_status,
    static_panel_html,
)
from screamingface._ui.engine_origin import _is_hosted_engine
from screamingface._ui.loop_dispatch import _CompletionDispatcher
from screamingface.errors import ScreamingFaceError

if TYPE_CHECKING:
    from ipywidgets import Widget

    from screamingface.connections import Connection, OAuthFlow


class _ConnectionCatalog(Protocol):
    def list(self) -> tuple[Connection, ...]: ...

    def get(self, provider: str) -> Connection: ...


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

    @overload
    def connect(
        self,
        provider: str,
        *,
        api_key: str,
        method: Literal["api_key"] | None = None,
    ) -> Connection: ...

    @overload
    def connect(
        self,
        provider: str,
        *,
        api_key: None = None,
        method: Literal["oauth"],
    ) -> OAuthFlow: ...

    def disconnect(self, provider: str) -> Connection: ...


class ConnectionPanel:
    """A fresh Engine-scoped connection view with optional notebook controls."""

    def __init__(self, client: _Client) -> None:
        self.engine: str = client.engine_url
        self._client = client
        hosted = _is_hosted_engine(client.engine_url)
        self._state = _ConnectionPanelState(
            hosted=hosted,
            engine_url=client.engine_url,
            # Temporary tester-release policy: only a loopback Engine exposes BYOK controls.
            # Keep this separate from `hosted`, which may later be cleared when a remote Engine
            # reports that it does not require Cloudflare Access.
            provider_mutations_enabled=not hosted,
            access_check_pending=(
                hosted and not client.authenticated and _sync_access_probe(client) is not None
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
        self._dispatcher = _CompletionDispatcher()
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

    def widget(self) -> Widget:
        self._dispatcher.capture()
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
        provider_mutations_enabled = self._state.provider_mutations_enabled
        statuses = ", ".join(
            f"{item.provider}="
            f"{_provider_status(item, provider_mutations_enabled=provider_mutations_enabled)}"
            for item in self._state.connections
        )
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
        except (ScreamingFaceError, RuntimeError, ValueError) as exc:
            self._set_notice(_user_message(exc))

    def _set_notice(self, message: str | None) -> None:
        self._state.notice = message
        if self._view is not None:
            self._view.render_notice()

    def _submit_api_key(self, provider: str, api_key: str) -> None:
        self._client.connect(provider, api_key=api_key)
        self._state.modes.pop(provider, None)
        self.refresh()

    def _start_oauth(self, provider: str) -> None:
        flow = self._client.connect(provider, method="oauth")
        if not hasattr(flow, "authorize_url"):
            raise ValueError("the Engine did not start an OAuth authorization")
        self._state.modes.pop(provider, None)
        self._state.flows[provider] = flow
        self._render_rows()
        # WHY: Jupyter may render a widget and later dispatch its button callback on a
        # different event loop. Always prefer the loop active for this click; scheduling
        # the poller on the loop cached by ``widget()`` can leave it dormant forever.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = self._dispatcher.loop
        if loop is None or loop.is_closed():
            return
        self._dispatcher.adopt(loop)
        self._tasks[provider] = loop.create_task(self._poll_oauth(provider, flow))

    async def _poll_oauth(self, provider: str, flow: object) -> None:
        try:
            while self._state.flows.get(provider) is flow:
                if bool(getattr(flow, "expired", False)):
                    raise ValueError(f"OAuth authorization for {provider!r} expired")
                connection = await asyncio.to_thread(self._client.connections.get, provider)
                if connection.status != "pending":
                    self._state.flows.pop(provider, None)
                    self._state.connections = await asyncio.to_thread(self._client.connections.list)
                    self._render_rows()
                    return
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except (ScreamingFaceError, RuntimeError, ValueError) as exc:
            self._state.flows.pop(provider, None)
            self._set_notice(_user_message(exc))
            self._render_rows()
        finally:
            current = asyncio.current_task()
            if self._tasks.get(provider) is current:
                self._tasks.pop(provider, None)

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
            asyncio.get_running_loop()
        except RuntimeError:
            self._attempt(self._login_access)
            if self._client.authenticated:
                self.refresh()
            else:
                self._render_rows()
            return

        self._state.access_pending = True
        self._render_rows()
        self._start_login_thread()

    def _start_access_check(self) -> None:
        if not self._state.access_check_pending or self._state.access_check_started:
            return
        check = _sync_access_probe(self._client)
        if check is None:
            self._state.access_check_pending = False
            self._render_rows()
            return
        self._state.access_check_started = True
        # WHY: "checking" is only shown once the probe is in flight, so the row has to be
        # re-rendered here — the view was built before the check started.
        self._render_rows()
        if self._dispatcher.loop is None:
            self._run_access_check_sync(check)
            return
        self._start_access_check_thread(check)

    def _run_access_check_sync(self, check: Callable[[], bool]) -> None:
        try:
            required = check()
        except Exception as exc:
            self._complete_access_check(True, exc)
        else:
            self._complete_access_check(required, None)

    def _start_access_check_thread(self, check: Callable[[], bool]) -> None:
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
            panel._dispatcher(panel._complete_access_check, required, error)

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

    def _start_login_thread(self) -> None:
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
            panel._dispatcher(panel._complete_login_access, error)

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
        self._dispatcher(self._apply_auth_state)

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
        self._drop_flow(provider)
        self.refresh()

    def _cancel_flow(self, provider: str) -> None:
        flow = self._state.flows.pop(provider, None)
        cancel = getattr(flow, "cancel", None)
        if callable(cancel):
            cancel()
        self._drop_flow(provider)
        self._state.modes.pop(provider, None)
        self.refresh()

    def _drop_flow(self, provider: str) -> None:
        self._state.flows.pop(provider, None)
        task = self._tasks.pop(provider, None)
        if task is not None:
            task.cancel()


__all__ = ["ConnectionPanel"]
