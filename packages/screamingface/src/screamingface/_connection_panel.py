"""Rich Engine and provider connection panel bound to one ScreamingFace Client."""

from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable
from html import escape
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast
from urllib.parse import urlsplit

from screamingface._display import STYLE
from screamingface.errors import ScreamingFaceError

if TYPE_CHECKING:
    from screamingface.connections import Connection

type PanelMode = Literal["methods", "api_key"]


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


_STYLE = (
    STYLE
    + """<style>
.sf-connections{border:0;border-radius:0}
.sf-connection-widget.widget-vbox{border:0!important;box-shadow:none!important}
.sf-connections__head{height:48px;display:flex;align-items:center;gap:12px;padding:0 12px;
  border-bottom:1px solid var(--sf-line-2)}
.sf-connections__title{font-size:13px;font-weight:600}
.sf-connections__engine{margin-left:auto;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;color:var(--sf-ink-3);white-space:nowrap}
.sf-connections__row{height:48px!important;display:flex!important;flex-flow:row nowrap!important;
  align-items:center!important;gap:12px!important;padding:0 12px!important;
  border:0!important;border-bottom:1px solid var(--sf-line)!important}
.sf-connections__row:last-child{border-bottom:0!important}
.sf-connections__meta{display:grid;grid-template-columns:minmax(150px,1fr) 112px;
  align-items:center;gap:12px;width:100%;min-width:0}
.sf-connections__provider{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sf-connections__status{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;color:var(--sf-ink-3)}
.sf-connections__status.connected{color:var(--sf-gain)}
.sf-connections__status.authenticated{color:var(--sf-gain)}
.sf-connections__status.login_required,.sf-connections__status.waiting{color:var(--sf-blind)}
.sf-connections__status.needs_reauth,.sf-connections__status.error{color:var(--sf-blind)}
.sf-connections__account{color:var(--sf-ink-2);font-size:12px;font-weight:400}
.sf-connections__controls{flex:0 0 auto;margin-left:auto;display:flex;align-items:center;
  justify-content:flex-end;gap:4px;height:32px}
.sf-connections__notice{padding:8px 12px;border-bottom:1px solid var(--sf-line);
  border-left:2px solid var(--sf-blind);color:var(--sf-blind);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;white-space:pre-wrap}
.sf-connection-widget .widget-button,.sf-connection-widget .widget-text input{
  border-radius:0!important;box-shadow:none!important;background-image:none!important}
.sf-connection-widget .widget-button{height:32px!important;width:auto!important;
  padding:0 10px!important;border:1px solid var(--sf-line-2)!important;
  background:transparent!important;color:var(--sf-ink)!important;
  font:13px/1 "IBM Plex Mono",ui-monospace,monospace!important;white-space:nowrap}
.sf-connection-widget .widget-button:hover{background:var(--sf-surface)!important;
  border-color:var(--sf-ink-2)!important}
.sf-connection-widget .sf-button--primary{background:var(--sf-ink)!important;
  border-color:var(--sf-ink)!important;color:var(--sf-bg)!important}
.sf-connection-widget .sf-button--primary:hover{background:transparent!important;
  color:var(--sf-ink)!important}
.sf-connection-widget .widget-text{width:180px!important;height:32px!important}
.sf-connection-widget .widget-text input{height:32px!important;padding:0 8px!important;
  border:1px solid var(--sf-line-2)!important;background:var(--sf-bg)!important;
  color:var(--sf-ink)!important;font:13px/1 "IBM Plex Mono",ui-monospace,monospace!important}
.sf-connections__authorize{display:inline-flex;align-items:center;height:32px;padding:0 10px;
  border:1px solid var(--sf-ink);background:var(--sf-ink);color:var(--sf-bg)!important;
  font:13px/1 "IBM Plex Mono",ui-monospace,monospace;text-decoration:none!important}
.sf-connections__authorize:hover{background:transparent;color:var(--sf-ink)!important}
.sf-connection-widget .widget-hbox{align-items:center}
@media(max-width:680px){.sf-connections__engine{display:none}
  .sf-connections__meta{grid-template-columns:1fr 108px}
  .sf-connections__row{padding:0 8px!important;gap:8px!important}
  .sf-connection-widget .widget-text{width:140px!important}}
</style>"""
)


class ConnectionPanel:
    """A fresh Engine-scoped connection view with optional notebook controls."""

    def __init__(self, client: _Client) -> None:
        self.engine = client.engine_url
        self._client = client
        self._hosted = _is_hosted_engine(client.engine_url)
        self._connections: tuple[Connection, ...] = ()
        self._initial_notice: str | None = None
        if not self._hosted or client.authenticated:
            try:
                self._connections = client.connections.list()
            except (ScreamingFaceError, ValueError) as exc:
                self._initial_notice = _user_message(exc)
        self._access_pending = False
        self._access_check_pending = (
            self._hosted
            and not client.authenticated
            and callable(getattr(client, "_access_required", None))
        )
        self._access_check_started = False
        self._access_check_thread: threading.Thread | None = None
        self._login_thread: threading.Thread | None = None
        self._flows: dict[str, object] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._modes: dict[str, PanelMode] = {}
        self._rows: Any = None
        self._notice: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._unsubscribe_auth: Callable[[], None] | None = None
        self._closed = False

    @property
    def connections(self) -> tuple[Connection, ...]:
        return self._connections

    def refresh(self) -> tuple[Connection, ...]:
        self._connections = (
            self._client.connections.list()
            if not self._hosted or self._client.authenticated
            else ()
        )
        self._render_rows()
        return self._connections

    def widget(self):
        try:
            import ipywidgets as widgets
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Install screamingface[notebook] to use the interactive connection panel."
            ) from exc

        panel = self

        class PanelWidget(widgets.VBox):
            def close(self) -> None:
                panel.close()
                super().close()

        header = widgets.HTML(
            value=(
                f"{_STYLE}<div class='sf-connections__head'>"
                "<div class='sf-connections__title'>Connections</div>"
                f"<div class='sf-connections__engine'>Engine · {escape(self.engine)}</div></div>"
            )
        )
        self._notice = widgets.HTML()
        self._rows = widgets.VBox()
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
        root = PanelWidget(children=(header, self._notice, self._rows))
        for css_class in ("sf-ui", "sf-connection-widget", "sf-connections"):
            root.add_class(css_class)
        self._set_notice(self._initial_notice)
        self._render_rows()
        self._start_access_check()
        return root

    def _repr_html_(self) -> str:
        access = self._static_access_row() if self._hosted else ""
        rows = "".join(self._static_row(item) for item in self._connections)
        return (
            f"{_STYLE}<div class='sf-ui sf-connections' "
            "aria-label='ScreamingFace connections'>"
            "<div class='sf-connections__head'>"
            "<div class='sf-connections__title'>Connections</div>"
            f"<div class='sf-connections__engine'>Engine · {escape(self.engine)}</div></div>"
            f"{access}{rows}</div>"
        )

    def _ipython_display_(self) -> None:
        from IPython.display import display

        display(self.widget())

    def __repr__(self) -> str:
        statuses = ", ".join(f"{item.provider}={item.status}" for item in self._connections)
        access = (
            f", access={'authenticated' if self._client.authenticated else 'login_required'}"
            if self._hosted
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

    def _meta_html(self, connection: Connection) -> str:
        account = (
            f" <span class='sf-connections__account'>({escape(connection.account_label)})</span>"
            if connection.account_label
            else ""
        )
        return (
            "<div class='sf-connections__meta'>"
            f"<span class='sf-connections__provider'>{escape(connection.display_name)}"
            f"{account}</span>"
            f"<div class='sf-connections__status {connection.status}'>"
            f"{escape(connection.status.replace('_', ' '))}</div></div>"
        )

    def _static_row(self, connection: Connection) -> str:
        return f"<div class='sf-connections__row'>{self._meta_html(connection)}</div>"

    def _access_meta_html(self) -> str:
        if self._access_check_pending:
            status = "checking"
        elif self._access_waiting():
            status = "waiting"
        elif self._client.authenticated:
            status = "authenticated"
        else:
            status = "login_required"
        return (
            "<div class='sf-connections__meta'>"
            "<span class='sf-connections__provider'>Engine access</span>"
            f"<div class='sf-connections__status {status}'>"
            f"{escape(status.replace('_', ' '))}</div></div>"
        )

    def _static_access_row(self) -> str:
        return f"<div class='sf-connections__row'>{self._access_meta_html()}</div>"

    def _render_rows(self) -> None:
        if self._rows is not None:
            access = (self._interactive_access_row(),) if self._hosted else ()
            providers = tuple(self._interactive_row(item) for item in self._connections)
            self._rows.children = (*access, *providers)

    def _interactive_access_row(self):
        import ipywidgets as widgets

        meta = widgets.HTML(value=self._access_meta_html())
        meta.layout.flex = "1 1 auto"
        meta.layout.min_width = "0"
        if self._access_check_pending:
            button = self._button("Checking…", "Checking whether this Engine requires Access")
            button.disabled = True
        elif self._access_waiting():
            button = self._button("Cancel", "Cancel the Cloudflare Access login")
            button.on_click(lambda _: self._attempt(self._cancel_access_login))
        elif self._client.authenticated:
            button = self._button("Log out", "Log out of this Client and Cloudflare Access")
            button.on_click(lambda _: self._attempt(self._logout_access))
        else:
            button = self._button(
                "Log in",
                "Log in to this Engine through Cloudflare Access",
                primary=True,
            )
            button.on_click(lambda _: self._start_login_access())
        controls = widgets.HBox(children=(button,))
        controls.add_class("sf-connections__controls")
        controls.layout.flex = "0 0 auto"
        row = widgets.HBox(children=(meta, controls))
        row.add_class("sf-connections__row")
        row.layout.align_items = "center"
        row.layout.flex_flow = "row nowrap"
        row.layout.height = "48px"
        return row

    def _interactive_row(self, connection: Connection):
        import ipywidgets as widgets

        meta = widgets.HTML(value=self._meta_html(connection))
        meta.layout.flex = "1 1 auto"
        meta.layout.min_width = "0"
        controls = widgets.HBox(children=tuple(self._controls_for(connection)))
        controls.add_class("sf-connections__controls")
        controls.layout.flex = "0 0 auto"
        row = widgets.HBox(children=(meta, controls))
        row.add_class("sf-connections__row")
        row.layout.align_items = "center"
        row.layout.flex_flow = "row nowrap"
        row.layout.height = "48px"
        return row

    def _controls_for(self, connection: Connection) -> list[Any]:
        if connection.provider in self._flows:
            controls = self._oauth_controls(connection)
        elif connection.status == "pending":
            controls = self._pending_controls(connection)
        elif connection.status == "connected":
            controls = self._connected_controls(connection)
        elif self._modes.get(connection.provider) == "methods":
            controls = self._method_controls(connection)
        elif self._modes.get(connection.provider) == "api_key":
            controls = self._api_key_controls(connection)
        else:
            controls = self._collapsed_controls(connection)
        return controls

    def _collapsed_controls(self, connection: Connection) -> list[Any]:
        button = self._button("Connect", "Choose how to connect this provider", primary=True)
        button.on_click(lambda _: self._show_methods(connection.provider))
        return [button]

    def _method_controls(self, connection: Connection) -> list[Any]:
        controls: list[Any] = []
        if "oauth" in connection.auth_methods:
            oauth = self._button("OAuth", "Start provider OAuth authorization")
            oauth.on_click(
                lambda _: self._attempt(
                    lambda: self._set_notice("OAuth is not advertised by this Engine yet.")
                )
            )
            controls.append(oauth)
        if "api_key" in connection.auth_methods:
            api_key = self._button("API key", "Enter an API key for this provider")
            api_key.on_click(lambda _: self._show_api_key(connection.provider))
            controls.append(api_key)
        cancel = self._button("Cancel", "Close connection options")
        cancel.on_click(lambda _: self._cancel_mode(connection.provider))
        controls.append(cancel)
        return controls

    def _api_key_controls(self, connection: Connection) -> list[Any]:
        import ipywidgets as widgets

        password = widgets.Password(placeholder="API key")
        password.layout.width = "180px"
        save = self._button("Save", "Store this API key in the configured Engine", primary=True)

        def submit(_: Any) -> None:
            key = password.value
            try:
                self._attempt(lambda: self._submit_api_key(connection.provider, key))
            finally:
                password.value = ""

        save.on_click(submit)
        cancel = self._button("Cancel", "Close the API key editor")
        cancel.on_click(lambda _: self._cancel_mode(connection.provider))
        return [password, save, cancel]

    def _connected_controls(self, connection: Connection) -> list[Any]:
        button = self._button("Disconnect", "Remove this provider connection")
        button.on_click(lambda _: self._attempt(lambda: self._disconnect(connection.provider)))
        return [button]

    def _pending_controls(self, connection: Connection) -> list[Any]:
        button = self._button("Cancel", "Cancel the pending OAuth authorization")
        button.on_click(lambda _: self._attempt(lambda: self._disconnect(connection.provider)))
        return [button]

    def _oauth_controls(self, connection: Connection) -> list[Any]:
        # Kept as the rendering seam for a future Engine-advertised OAuthFlow.
        import ipywidgets as widgets

        flow = self._flows[connection.provider]
        authorize_url = escape(str(getattr(flow, "authorize_url", "")), quote=True)
        link = widgets.HTML(
            value=(
                "<a class='sf-connections__authorize' "
                f"href='{authorize_url}' target='_blank' rel='noopener noreferrer'>Authorize</a>"
            )
        )
        cancel = self._button("Cancel", "Cancel this OAuth authorization attempt")
        cancel.on_click(lambda _: self._cancel_flow(connection.provider))
        return [link, cancel]

    def _button(self, description: str, tooltip: str, *, primary: bool = False):
        import ipywidgets as widgets

        button = widgets.Button(description=description, tooltip=tooltip)
        button.add_class("sf-button")
        if primary:
            button.add_class("sf-button--primary")
        return button

    def _show_methods(self, provider: str) -> None:
        self._modes[provider] = "methods"
        self._render_rows()

    def _show_api_key(self, provider: str) -> None:
        self._modes[provider] = "api_key"
        self._render_rows()

    def _cancel_mode(self, provider: str) -> None:
        self._modes.pop(provider, None)
        self._render_rows()

    def _attempt(self, action: Any) -> None:
        self._set_notice(None)
        try:
            action()
        except (ScreamingFaceError, ValueError) as exc:
            self._set_notice(_user_message(exc))

    def _set_notice(self, message: str | None) -> None:
        if self._notice is not None:
            self._notice.value = (
                ""
                if message is None
                else f"<div class='sf-connections__notice' role='alert'>{escape(message)}</div>"
            )

    def _submit_api_key(self, provider: str, api_key: str) -> None:
        self._client.connect(provider, api_key=api_key)
        self._modes.pop(provider, None)
        self.refresh()

    def _login_access(self) -> None:
        self._client.login()

    def _access_waiting(self) -> bool:
        return self._access_pending or self._client.authenticating

    def _start_login_access(self) -> None:
        self._set_notice(None)
        if self._access_waiting():
            self._render_rows()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Non-notebook callers have no live event loop to keep the widget responsive.
            self._attempt(self._login_access)
            if self._client.authenticated:
                self.refresh()
            else:
                self._render_rows()
            return

        self._access_pending = True
        self._render_rows()
        self._start_login_thread(loop)

    def _start_access_check(self) -> None:
        if not self._access_check_pending or self._access_check_started:
            return
        check = getattr(self._client, "_access_required", None)
        if not callable(check):
            self._access_check_pending = False
            self._render_rows()
            return
        self._access_check_started = True
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
        self._access_check_pending = False
        self._access_check_thread = None
        if error is not None:
            self._set_notice(_user_message(error))
        elif not required:
            self._hosted = False
            try:
                self._connections = self._client.connections.list()
            except (ScreamingFaceError, ValueError) as exc:
                self._connections = ()
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
                # The notebook event loop may have closed while its browser was open.
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
        self._access_pending = False
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
        self._access_pending = self._client.authenticating
        if self._client.authenticated:
            try:
                self._connections = self._client.connections.list()
            except (ScreamingFaceError, ValueError) as exc:
                self._connections = ()
                self._set_notice(_user_message(exc))
        else:
            self._connections = ()
        self._render_rows()

    def _logout_access(self) -> None:
        self._client.logout()
        self._access_pending = False
        self._connections = ()
        self._render_rows()

    def _cancel_access_login(self) -> None:
        self._client._cancel_login()
        self._access_pending = False
        self._connections = ()
        self._render_rows()

    def _disconnect(self, provider: str) -> None:
        self._client.disconnect(provider)
        self._modes.pop(provider, None)
        self._cancel_flow(provider)
        self.refresh()

    def _cancel_flow(self, provider: str) -> None:
        flow = self._flows.pop(provider, None)
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
