"""Production notebook controls backed by the public Session connection APIs."""

from __future__ import annotations

from collections.abc import Callable
from html import escape
from time import monotonic
from typing import Any

from screamingface.errors import ScreamingFaceError
from screamingface.gateway import Connection, OAuthStart, ProviderCapability

_PROVIDER_DETAILS = {
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY"),
    "gemini-cli": ("Google Gemini", "GEMINI_API_KEY"),
    "huggingface": ("Hugging Face", "HF_TOKEN"),
    "ollama": ("Ollama", "No key required"),
}


class SetupPanel:
    """Notebook setup UI with a deterministic static representation for GitHub."""

    def __init__(
        self,
        session=None,
        *,
        static: bool = False,
        login: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.value: Any = session
        self._login = login
        self._static = static
        self.login_controls: dict[str, Any] = {}
        self.provider_controls: dict[str, dict[str, Any]] = {}
        self.widget: Any = None if static else self._build_widget()

    def __getattr__(self, name: str) -> Any:
        if self.value is None:
            raise AttributeError(name)
        return getattr(self.value, name)

    def __repr__(self) -> str:
        state = "connected" if self.value is not None else "login-required"
        return f"SetupPanel(state={state!r}, credentials=<never stored>)"

    def _repr_html_(self) -> str:
        mode = (
            "LOGIN REQUIRED"
            if self.value is None
            else ("SIMULATION" if self.value.mode == "mock" else "LIVE")
        )
        return (
            "<div><strong>ScreamingFace setup</strong> "
            f"<code>{mode}</code><br>Connect providers with OAuth or masked API keys. Each key is "
            "submitted to the configured AI Gateway, encrypted at rest there, and removed from "
            "this widget field.</div>"
        )

    def _repr_mimebundle_(self, **kwargs) -> dict[str, Any]:
        if self.widget is not None:
            return self.widget._repr_mimebundle_(**kwargs)
        return {"text/plain": repr(self), "text/html": self._repr_html_()}

    def login(self, username: str, password: str):
        if self._login is None:
            raise RuntimeError("This setup panel is already authenticated")
        # INVARIANT: the password crosses this call once and is never retained on the panel.
        self.value = self._login(username, password)
        if self.widget is not None:
            self.widget.children = tuple(self._session_controls())
        return self.value

    def _build_widget(self):
        widgets = _widgets()
        children = self._login_controls() if self.value is None else self._session_controls()
        return widgets.VBox(tuple(children))

    def _login_controls(self) -> list[Any]:
        widgets = _widgets()
        field_layout = widgets.Layout(width="100%")
        field_style = {"description_width": "72px"}
        username = widgets.Text(
            description="Username",
            placeholder="Your AI Gateway username",
            layout=field_layout,
            style=field_style,
        )
        password = widgets.Password(
            description="Password",
            placeholder="Your password",
            layout=field_layout,
            style=field_style,
        )
        submit = widgets.Button(
            description="Sign in",
            icon="sign-in-alt",
            button_style="primary",
            layout=widgets.Layout(width="100%"),
        )
        status = widgets.HTML()

        def on_login(_button) -> None:
            try:
                self.login(username.value, password.value)
            except (ScreamingFaceError, RuntimeError, ValueError) as exc:
                status.value = f"<span style='color:#b91c1c'>{escape(str(exc))}</span>"
            finally:
                password.value = ""

        submit.on_click(on_login)
        card = widgets.VBox(
            (
                widgets.HTML(
                    "<style>.sf-login-card{border-radius:10px;box-shadow:0 2px 10px "
                    "rgba(60,64,67,.10)}</style>"
                    "<h3 style='margin:0 0 .25rem'>Sign in to ScreamingFace</h3>"
                    "<p style='margin:0 0 .8rem;color:#5f6368'>Use your AI Gateway account to "
                    "access encrypted provider connections.</p>"
                ),
                username,
                password,
                submit,
                status,
                widgets.HTML(
                    "<small style='color:#80868b'>Provider keys are added after sign-in and "
                    "authorize upstream model billing.</small>"
                ),
            ),
            layout=widgets.Layout(
                align_items="stretch",
                border="1px solid #e0e3e7",
                padding="18px",
                width="420px",
                max_width="100%",
            ),
        )
        card.add_class("sf-login-card")
        self.login_controls = {
            "card": card,
            "username": username,
            "password": password,
            "submit": submit,
            "status": status,
        }
        return [card]

    def _session_controls(self) -> list[Any]:
        widgets = _widgets()
        if self.value.mode == "mock":
            return [widgets.HTML(self._repr_html_())]
        capabilities = self.value.providers()
        connectable = sorted(
            (
                row
                for row in capabilities
                if "api_key" in row.auth_methods or "oauth" in row.auth_methods
            ),
            key=lambda row: _provider_details(row.id)[0].casefold(),
        )
        keyless = [row for row in capabilities if "none" in row.auth_methods]
        self.provider_controls = {
            capability.id: self._provider_card(widgets, capability) for capability in connectable
        }
        cards = [controls["card"] for controls in self.provider_controls.values()]
        provider_list = widgets.VBox(tuple(cards), layout=widgets.Layout(width="100%"))
        refresh = widgets.Button(
            description="Check connection status",
            icon="refresh",
            tooltip="Ask AI Gateway for the latest OAuth and API-key connection states",
            layout=widgets.Layout(width="auto"),
        )
        refresh.on_click(lambda _button: self._refresh_provider_cards())
        self._summary_widget = widgets.HTML()
        self._refresh_provider_cards()
        return [
            widgets.HTML(
                "<h3 style='margin:0'>Connect model providers</h3>"
                "<p style='margin:.35rem 0;color:#5f6368'>Choose OAuth or bring your own API key "
                "when offered. Each key is submitted to the configured AI Gateway, encrypted at "
                "rest there, and removed from this widget field.</p>"
            ),
            self._summary_widget,
            widgets.HTML(self._keyless_html(keyless)),
            provider_list,
            refresh,
        ]

    def _provider_card(self, widgets, capability: ProviderCapability) -> dict[str, Any]:
        display_name, env_name = _provider_details(capability.id)
        status = widgets.HTML(layout=widgets.Layout(flex="1 1 auto"))
        remove = widgets.Button(
            description="Disconnect",
            icon="unlink",
            button_style="danger",
            disabled=True,
            tooltip=f"Disconnect {display_name}",
            layout=widgets.Layout(display="none", width="auto"),
        )
        controls: dict[str, Any] = {
            "provider": capability.id,
            "display_name": display_name,
            "status": status,
            "remove": remove,
            "connection": None,
            "oauth_start": None,
        }
        detail_children, actions = self._provider_connection_actions(
            widgets, capability, controls, env_name
        )
        actions.append(remove)
        remove.on_click(lambda _button: self._remove_connection(controls))
        details = _provider_details_row(widgets, detail_children)
        controls["details"] = details
        header = _provider_header_row(
            widgets, display_name, capability.model_count, status, details, actions
        )
        controls["header"] = header
        card = widgets.VBox(
            (header,),
            layout=widgets.Layout(
                border_bottom="1px solid #e3e6e8",
                padding="8px 2px",
                width="100%",
            ),
        )
        controls["card"] = card
        return controls

    def _provider_connection_actions(
        self,
        widgets,
        capability: ProviderCapability,
        controls: dict[str, Any],
        env_name: str,
    ) -> tuple[list[Any], list[Any]]:
        detail_children: list[Any] = []
        actions: list[Any] = []
        if "api_key" in capability.auth_methods:
            api_key = widgets.Password(
                placeholder=f"Paste {env_name}",
                layout=widgets.Layout(flex="1 1 260px", min_width="220px"),
            )
            connect = widgets.Button(
                description="Save API key",
                button_style="primary",
                layout=widgets.Layout(width="auto"),
            )
            connect.on_click(lambda _button: self._connect_api_key(controls))
            cancel_api = widgets.Button(
                description="Cancel",
                layout=widgets.Layout(width="auto"),
            )
            cancel_api.on_click(lambda _button: self._cancel_api_key(controls))
            controls.update(api_key=api_key, connect=connect, cancel_api=cancel_api)
            detail_children.extend([api_key, connect, cancel_api])
        if "oauth" in capability.auth_methods:
            oauth = widgets.Button(
                description="Connect with OAuth",
                icon="external-link",
                layout=widgets.Layout(width="auto"),
            )
            oauth.on_click(lambda _button: self._connect_oauth(controls))
            controls["oauth"] = oauth
            actions.append(oauth)

        methods = set(capability.auth_methods)
        open_details = None
        if "api_key" in methods:
            open_details = widgets.Button(
                description="Use API key",
                layout=widgets.Layout(width="auto"),
            )
            open_details.on_click(lambda _button: self._toggle_provider_details(controls))
            controls["open"] = open_details
            actions.append(open_details)
        return detail_children, actions

    def _toggle_provider_details(self, controls: dict[str, Any]) -> None:
        controls["details"].layout.display = "flex"
        controls["open"].layout.display = "none"
        oauth = controls.get("oauth")
        if oauth is not None:
            oauth.layout.display = "none"

    def _cancel_api_key(self, controls: dict[str, Any]) -> None:
        controls["api_key"].value = ""
        controls["status"].value = ""
        controls["details"].layout.display = "none"
        _update_provider_buttons(controls, controls.get("connection"))

    def _connect_api_key(self, controls: dict[str, Any]) -> None:
        try:
            self.value.connect(
                controls["provider"],
                label="default",
                api_key=controls["api_key"].value,
            )
            self._refresh_provider_cards()
        except (ScreamingFaceError, ValueError) as exc:
            controls["status"].value = _error_html(exc)
        finally:
            controls["api_key"].value = ""

    def _connect_oauth(self, controls: dict[str, Any]) -> None:
        try:
            controls["oauth_start"] = self.value.connect_oauth(
                controls["provider"], label="default"
            )
            self._refresh_provider_cards()
            self._start_oauth_poll(controls)
        except (ScreamingFaceError, ValueError) as exc:
            controls["status"].value = _error_html(exc)

    def _start_oauth_poll(self, controls: dict[str, Any]) -> None:
        io_loop = _notebook_io_loop()
        oauth_start = controls.get("oauth_start")
        if io_loop is None or not isinstance(oauth_start, OAuthStart):
            return
        token = object()
        controls["poll_token"] = token
        deadline = monotonic() + min(max(oauth_start.expires_in, 1), 600)

        def poll() -> None:
            if controls.get("poll_token") is not token:
                return
            try:
                self._refresh_provider_cards()
            except (ScreamingFaceError, RuntimeError, ValueError):
                if monotonic() < deadline:
                    io_loop.call_later(1.5, poll)
                return
            connection = controls.get("connection")
            if (
                isinstance(connection, Connection)
                and connection.status == "pending"
                and monotonic() < deadline
            ):
                io_loop.call_later(1.5, poll)

        io_loop.call_later(1.0, poll)

    def _remove_connection(self, controls: dict[str, Any]) -> None:
        connection = controls["connection"]
        if isinstance(connection, Connection):
            controls["poll_token"] = None
            self.value.disconnect(connection.id)
            self._refresh_provider_cards()

    def _refresh_provider_cards(self) -> None:
        rows = tuple(self.value.refresh_connections())
        for provider, controls in self.provider_controls.items():
            connection = _preferred_connection(provider, rows)
            controls["connection"] = connection
            controls["status"].value = _connection_status_html(connection, controls)
            _update_provider_buttons(controls, connection)
        if hasattr(self, "_summary_widget"):
            self._summary_widget.value = self._connection_summary(rows)

    def _connection_summary(self, connections: tuple[Connection, ...] | None = None) -> str:
        rows = self.value.connections() if connections is None else connections
        connected = len({row.provider for row in rows if row.status == "active"})
        return f"<strong>{connected}</strong> providers connected"

    def _keyless_html(self, capabilities: list[ProviderCapability]) -> str:
        if not capabilities:
            return ""
        names = ", ".join(_provider_details(row.id)[0] for row in capabilities)
        return (
            "<div style='padding:.5rem .75rem;background:#eef6ff;border-radius:6px'>"
            f"<strong>{escape(names)}</strong> available locally — no API key required.</div>"
        )


def setup_panel(session, *, static: bool = False) -> SetupPanel:
    return SetupPanel(session, static=static)


def login_panel(login: Callable[[str, str], Any], *, static: bool = False) -> SetupPanel:
    return SetupPanel(static=static, login=login)


def _widgets():
    try:
        import ipywidgets
    except ImportError as exc:
        raise RuntimeError(
            "Interactive setup requires the notebook extra: uv sync --extra notebook"
        ) from exc
    return ipywidgets


def _error_html(exc: Exception) -> str:
    return f"<span style='color:#b91c1c'>{escape(str(exc))}</span>"


def _provider_details_row(widgets, children: list[Any]):
    return widgets.HBox(
        tuple(children),
        layout=widgets.Layout(
            align_items="center",
            display="none",
            flex_flow="row wrap",
            margin="0",
            flex="1 1 360px",
        ),
    )


def _provider_header_row(widgets, name: str, model_count: int, status, details, actions: list[Any]):
    label = widgets.HTML(
        f"<strong>{escape(name)}</strong>"
        f" <span style='font-size:.78rem;color:#80868b'>{model_count} models</span>",
        layout=widgets.Layout(flex="0 0 190px", min_width="150px"),
    )
    return widgets.HBox(
        tuple([label, status, details, *actions]),
        layout=widgets.Layout(align_items="center", flex_flow="row wrap", width="100%"),
    )


def _provider_details(provider: str) -> tuple[str, str]:
    if provider in _PROVIDER_DETAILS:
        return _PROVIDER_DETAILS[provider]
    return provider.replace("-", " ").title(), f"{provider.upper().replace('-', '_')}_API_KEY"


def _preferred_connection(provider: str, connections: tuple[Connection, ...]) -> Connection | None:
    matching = [row for row in connections if row.provider == provider and row.label == "default"]
    return next(
        (row for row in matching if row.status == "active"), matching[0] if matching else None
    )


def _connection_status_html(connection: Connection | None, controls: dict[str, Any]) -> str:
    if connection is None:
        result = ""
    elif connection.status == "active":
        method = "OAuth" if connection.auth_type == "oauth" else "API key"
        result = f"<span style='color:#137333'>● Connected via {method}</span>"
    elif connection.auth_type == "oauth" and isinstance(controls.get("oauth_start"), OAuthStart):
        oauth_start = controls["oauth_start"]
        url = escape(oauth_start.authorize_url, quote=True)
        name = escape(str(controls["display_name"]))
        result = (
            "<span style='color:#a15c00'>● OAuth pending</span> "
            f"<a href='{url}' target='_blank' rel='noopener noreferrer' "
            "style='display:inline-block;margin-left:.4rem;padding:.3rem .65rem;"
            "border-radius:4px;background:#1a73e8;color:white;text-decoration:none;"
            f"font-weight:600'>Authorize {name} ↗</a>"
        )
    else:
        result = f"<span style='color:#b06000'>● {escape(connection.status.title())}</span>"
    return result


def _notebook_io_loop():
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        return None
    shell = get_ipython()
    kernel = getattr(shell, "kernel", None)
    return getattr(kernel, "io_loop", None)


def _update_provider_buttons(controls: dict[str, Any], connection: Connection | None) -> None:
    connected_type = connection.auth_type if connection is not None else None
    locked = connection is not None
    api_key = controls.get("api_key")
    connect = controls.get("connect")
    if api_key is not None and connect is not None:
        api_key.disabled = connected_type == "oauth"
        connect.disabled = connected_type == "oauth"
        connect.description = "Save API key"
    oauth = controls.get("oauth")
    if oauth is not None:
        oauth.disabled = locked
        oauth.description = "Connect with OAuth"
        oauth.layout.display = "none" if locked else ""
    remove = controls["remove"]
    remove.description = (
        "Cancel connection"
        if connection is not None and connection.status != "active"
        else "Disconnect"
    )
    remove.disabled = not locked
    remove.layout.display = "" if locked else "none"
    details = controls["details"]
    if connection is not None:
        details.layout.display = "none"
    open_details = controls.get("open")
    if open_details is not None:
        open_details.layout.display = "none" if locked else ""
        open_details.description = "Use API key"
