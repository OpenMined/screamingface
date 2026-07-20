"""Dependency-light provider panel with optional ipywidgets interaction."""

from __future__ import annotations

import asyncio
from html import escape
from typing import TYPE_CHECKING, Any

from screamingface import connections as connection_api
from screamingface._config import current_engine_url
from screamingface._profile import ProviderRecord, Registry, load_registry
from screamingface.errors import ScreamingFaceError

if TYPE_CHECKING:
    from screamingface.connections import Connection, OAuthFlow

_STYLE = """<style>
.sf-connections {
  --sf-bg:#ffffff;--sf-surface:#f6f6f7;--sf-ink:#16181d;--sf-ink-2:#585d67;
  --sf-ink-3:#8b909a;--sf-line:#e6e7ea;--sf-line-2:#d4d6db;--sf-gain:#0f7a3d;
  --sf-blind:#b23b3b;max-width:760px;border:1px solid var(--sf-line-2);border-radius:0;
  background:var(--sf-bg);color:var(--sf-ink);font:13px/1.45 "IBM Plex Sans",system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){.sf-connections{--sf-bg:#0a0b0d;--sf-surface:#131519;
  --sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;--sf-line:#20232a;
  --sf-line-2:#2c303a;--sf-gain:#35d07f;--sf-blind:#f0726f}}
.jp-mod-theme-dark .sf-connections,.vscode-dark .sf-connections{--sf-bg:#0a0b0d;
  --sf-surface:#131519;--sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;
  --sf-line:#20232a;--sf-line-2:#2c303a;--sf-gain:#35d07f;--sf-blind:#f0726f}
.sf-connections,.sf-connections *{box-sizing:border-box}
.sf-connections__head{padding:16px;border-bottom:1px solid var(--sf-line)}
.sf-connections__title{font-size:16px;font-weight:600}
.sf-connections__engine,.sf-connections__status,.sf-connections__methods{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;color:var(--sf-ink-3)}
.sf-connections__engine{margin-top:4px}.sf-connections__row{display:grid;
  grid-template-columns:minmax(150px,1fr) minmax(120px,1fr);gap:12px;padding:12px 16px;
  border-bottom:1px solid var(--sf-line)}
.sf-connections__row:last-child{border-bottom:0}.sf-connections__provider{font-weight:600}
.sf-connections__status{text-align:right}.sf-connections__status.connected{color:var(--sf-gain)}
.sf-connections__status.needs_reauth,.sf-connections__status.error{color:var(--sf-blind)}
.sf-connections__account{grid-column:1/-1;color:var(--sf-ink-2)}
.sf-connections__actions{grid-column:1/-1;color:var(--sf-ink-3);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;letter-spacing:.1em;
  text-transform:uppercase}
.sf-connections__notice{padding:10px 16px;border-bottom:1px solid var(--sf-line);
  color:var(--sf-blind);font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.sf-connection-widget .widget-button,.sf-connection-widget .widget-text input{
  border-radius:0!important;box-shadow:none!important;background-image:none!important}
.sf-connection-widget .widget-button{font-family:"IBM Plex Mono",ui-monospace,monospace}
</style>"""


class ConnectionPanel:
    """A fresh engine-scoped connection view with optional notebook controls."""

    def __init__(self, registry: Registry, *, engine: str) -> None:
        self.engine = engine
        self._registry = registry
        self._connections = connection_api._list_for_registry(registry, engine_url=engine)
        self._flows: dict[str, OAuthFlow] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
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
                f"{_STYLE}<div class='sf-connections sf-connections__head'>"
                "<div class='sf-connections__title'>Provider connections</div>"
                "<div class='sf-connections__engine'>Connection credentials are stored by "
                f"{escape(self.engine)}</div></div>"
            )
        )
        self._notice = widgets.HTML()
        self._rows = widgets.VBox()
        root = PanelWidget(children=(header, self._notice, self._rows))
        root.add_class("sf-connection-widget")
        self._render_rows()
        return root

    def _repr_html_(self) -> str:
        rows = "".join(self._static_row(item) for item in self._connections)
        return (
            f"{_STYLE}<div class='sf-connections' aria-label='ScreamingFace provider connections'>"
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

    def _static_row(self, connection: Connection) -> str:
        account = (
            f"<div class='sf-connections__account'>{escape(connection.account_label)}</div>"
            if connection.account_label
            else ""
        )
        actions = " · ".join(connection.auth_methods)
        return (
            "<div class='sf-connections__row'>"
            f"<div><div class='sf-connections__provider'>{escape(connection.display_name)}</div>"
            f"<div class='sf-connections__methods'>{escape(connection.provider)}</div></div>"
            f"<div class='sf-connections__status {connection.status}'>"
            f"{escape(connection.status.replace('_', ' '))}</div>{account}"
            f"<div class='sf-connections__actions'>{escape(actions)}</div></div>"
        )

    def _render_rows(self) -> None:
        if self._rows is None:
            return
        self._rows.children = tuple(self._interactive_row(item) for item in self._connections)

    def _interactive_row(self, connection: Connection):
        import ipywidgets as widgets

        provider = self._provider(connection.provider)
        label = widgets.HTML(value=self._static_row(connection))
        actions: list[widgets.Widget] = []
        flow = self._flows.get(provider.id)
        if flow is not None:
            actions.extend(self._oauth_controls(provider, flow))
        elif connection.status == "connected":
            actions.extend(self._connected_controls(provider))
        else:
            actions.extend(self._connect_controls(provider))
        box = widgets.VBox(children=(label, widgets.HBox(children=tuple(actions))))
        box.layout.border = "0"
        return box

    def _connect_controls(self, provider: ProviderRecord) -> list[Any]:
        import ipywidgets as widgets

        controls: list[Any] = []
        if "oauth" in provider.auth_methods:
            button = self._button("Connect with OAuth", "Start provider OAuth authorization")
            button.on_click(lambda _button: self._attempt(lambda: self._start_oauth(provider)))
            controls.append(button)
        if "api_key" in provider.auth_methods:
            password = widgets.Password(description="API key", placeholder="Paste API key")
            save = self._button("Save API key", "Store this API key in the configured engine")

            def submit(_button: Any) -> None:
                key = password.value
                try:
                    self._attempt(lambda: self._submit_api_key(provider, key))
                finally:
                    # INVARIANT: Widget state never retains a submitted API key after an attempt.
                    password.value = ""

            save.on_click(submit)
            controls.extend((password, save))
        return controls

    def _connected_controls(self, provider: ProviderRecord) -> list[Any]:
        controls = self._connect_controls(provider)
        disconnect = self._button("Disconnect", "Remove this provider connection")
        disconnect.on_click(lambda _button: self._attempt(lambda: self._disconnect(provider)))
        controls.append(disconnect)
        return controls

    def _oauth_controls(self, provider: ProviderRecord, flow: OAuthFlow) -> list[Any]:
        import ipywidgets as widgets

        link = widgets.HTML(
            value=(
                f"<a href='{escape(flow.authorize_url, quote=True)}' target='_blank' "
                "rel='noopener noreferrer'>Authorize provider</a>"
            )
        )
        refresh = self._button("Refresh", "Refresh provider connection status")
        refresh.on_click(lambda _button: self._attempt(lambda: self._refresh_flow(provider)))
        cancel = self._button("Cancel", "Cancel this OAuth authorization attempt")
        cancel.on_click(lambda _button: self._attempt(lambda: self._cancel_flow(provider)))
        return [link, refresh, cancel]

    def _button(self, description: str, tooltip: str):
        import ipywidgets as widgets

        button = widgets.Button(description=description, tooltip=tooltip)
        button.layout.border = "1px solid var(--sf-line-2)"
        button.layout.border_radius = "0"
        return button

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
            else (
                "<div class='sf-connections sf-connections__notice' role='alert'>"
                f"{escape(message)}</div>"
            )
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
        self.refresh()

    def _start_oauth(self, provider: ProviderRecord) -> None:
        flow = connection_api._start_oauth(provider, "oauth", engine_url=self.engine)
        self._flows[provider.id] = flow
        self._render_rows()
        self._schedule_poll(provider, flow)

    def _refresh_flow(self, provider: ProviderRecord) -> None:
        connection = connection_api._get_connection(provider, engine_url=self.engine)
        if connection.status != "pending":
            self._finish_flow(provider.id)
        self.refresh()

    def _cancel_flow(self, provider: ProviderRecord) -> None:
        flow = self._flows.pop(provider.id, None)
        if flow is not None:
            flow.cancel()
        self._cancel_task(provider.id)
        self.refresh()

    def _disconnect(self, provider: ProviderRecord) -> None:
        connection_api._disconnect_provider(provider, engine_url=self.engine)
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
        self._cancel_task(provider_id)

    def _cancel_task(self, provider_id: str) -> None:
        task = self._tasks.pop(provider_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()


__all__ = ["ConnectionPanel"]
