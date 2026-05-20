"""Shared lifecycle base for aigw_*_backend plugins.

Subclasses mirror direct backend plugin style: declare class-level metadata
(`name`, `backend_call_paths`, `schema_link_base`, `settings_class`,
`create_router`) and inherit `_make_interpreter` here.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any, ClassVar, cast

import httpx

from screamingface.plugins.backend_api_base.plugin_base import BackendApiPluginBase

from .backend import AigwBackend
from .client import AigwGatewayClient, AigwGatewayClientError
from .config import resolve_aigw_runtime_config
from .interpreter import AigwInterpreter
from .settings import AigwBackendApiSettingsBase

if TYPE_CHECKING:
    from fastapi import FastAPI

_log = logging.getLogger(__name__)

# Hard cap on the gateway profile-list fetch performed during schema
# emission. The /plugins/{name}/schema endpoint must never hang the UI.
_SCHEMA_FETCH_TIMEOUT_S = 2.0


class AigwBackendApiPluginBase(BackendApiPluginBase):
    """Base class for every aigw_*_backend plugin."""

    tags: ClassVar[list[str]] = ["product:aigw"]
    depends: ClassVar[list[str]] = ["llm-base", "backend-api-base", "aigw-base"]
    conflicts: ClassVar[list[str]] = []

    # Provider key used by the AI Gateway.
    # Subclasses MUST set this if they want the auth-proxy router mounted.
    gateway_provider: ClassVar[str | None] = None

    def _backend(self, app: FastAPI | None = None) -> AigwBackend:
        settings = cast(AigwBackendApiSettingsBase, self.settings)
        if not self.gateway_provider:
            msg = f"{self.name} must declare gateway_provider"
            raise ValueError(msg)
        gateway_url = _gateway_url(app, settings)
        key = (gateway_url, settings.auth_profile, self.gateway_provider, id(app))
        cached = getattr(self, "_aigw_backend", None)
        if cached is not None and getattr(self, "_aigw_backend_key", None) == key:
            return cached
        backend = AigwBackend(
            gateway_url=gateway_url,
            profile_name=settings.auth_profile,
            gateway_provider=self.gateway_provider,
            app=app,
        )
        self._aigw_backend = backend
        self._aigw_backend_key = key
        return backend

    def _make_interpreter(self, app: FastAPI):
        settings = cast(AigwBackendApiSettingsBase, self.settings)
        if not self.gateway_provider:
            msg = f"{self.name} must declare gateway_provider"
            raise ValueError(msg)
        return AigwInterpreter(
            app=app,
            settings=settings,
            backend=self._backend(app),
            gateway_provider=self.gateway_provider,
        )

    def setup(self, app: FastAPI, hooks, classes, routes) -> None:
        self._app = app
        self._assert_loopback_server_bind(app)
        router = type(self).create_router(self.settings, app, backend=self._backend(app))
        routes.add_router(self.name, router, prefix="")

    def _assert_loopback_server_bind(self, app: FastAPI) -> None:
        if os.environ.get("SF_AIGW_ALLOW_LAN") == "1":
            return
        host = getattr(getattr(app.state, "config", None), "server", None)
        bind_host = getattr(host, "host", "")
        if not bind_host:
            return
        if _is_loopback_host(bind_host):
            return
        msg = (
            f"{self.name} refuses to activate on non-loopback SF host {bind_host!r}; "
            "set SF_AIGW_ALLOW_LAN=1 to override"
        )
        raise RuntimeError(msg)

    # ------------------------------------------------------------------ #
    # Schema customization
    #
    # The aigw_*_backend plugins delegate profile state to the gateway, so
    # the legacy `profiles: dict[str, BackendProfile]` and
    # `default_profile: str` fields inherited from `BackendApiSettingsBase`
    # don't make sense in the SF Settings UI. Strip them from the schema and
    # turn `auth_profile` into a dynamic enum sourced live from gateway
    # compatibility profiles plus active OAuthConnection labels.
    #
    # The runtime model still carries the stripped fields so any legacy code
    # that touches them keeps working — only the UI knob is hidden.
    # ------------------------------------------------------------------ #

    # Inherited fields that don't apply to gateway-based backends. They're
    # CLI-only (`max_budget_usd`, `permission_mode`, `dangerously_skip_permissions`)
    # or replaced by the gateway's profile model (`profiles`, `default_profile`).
    # Hidden from the schema so the SF Settings UI (RJSF) doesn't render
    # noise — and doesn't raise validation errors on them.
    _HIDDEN_INHERITED_FIELDS: ClassVar[tuple[str, ...]] = (
        "profiles",
        "default_profile",
        "gateway_url",
        "max_budget_usd",
        "permission_mode",
        "dangerously_skip_permissions",
    )

    def customize_schema(self, schema: dict) -> dict:
        # Skip the parent's customize_schema — it injects an enum / x-link-base
        # on `default_profile` / `profiles`, both of which we're about to drop.
        props = schema.setdefault("properties", {})
        required = schema.get("required")
        for name in self._HIDDEN_INHERITED_FIELDS:
            props.pop(name, None)
            if isinstance(required, list) and name in required:
                required.remove(name)

        if "auth_profile" in props:
            self._inject_auth_profile_enum(props["auth_profile"])
        return schema

    def _inject_auth_profile_enum(self, auth_profile_field: dict[str, Any]) -> None:
        settings = cast(AigwBackendApiSettingsBase, self.settings)
        current = settings.auth_profile if settings else "default"

        names = self._fetch_gateway_profile_names()
        if names is None:
            # Gateway unreachable: keep the currently-configured value as the
            # only selectable so the user has something to work with offline.
            auth_profile_field["enum"] = [current] if current else []
            return

        # Gateway reachable. The dropdown reflects the gateway's actual
        # profile/connection inventory. We DO surface the currently-configured
        # value if the gateway already lists it (so it shows as selected), but
        # we do NOT inject "default" or the configured value when the gateway
        # has nothing — an empty dropdown correctly tells the user "no profiles
        # yet, go authenticate one".
        auth_profile_field["enum"] = list(names)

    def _fetch_gateway_profile_names(self) -> list[str] | None:
        """Return selectable gateway auth profile/connection names, or ``None`` on error.

        The fetch is synchronous (the schema endpoint is async but the
        customize_schema hook is sync) and bounded by a 2s timeout so a
        wedged gateway can't hang the UI.

        Tests inject ``self._http_transport`` — an ``httpx.MockTransport`` —
        to fully simulate the gateway without a network round-trip.
        """
        if not self.gateway_provider:
            return None
        settings = cast(AigwBackendApiSettingsBase, self.settings)
        if not settings:
            return None
        app = getattr(self, "_app", None)
        transport = getattr(self, "_http_transport", None)
        sync_factory: Callable[[float], httpx.Client] | None = None
        if transport is not None:

            def make_sync_client(timeout: float) -> httpx.Client:
                return httpx.Client(timeout=timeout, transport=transport)

            sync_factory = make_sync_client

        client = AigwGatewayClient(app, sync_http_client_factory=sync_factory)
        try:
            payload = _gateway_json(
                client,
                f"/v1/auth/{self.gateway_provider}/profiles",
            )
        except (AigwGatewayClientError, httpx.HTTPError, ValueError) as exc:
            _log.debug(
                "aigw schema: gateway profile-list fetch failed (%s); "
                "falling back to current auth_profile only",
                exc,
            )
            return None

        names = _names_from_payload(payload, "profiles", "name")
        if names is None:
            return None

        try:
            connections_payload = _gateway_json(
                client,
                f"/v1/oauth/connections?provider={self.gateway_provider}&status=active",
            )
        except (AigwGatewayClientError, httpx.HTTPError, ValueError) as exc:
            _log.debug(
                "aigw schema: gateway connection-list fetch failed (%s); using profile names only",
                exc,
            )
        else:
            connection_names = _names_from_payload(connections_payload, "connections", "label")
            if connection_names is not None:
                names.extend(connection_names)
        return _dedupe_preserving_order(names)


def _gateway_json(client: AigwGatewayClient, path: str) -> Any:
    resp = client.request_sync(
        "GET",
        path,
        timeout_seconds=_SCHEMA_FETCH_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def _names_from_payload(payload: Any, collection_key: str, name_key: str) -> list[str] | None:
    items = payload.get(collection_key) if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get(name_key)
            if isinstance(name, str) and name:
                names.append(name)
    return names


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _gateway_url(app: FastAPI | None, settings: AigwBackendApiSettingsBase) -> str:
    if app is None:
        return settings.gateway_url
    return resolve_aigw_runtime_config(app).gateway_url
