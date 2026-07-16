"""Session setup and process-local active-session state."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from screamingface.widgets import SetupPanel

from screamingface.errors import AmbiguousProfile, GatewayError, GatewayUnavailable, LoginRequired
from screamingface.gateway import (
    AIGatewayClient,
    Connection,
    GatewayPort,
    OAuthGatewayPort,
    OAuthStart,
    ProviderCapability,
)

Mode = Literal["live", "mock"]
_LOCAL_GATEWAY = "http://127.0.0.1:9105"


@dataclass
class Session:
    mode: Mode
    static_widgets: bool = False
    gateway_url: str | None = None
    dataset_source: str = "gated:Idavidrein/gpqa:gpqa_diamond"
    profiles: dict[str, str] = field(default_factory=dict)
    connected_providers: frozenset[str] | None = None
    gateway: GatewayPort | None = field(default=None, repr=False, compare=False)
    closed: bool = field(default=False, init=False)

    def _repr_html_(self) -> str:
        label = "SIMULATION" if self.mode == "mock" else "LIVE"
        gateway = self.gateway_url or "deterministic local adapter"
        return (
            "<div><strong>ScreamingFace setup</strong> "
            f"<code>{label}</code><br>Gateway: {gateway}</div>"
        )

    def connections(self) -> tuple[Connection, ...]:
        return tuple(_run(self._live_gateway().list_connections()))

    def refresh_connections(self) -> tuple[Connection, ...]:
        return self._refresh_profiles()

    def providers(self) -> tuple[ProviderCapability, ...]:
        if self.mode == "mock":
            return ()
        return tuple(_run(self._live_gateway().list_providers()))

    def connect(
        self,
        provider: str,
        *,
        label: str | None = None,
        api_key: str,
    ) -> Connection:
        if not api_key:
            raise ValueError("API key is required")
        gateway = self._live_gateway()
        effective_label = label or "default"
        existing = next(
            (
                row
                for row in _run(gateway.list_connections())
                if row.provider == provider
                and row.label == effective_label
                and row.auth_type == "api_key"
            ),
            None,
        )
        if existing is None:
            result = _run(gateway.create_api_key_connection(provider, effective_label, api_key))
        else:
            result = _run(gateway.replace_api_key_connection(existing.id, api_key))
        self._refresh_profiles()
        return result

    def connect_oauth(
        self,
        provider: str,
        *,
        label: str | None = None,
        redirect_uri: str | None = None,
    ) -> OAuthStart:
        gateway = cast(OAuthGatewayPort, self._live_gateway())
        return _run(gateway.start_oauth_connection(provider, label, redirect_uri))

    def wait_for_connection(self, connection_id: str, *, timeout_s: float = 600) -> Connection:
        return _run(_wait_for_connection(self._live_gateway(), connection_id, timeout_s))

    def disconnect(self, connection_id: str) -> None:
        _run(self._live_gateway().delete_connection(connection_id))
        self._refresh_profiles()

    def close(self) -> None:
        gateway = self.gateway
        if self.closed:
            return
        self.closed = True
        if gateway is not None:
            _run(gateway.aclose())

    def _live_gateway(self) -> GatewayPort:
        if self.mode != "live" or self.gateway is None or self.closed:
            raise GatewayError("A live, open AI Gateway session is required")
        return self.gateway

    def _refresh_profiles(self) -> tuple[Connection, ...]:
        connections = _run(self._live_gateway().list_connections())
        return self._apply_connections(connections)

    async def _refresh_profiles_async(self) -> tuple[Connection, ...]:
        connections = await self._live_gateway().list_connections()
        return self._apply_connections(connections)

    def _apply_connections(self, connections: list[Connection]) -> tuple[Connection, ...]:
        active = _active_profile_labels(connections)
        requested = {
            provider: label for provider, label in self.profiles.items() if provider in active
        }
        self.profiles = _resolve_profiles(connections, requested)
        self.connected_providers = frozenset(self.profiles)
        return tuple(connections)


_active: Session | None = None
_sync_executor: ThreadPoolExecutor | None = None
_worker_loop: asyncio.AbstractEventLoop | None = None


def current_session() -> Session | None:
    return _active


def reset_session() -> None:
    global _active
    if _active is not None:
        _active.close()
    _active = None


def shutdown() -> None:
    """Close the active session and the process-local async worker."""
    global _sync_executor, _worker_loop
    reset_session()
    if _sync_executor is not None:
        _sync_executor.submit(_close_worker_loop).result()
        _sync_executor.shutdown(wait=True)
    _sync_executor = None
    _worker_loop = None


def setup(
    *,
    mode: Mode = "live",
    gateway: str | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    profiles: dict[str, str] | None = None,
    static_widgets: bool = False,
    interactive: bool | None = None,
) -> Session | SetupPanel:
    """Create the active SDK session; live mode never silently becomes mock."""
    global _active
    if mode not in ("live", "mock"):
        raise ValueError("mode must be 'live' or 'mock'")
    show_panel = _in_notebook() if interactive is None else interactive
    if mode == "mock":
        session = Session(
            mode="mock",
            static_widgets=static_widgets,
            dataset_source="synthetic-gpqa-shaped",
        )
        session = _set_active(session)
        return _panel_for(session, static_widgets) if show_panel else session

    base_url = gateway or os.getenv("SCREAMINGFACE_GATEWAY_URL") or _LOCAL_GATEWAY
    auth_token = token or os.getenv("SCREAMINGFACE_GATEWAY_TOKEN")
    session = _reusable_live_session(base_url, auth_token, username, password, profiles)
    if session is None and show_panel and not auth_token and username is None and password is None:
        client = AIGatewayClient(base_url, timeout=30.0)
        if not _run(client.health()):
            _run(client.aclose())
            raise GatewayUnavailable(
                f"No AI Gateway found at {base_url}. Start apps/aigateway on port 9105 "
                "or set SCREAMINGFACE_GATEWAY_URL."
            )

        def finish_login(login_username: str, login_password: str) -> Session:
            _run(client.login(login_username, login_password))
            session = _session_from_client(client, base_url, profiles or {}, static_widgets)
            return _set_active(session)

        from screamingface.widgets import login_panel

        return login_panel(finish_login, static=static_widgets)

    if session is None:
        session = _setup_live(
            gateway=gateway,
            token=token,
            username=username,
            password=password,
            profiles=profiles,
            static_widgets=static_widgets,
        )
        session = _set_active(session)
    return _panel_for(session, static_widgets) if show_panel else session


def _reusable_live_session(
    base_url: str,
    auth_token: str | None,
    username: str | None,
    password: str | None,
    profiles: dict[str, str] | None,
) -> Session | None:
    # Notebook cell re-execution should reuse the authenticated, process-local JWT.
    # Kernel restart, shutdown(), a different gateway, explicit credentials, or a new
    # profile selection still establishes a new session.
    if (
        auth_token is None
        and username is None
        and password is None
        and profiles is None
        and _active is not None
        and _active.mode == "live"
        and not _active.closed
        and _active.gateway_url == base_url
    ):
        return _active
    return None


def _set_active(session: Session) -> Session:
    global _active
    if _active is not None and _active is not session:
        _active.close()
    _active = session
    return session


def _setup_live(
    *,
    gateway: str | None,
    token: str | None,
    username: str | None,
    password: str | None,
    profiles: dict[str, str] | None,
    static_widgets: bool,
) -> Session:
    base_url = gateway or os.getenv("SCREAMINGFACE_GATEWAY_URL") or _LOCAL_GATEWAY
    auth_token = token or os.getenv("SCREAMINGFACE_GATEWAY_TOKEN")
    client = AIGatewayClient(base_url, token=auth_token, timeout=30.0)
    if not _run(client.health()):
        _run(client.aclose())
        raise GatewayUnavailable(
            f"No AI Gateway found at {base_url}. Start apps/aigateway on port 9105 or "
            "set SCREAMINGFACE_GATEWAY_URL."
        )
    try:
        _authenticate(client, auth_token, username, password)
        return _session_from_client(
            client,
            base_url,
            profiles or {},
            static_widgets,
        )
    except (GatewayError, ValueError):
        _run(client.aclose())
        raise


def _session_from_client(
    client: AIGatewayClient,
    base_url: str,
    profiles: dict[str, str],
    static_widgets: bool,
) -> Session:
    _run(client.me())
    connections = _run(client.list_connections())
    selected_profiles = _resolve_profiles(connections, profiles)
    return Session(
        mode="live",
        static_widgets=static_widgets,
        gateway_url=base_url,
        profiles=selected_profiles,
        connected_providers=frozenset(selected_profiles),
        gateway=client,
    )


def _panel_for(session: Session, static: bool):
    from screamingface.widgets import setup_panel

    return setup_panel(session, static=static)


def _in_notebook() -> bool:
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        return False
    return get_ipython() is not None


def _authenticate(
    client: AIGatewayClient,
    auth_token: str | None,
    username: str | None,
    password: str | None,
) -> str:
    if (username is None) != (password is None):
        raise ValueError("username and password must be supplied together")
    if not auth_token and username is not None and password is not None:
        _run(client.login(username, password))
        return "in-memory gateway session"
    if not auth_token:
        raise LoginRequired(
            "AI Gateway is reachable but login is required. Supply a token or username/password."
        )
    return auth_token


def require_session() -> Session:
    if _active is None:
        raise RuntimeError("Call sf.setup() before using models or fusions")
    return _active


def _resolve_profiles(
    connections: list[Connection] | list[dict[str, Any]], requested: dict[str, str]
) -> dict[str, str]:
    active = _active_profile_labels(connections)
    unknown = requested.keys() - active.keys()
    if unknown:
        provider = sorted(unknown)[0]
        raise GatewayError(f"No active provider connection for {provider!r}")
    selected: dict[str, str] = {}
    for provider, labels in active.items():
        requested_label = requested.get(provider)
        if requested_label is None and len(labels) != 1:
            raise AmbiguousProfile(
                f"Multiple active {provider} profiles exist; select one with profiles={{...}}"
            )
        selected_label = requested_label or labels[0]
        if selected_label not in labels:
            raise GatewayError(f"No active {provider} profile named {selected_label!r}")
        selected[provider] = selected_label
    return selected


def _active_profile_labels(
    connections: list[Connection] | list[dict[str, Any]],
) -> dict[str, list[str]]:
    active: dict[str, list[str]] = {}
    for connection in connections:
        provider = (
            connection.provider
            if isinstance(connection, Connection)
            else connection.get("provider")
        )
        label = connection.label if isinstance(connection, Connection) else connection.get("label")
        status = (
            connection.status if isinstance(connection, Connection) else connection.get("status")
        )
        if status == "active" and isinstance(provider, str) and isinstance(label, str):
            active.setdefault(provider, []).append(label)
    return active


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    # A single worker loop lets synchronous scripts and Jupyter share one AsyncClient
    # safely across setup, model discovery, and evaluation calls.
    global _sync_executor
    if _sync_executor is None:
        _sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screamingface-sync")
    return _sync_executor.submit(_run_on_worker_loop, awaitable).result()


def _run_on_worker_loop[T](awaitable: Coroutine[Any, Any, T]) -> T:
    global _worker_loop
    if _worker_loop is None:
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop.run_until_complete(awaitable)


def _close_worker_loop() -> None:
    global _worker_loop
    if _worker_loop is not None:
        _worker_loop.close()
        _worker_loop = None


async def _wait_for_connection(
    gateway: GatewayPort, connection_id: str, timeout_s: float
) -> Connection:
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    deadline = time.monotonic() + timeout_s
    while True:
        connection = await gateway.get_connection(connection_id)
        if connection.status == "active":
            return connection
        if connection.status in {"error", "expired", "revoked"}:
            raise GatewayError(
                f"Provider connection {connection_id!r} ended with status {connection.status!r}"
            )
        if time.monotonic() >= deadline:
            raise GatewayError(f"Timed out waiting for provider connection {connection_id!r}")
        await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


def connections() -> tuple[Connection, ...]:
    return require_session().connections()


def providers() -> tuple[ProviderCapability, ...]:
    return require_session().providers()


def connect(
    provider: str,
    *,
    label: str | None = None,
    api_key: str,
) -> Connection:
    return require_session().connect(provider, label=label, api_key=api_key)


def connect_oauth(
    provider: str,
    *,
    label: str | None = None,
    redirect_uri: str | None = None,
) -> OAuthStart:
    return require_session().connect_oauth(provider, label=label, redirect_uri=redirect_uri)


def wait_for_connection(connection_id: str, *, timeout_s: float = 600) -> Connection:
    return require_session().wait_for_connection(connection_id, timeout_s=timeout_s)


def disconnect(connection_id: str) -> None:
    require_session().disconnect(connection_id)
