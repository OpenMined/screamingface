"""Static HTML and ipywidgets adapters for the connection-panel controller."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, Protocol

from screamingface._ui.connection_state import _ConnectionPanelState
from screamingface._ui.style import STYLE

if TYPE_CHECKING:
    from screamingface.connections import Connection


class _PanelController(Protocol):
    engine: str

    @property
    def authenticated(self) -> bool: ...

    @property
    def authenticating(self) -> bool: ...

    def close(self) -> None: ...

    def _attempt(self, action: Any) -> None: ...

    def _cancel_access_login(self) -> None: ...

    def _cancel_flow(self, provider: str) -> None: ...

    def _cancel_mode(self, provider: str) -> None: ...

    def _disconnect(self, provider: str) -> None: ...

    def _logout_access(self) -> None: ...

    def _show_api_key(self, provider: str) -> None: ...

    def _show_methods(self, provider: str) -> None: ...

    def _start_login_access(self) -> None: ...

    def _start_oauth(self, provider: str) -> None: ...

    def _set_notice(self, message: str | None) -> None: ...

    def _submit_api_key(self, provider: str, api_key: str) -> None: ...


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


def static_panel_html(
    engine: str,
    state: _ConnectionPanelState,
    *,
    authenticated: bool,
    authenticating: bool,
) -> str:
    access = (
        _static_access_row(state, authenticated=authenticated, authenticating=authenticating)
        if state.hosted
        else ""
    )
    rows = "".join(_static_row(item) for item in state.connections)
    return (
        f"{_STYLE}<div class='sf-ui sf-connections' "
        "aria-label='ScreamingFace connections'>"
        f"{_header_html(engine)}{access}{rows}</div>"
    )


class _NotebookConnectionView:
    """ipywidgets adapter; all mutations are delegated to the controller."""

    def __init__(self, controller: _PanelController, state: _ConnectionPanelState) -> None:
        try:
            import ipywidgets as widgets
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Install screamingface[notebook] to use the interactive connection panel."
            ) from exc

        self._widgets = widgets
        self._controller = controller
        self._state = state
        self._notice = widgets.HTML()
        self._rows = widgets.VBox()

        view = self

        class PanelWidget(widgets.VBox):
            def close(self) -> None:
                view._controller.close()
                super().close()

        header = widgets.HTML(value=f"{_STYLE}{_header_html(controller.engine)}")
        self.root = PanelWidget(children=(header, self._notice, self._rows))
        for css_class in ("sf-ui", "sf-connection-widget", "sf-connections"):
            self.root.add_class(css_class)
        self.render()

    def render(self) -> None:
        self.render_notice()
        access = (self._interactive_access_row(),) if self._state.hosted else ()
        providers = tuple(self._interactive_row(item) for item in self._state.connections)
        self._rows.children = (*access, *providers)

    def render_notice(self) -> None:
        self._notice.value = _notice_html(self._state.notice)

    def _interactive_access_row(self):
        widgets = self._widgets
        status = self._state.access_status(
            authenticated=self._controller.authenticated,
            authenticating=self._controller.authenticating,
        )
        meta = widgets.HTML(value=_access_meta_html(status))
        meta.layout.flex = "1 1 auto"
        meta.layout.min_width = "0"
        if status == "checking":
            button = self._button("Checking…", "Checking whether this Engine requires Access")
            button.disabled = True
        elif status == "waiting":
            button = self._button("Cancel", "Cancel the Cloudflare Access login")
            button.on_click(
                lambda _: self._controller._attempt(self._controller._cancel_access_login)
            )
        elif status == "authenticated":
            button = self._button("Log out", "Log out of this Client and Cloudflare Access")
            button.on_click(lambda _: self._controller._attempt(self._controller._logout_access))
        else:
            button = self._button(
                "Log in",
                "Log in to this Engine through Cloudflare Access",
                primary=True,
            )
            button.on_click(lambda _: self._controller._start_login_access())
        return self._row(meta, [button])

    def _interactive_row(self, connection: Connection):
        widgets = self._widgets
        meta = widgets.HTML(value=_meta_html(connection))
        meta.layout.flex = "1 1 auto"
        meta.layout.min_width = "0"
        return self._row(meta, self._controls_for(connection))

    def _row(self, meta: Any, controls_: list[Any]):
        widgets = self._widgets
        controls = widgets.HBox(children=tuple(controls_))
        controls.add_class("sf-connections__controls")
        controls.layout.flex = "0 0 auto"
        row = widgets.HBox(children=(meta, controls))
        row.add_class("sf-connections__row")
        row.layout.align_items = "center"
        row.layout.flex_flow = "row nowrap"
        row.layout.height = "48px"
        return row

    def _controls_for(self, connection: Connection) -> list[Any]:
        if connection.provider in self._state.flows:
            controls = self._oauth_controls(connection)
        elif connection.status == "pending":
            controls = self._pending_controls(connection)
        elif connection.status == "connected":
            controls = self._connected_controls(connection)
        elif self._state.modes.get(connection.provider) == "methods":
            controls = self._method_controls(connection)
        elif self._state.modes.get(connection.provider) == "api_key":
            controls = self._api_key_controls(connection)
        else:
            controls = self._collapsed_controls(connection)
        return controls

    def _collapsed_controls(self, connection: Connection) -> list[Any]:
        button = self._button("Connect", "Choose how to connect this provider", primary=True)
        button.on_click(lambda _: self._controller._show_methods(connection.provider))
        return [button]

    def _method_controls(self, connection: Connection) -> list[Any]:
        controls: list[Any] = []
        if "oauth" in connection.auth_methods:
            oauth = self._button("OAuth", "Start provider OAuth authorization")
            oauth.on_click(
                lambda _: self._controller._attempt(
                    lambda: self._controller._start_oauth(connection.provider)
                )
            )
            controls.append(oauth)
        if "api_key" in connection.auth_methods:
            api_key = self._button("API key", "Enter an API key for this provider")
            api_key.on_click(lambda _: self._controller._show_api_key(connection.provider))
            controls.append(api_key)
        cancel = self._button("Cancel", "Close connection options")
        cancel.on_click(lambda _: self._controller._cancel_mode(connection.provider))
        controls.append(cancel)
        return controls

    def _api_key_controls(self, connection: Connection) -> list[Any]:
        password = self._widgets.Password(placeholder="API key")
        password.layout.width = "180px"
        save = self._button("Save", "Store this API key in the configured Engine", primary=True)

        def submit(_: Any) -> None:
            key = password.value
            try:
                self._controller._attempt(
                    lambda: self._controller._submit_api_key(connection.provider, key)
                )
            finally:
                password.value = ""

        save.on_click(submit)
        cancel = self._button("Cancel", "Close the API key editor")
        cancel.on_click(lambda _: self._controller._cancel_mode(connection.provider))
        return [password, save, cancel]

    def _connected_controls(self, connection: Connection) -> list[Any]:
        button = self._button("Disconnect", "Remove this provider connection")
        button.on_click(
            lambda _: self._controller._attempt(
                lambda: self._controller._disconnect(connection.provider)
            )
        )
        return [button]

    def _pending_controls(self, connection: Connection) -> list[Any]:
        button = self._button("Cancel", "Cancel the pending OAuth authorization")
        button.on_click(
            lambda _: self._controller._attempt(
                lambda: self._controller._disconnect(connection.provider)
            )
        )
        return [button]

    def _oauth_controls(self, connection: Connection) -> list[Any]:
        flow = self._state.flows[connection.provider]
        authorize_url = escape(str(getattr(flow, "authorize_url", "")), quote=True)
        link = self._widgets.HTML(
            value=(
                "<a class='sf-connections__authorize' "
                f"href='{authorize_url}' target='_blank' rel='noopener noreferrer'>Authorize</a>"
            )
        )
        cancel = self._button("Cancel", "Cancel this OAuth authorization attempt")
        cancel.on_click(
            lambda _: self._controller._attempt(
                lambda: self._controller._cancel_flow(connection.provider)
            )
        )
        return [link, cancel]

    def _button(self, description: str, tooltip: str, *, primary: bool = False):
        button = self._widgets.Button(description=description, tooltip=tooltip)
        button.add_class("sf-button")
        if primary:
            button.add_class("sf-button--primary")
        return button


def _header_html(engine: str) -> str:
    return (
        "<div class='sf-connections__head'>"
        "<div class='sf-connections__title'>Connections</div>"
        f"<div class='sf-connections__engine'>Engine · {escape(engine)}</div></div>"
    )


def _meta_html(connection: Connection) -> str:
    account = (
        f" <span class='sf-connections__account'>({escape(connection.account_label)})</span>"
        if connection.account_label
        else ""
    )
    return (
        "<div class='sf-connections__meta'>"
        f"<span class='sf-connections__provider'>{escape(connection.display_name)}{account}</span>"
        f"<div class='sf-connections__status {connection.status}'>"
        f"{escape(connection.status.replace('_', ' '))}</div></div>"
    )


def _static_row(connection: Connection) -> str:
    return f"<div class='sf-connections__row'>{_meta_html(connection)}</div>"


def _access_meta_html(status: str) -> str:
    return (
        "<div class='sf-connections__meta'>"
        "<span class='sf-connections__provider'>Engine access</span>"
        f"<div class='sf-connections__status {status}'>"
        f"{escape(status.replace('_', ' '))}</div></div>"
    )


def _static_access_row(
    state: _ConnectionPanelState,
    *,
    authenticated: bool,
    authenticating: bool,
) -> str:
    status = state.access_status(
        authenticated=authenticated,
        authenticating=authenticating,
    )
    return f"<div class='sf-connections__row'>{_access_meta_html(status)}</div>"


def _notice_html(message: str | None) -> str:
    if message is None:
        return ""
    return f"<div class='sf-connections__notice' role='alert'>{escape(message)}</div>"


__all__: list[str] = []
