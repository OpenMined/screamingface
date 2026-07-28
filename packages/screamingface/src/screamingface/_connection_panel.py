"""Dependency-light provider panel with optional ipywidgets interaction."""

from __future__ import annotations

import asyncio
from html import escape
from typing import TYPE_CHECKING, Any, Literal

from screamingface import connections as connection_api
from screamingface._config import current_engine_url
from screamingface._display import STYLE
from screamingface._profile import ProviderRecord, Registry, load_registry
from screamingface.errors import ScreamingFaceError

if TYPE_CHECKING:
    from screamingface.connections import Connection, OAuthFlow

type PanelMode = Literal["methods", "api_key"]

_STYLE = (
    STYLE
    + """<style>
.sf-connections{border:0;border-radius:0}
.sf-connections__accent{height:3px;background:var(--sf-gain)}
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
.sf-connections__status.needs_reauth,.sf-connections__status.error{color:var(--sf-blind)}
.sf-connections__account{color:var(--sf-ink-2);font-size:12px;font-weight:400}
.sf-connections__controls{flex:0 0 auto;margin-left:auto;display:flex;align-items:center;
  justify-content:flex-end;gap:4px;height:32px}
.sf-connections__notice{padding:8px 12px;border-bottom:1px solid var(--sf-line);
  border-left:2px solid var(--sf-blind);
  color:var(--sf-blind);font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
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
@media (max-width:680px){
  .sf-connections__engine{display:none}.sf-connections__meta{grid-template-columns:1fr 108px}
  .sf-connections__row{padding:0 8px!important;gap:8px!important}
  .sf-connection-widget .widget-text{width:140px!important}}
</style>"""
)


class ConnectionPanel:
    """A fresh engine-scoped connection view with optional notebook controls."""

    def __init__(self, registry: Registry, *, engine: str) -> None:
        self.engine = engine
        self._registry = registry
        self._connections = connection_api._list_for_registry(registry, engine_url=engine)
        self._flows: dict[str, OAuthFlow] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._modes: dict[str, PanelMode] = {}
        self._rows: Any = None
        self._notice: Any = None

    @classmethod
    def create(cls) -> ConnectionPanel:
        return cls(load_registry(), engine=current_engine_url())

    @property
    def connections(self) -> tuple[Connection, ...]:
        return self._connections

    def refresh(self) -> tuple[Connection, ...]:
        """Fetch fresh state from this panel's originating engine."""

        self._connections = connection_api._list_for_registry(
            self._registry,
            engine_url=self.engine,
        )
        self._render_rows()
        return self._connections

    def widget(self):
        """Build the interactive notebook view when the notebook extra is installed."""

        try:
            import ipywidgets as widgets
        except ImportError as exc:  # pragma: no cover - exercised in a dependency-isolated install
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
                f"{_STYLE}<div class='sf-connections__accent'></div>"
                "<div class='sf-connections__head'>"
                "<div class='sf-connections__title'>Provider connections</div>"
                f"<div class='sf-connections__engine'>Engine · {escape(self.engine)}</div></div>"
            )
        )
        self._notice = widgets.HTML()
        self._rows = widgets.VBox()
        root = PanelWidget(children=(header, self._notice, self._rows))
        root.add_class("sf-ui")
        root.add_class("sf-connection-widget")
        root.add_class("sf-connections")
        self._render_rows()
        return root

    def _repr_html_(self) -> str:
        rows = "".join(self._static_row(item) for item in self._connections)
        return (
            f"{_STYLE}<div class='sf-ui sf-connections' "
            "aria-label='ScreamingFace provider connections'>"
            "<div class='sf-connections__accent'></div>"
            "<div class='sf-connections__head'>"
            "<div class='sf-connections__title'>Provider connections</div>"
            f"<div class='sf-connections__engine'>Engine · {escape(self.engine)}</div></div>"
            f"{rows}</div>"
        )

    def _ipython_display_(self) -> None:
        from IPython.display import display

        display(self.widget())

    def __repr__(self) -> str:
        statuses = ", ".join(f"{item.provider}={item.status}" for item in self._connections)
        return f"ConnectionPanel(engine={self.engine!r}, {statuses})"

    def close(self) -> None:
        """Cancel bounded background polling when the panel is disposed."""

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

    def _render_rows(self) -> None:
        if self._rows is None:
            return
        self._rows.children = tuple(self._interactive_row(item) for item in self._connections)

    def _interactive_row(self, connection: Connection):
        import ipywidgets as widgets

        provider = self._provider(connection.provider)
        meta = widgets.HTML(value=self._meta_html(connection))
        meta.layout.flex = "1 1 auto"
        meta.layout.min_width = "0"
        actions = self._controls_for(connection, provider)
        controls = widgets.HBox(children=tuple(actions))
        controls.add_class("sf-connections__controls")
        controls.layout.flex = "0 0 auto"
        row = widgets.HBox(children=(meta, controls))
        row.add_class("sf-connections__row")
        row.layout.align_items = "center"
        row.layout.flex_flow = "row nowrap"
        row.layout.height = "48px"
        return row

    def _controls_for(self, connection: Connection, provider: ProviderRecord) -> list[Any]:
        flow = self._flows.get(provider.id)
        if flow is not None:
            controls = self._oauth_controls(provider, flow)
        elif connection.status == "pending":
            controls = self._pending_controls(provider)
        elif connection.status == "connected":
            controls = self._connected_controls(provider)
        elif self._modes.get(provider.id) == "methods":
            controls = self._method_controls(provider)
        elif self._modes.get(provider.id) == "api_key":
            controls = self._api_key_controls(provider)
        else:
            controls = self._collapsed_controls(provider)
        return controls

    def _collapsed_controls(self, provider: ProviderRecord) -> list[Any]:
        connect = self._button("Connect", "Choose how to connect this provider", primary=True)
        connect.on_click(lambda _button: self._show_methods(provider))
        return [connect]

    def _method_controls(self, provider: ProviderRecord) -> list[Any]:
        controls: list[Any] = []
        if "oauth" in provider.auth_methods:
            button = self._button("OAuth", "Start provider OAuth authorization")
            button.on_click(lambda _button: self._attempt(lambda: self._start_oauth(provider)))
            controls.append(button)
        if "api_key" in provider.auth_methods:
            button = self._button("API key", "Enter an API key for this provider")
            button.on_click(lambda _button: self._show_api_key(provider))
            controls.append(button)
        cancel = self._button("Cancel", "Close connection options")
        cancel.on_click(lambda _button: self._cancel_mode(provider.id))
        controls.append(cancel)
        return controls

    def _api_key_controls(self, provider: ProviderRecord) -> list[Any]:
        import ipywidgets as widgets

        password = widgets.Password(placeholder="API key")
        password.layout.width = "180px"
        save = self._button("Save", "Store this API key in the configured engine", primary=True)

        def submit(_button: Any) -> None:
            key = password.value
            try:
                self._attempt(lambda: self._submit_api_key(provider, key))
            finally:
                # INVARIANT: Widget state never retains a submitted API key after an attempt.
                password.value = ""

        save.on_click(submit)
        cancel = self._button("Cancel", "Close the API key editor")
        cancel.on_click(lambda _button: self._cancel_mode(provider.id))
        return [password, save, cancel]

    def _connected_controls(self, provider: ProviderRecord) -> list[Any]:
        disconnect = self._button("Disconnect", "Remove this provider connection")
        disconnect.on_click(lambda _button: self._attempt(lambda: self._disconnect(provider)))
        return [disconnect]

    def _pending_controls(self, provider: ProviderRecord) -> list[Any]:
        # WHY: A fresh notebook can recover engine-persisted pending state but not the one-time
        # authorize URL. It must offer an honest escape instead of pretending this is disconnected.
        cancel = self._button("Cancel", "Cancel the pending OAuth authorization")
        cancel.on_click(lambda _button: self._attempt(lambda: self._disconnect(provider)))
        return [cancel]

    def _oauth_controls(self, provider: ProviderRecord, flow: OAuthFlow) -> list[Any]:
        import ipywidgets as widgets

        link = widgets.HTML(
            value=(
                "<a class='sf-connections__authorize' "
                f"href='{escape(flow.authorize_url, quote=True)}' "
                "target='_blank' rel='noopener noreferrer'>Authorize</a>"
            )
        )
        cancel = self._button("Cancel", "Cancel this OAuth authorization attempt")
        cancel.on_click(lambda _button: self._attempt(lambda: self._cancel_flow(provider)))
        return [link, cancel]

    def _button(self, description: str, tooltip: str, *, primary: bool = False):
        import ipywidgets as widgets

        button = widgets.Button(description=description, tooltip=tooltip)
        button.add_class("sf-button")
        if primary:
            button.add_class("sf-button--primary")
        return button

    def _show_methods(self, provider: ProviderRecord) -> None:
        self._modes[provider.id] = "methods"
        self._render_rows()

    def _show_api_key(self, provider: ProviderRecord) -> None:
        self._modes[provider.id] = "api_key"
        self._render_rows()

    def _cancel_mode(self, provider_id: str) -> None:
        self._modes.pop(provider_id, None)
        self._render_rows()

    def _attempt(self, action: Any) -> None:
        self._set_notice(None)
        try:
            action()
        except (ScreamingFaceError, ValueError) as exc:
            # WHY: Widget callbacks should show the SDK's sanitized actionable error inline
            # instead of leaving a traceback as the only feedback.
            self._set_notice(str(exc))

    def _set_notice(self, message: str | None) -> None:
        if self._notice is None:
            return
        self._notice.value = (
            ""
            if message is None
            else (f"<div class='sf-connections__notice' role='alert'>{escape(message)}</div>")
        )

    def _provider(self, provider_id: str) -> ProviderRecord:
        return next(item for item in self._registry.providers if item.id == provider_id)

    def _submit_api_key(self, provider: ProviderRecord, api_key: str) -> None:
        connection_api._connect_api_key(
            provider,
            method=None,
            api_key=api_key,
            engine_url=self.engine,
        )
        self._modes.pop(provider.id, None)
        self.refresh()

    def _start_oauth(self, provider: ProviderRecord) -> None:
        flow = connection_api._start_oauth(provider, "oauth", engine_url=self.engine)
        self._modes.pop(provider.id, None)
        self._flows[provider.id] = flow
        self._render_rows()
        self._schedule_poll(provider, flow)

    def _cancel_flow(self, provider: ProviderRecord) -> None:
        flow = self._flows.pop(provider.id, None)
        if flow is not None:
            flow.cancel()
        self._cancel_task(provider.id)
        self.refresh()

    def _disconnect(self, provider: ProviderRecord) -> None:
        connection_api._disconnect_provider(provider, engine_url=self.engine)
        self._modes.pop(provider.id, None)
        self._finish_flow(provider.id)
        self.refresh()

    def _schedule_poll(self, provider: ProviderRecord, flow: OAuthFlow) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._cancel_task(provider.id)
        self._tasks[provider.id] = loop.create_task(self._poll(provider, flow))

    async def _poll(self, provider: ProviderRecord, flow: OAuthFlow) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                if flow.expired:
                    self._finish_flow(provider.id)
                    self.refresh()
                    return
                connection = await asyncio.to_thread(
                    connection_api._get_connection,
                    provider,
                    engine_url=self.engine,
                )
                if connection.status != "pending":
                    self._finish_flow(provider.id)
                    self.refresh()
                    return
        except asyncio.CancelledError:
            return

    def _finish_flow(self, provider_id: str) -> None:
        self._flows.pop(provider_id, None)
        self._modes.pop(provider_id, None)
        self._cancel_task(provider_id)

    def _cancel_task(self, provider_id: str) -> None:
        task = self._tasks.pop(provider_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()


__all__ = ["ConnectionPanel"]
