"""Shared lifecycle base for aigw_*_backend plugins.

Subclasses mirror direct backend plugin style: declare class-level metadata
(`name`, `backend_call_paths`, `schema_link_base`, `settings_class`,
`create_route_bundle`/`create_router`) and inherit `_make_interpreter` here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, cast

import httpx

from screamingface.core.local_only import assert_loopback_server_bind
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
        bundle = type(self).create_route_bundle(self.settings, app, backend=self._backend(app))
        routes.add_router(self.name, bundle.router, prefix="")
        # SF-346: same explicit profile-alias wiring capture as
        # BackendApiPluginBase.setup (this override does not call super().setup()).
        self._api_config = bundle.config

    def _refresh_api_config_for_alias(self, app: FastAPI) -> None:
        super()._refresh_api_config_for_alias(app)
        if self._api_config is not None:
            self._api_config.backend = self._backend(app)

    def _assert_loopback_server_bind(self, app: FastAPI) -> None:
        assert_loopback_server_bind(
            app,
            self.name,
            allow_env_vars=("SF_SERVER_ALLOW_LAN",),
        )

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

    # Settings fields that hold a `<provider>/<model>` string and should offer
    # a gateway-derived suggestion dropdown. Not every subclass declares both
    # (only aigw-claude-backend has a `fallback_model`); absent fields are
    # skipped. Populated dynamically in `customize_schema` (SF-284).
    _MODEL_SUGGESTION_FIELDS: ClassVar[tuple[str, ...]] = (
        "default_model",
        "fallback_model",
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
        self._inject_model_suggestions(props)
        return schema

    def _inject_model_suggestions(self, props: dict[str, Any]) -> None:
        """Populate the model fields' ``examples`` from the gateway's live
        ``/v1/models`` registry (SF-284).

        The SF Settings model dropdown thus reflects exactly what the gateway
        can route, with no hard-coded copy of the gateway's model list. We set
        ``examples`` (a free-text datalist), never ``enum``: a brand-new
        snapshot the gateway already supports must remain typeable before this
        derivation is refreshed.
        """
        present = [name for name in self._MODEL_SUGGESTION_FIELDS if name in props]
        if not present:
            return

        suggestions = self._fetch_gateway_model_ids()
        if suggestions is not None:
            for name in present:
                props[name]["examples"] = list(suggestions)
            return

        # Gateway unreachable: fall back to each field's currently-configured
        # value so the dropdown isn't empty offline (mirrors the auth_profile
        # fallback). Free-text entry still works either way.
        settings = self.settings
        for name in present:
            current = getattr(settings, name, None) if settings else None
            props[name]["examples"] = [current] if current else []

    def _fetch_gateway_model_ids(self) -> list[str] | None:
        """Return this provider's gateway models as SF ``<provider>/<model>``
        strings, or ``None`` when the gateway can't be reached.

        Mirrors `_fetch_gateway_profile_names`: synchronous, bounded by
        `_SCHEMA_FETCH_TIMEOUT_S`, and tolerant of a down gateway. ``/v1/models``
        aggregates every loaded provider, so results are filtered to this
        backend's `gateway_provider` (which equals the gateway's ``owned_by``).
        """
        if not self.gateway_provider:
            return None
        if self.settings is None:
            return None
        client = self._schema_gateway_client()
        try:
            payload = _gateway_json(client, "/v1/models")
        except (AigwGatewayClientError, httpx.HTTPError, ValueError) as exc:
            _log.debug(
                "aigw schema: gateway model-list fetch failed (%s); "
                "falling back to configured model values",
                exc,
            )
            return None
        return _model_ids_from_payload(payload, self.gateway_provider)

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
        if self.settings is None:
            return None
        client = self._schema_gateway_client()
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

    def _schema_gateway_client(self) -> AigwGatewayClient:
        """Build the gateway client used during synchronous schema emission.

        Tests inject ``self._http_transport`` — an ``httpx.MockTransport`` — to
        fully simulate the gateway without a network round-trip; otherwise the
        client talks to the real (local) gateway.
        """
        app = getattr(self, "_app", None)
        transport = getattr(self, "_http_transport", None)
        sync_factory: Callable[[float], httpx.Client] | None = None
        if transport is not None:

            def make_sync_client(timeout: float) -> httpx.Client:
                return httpx.Client(timeout=timeout, transport=transport)

            sync_factory = make_sync_client

        return AigwGatewayClient(app, sync_http_client_factory=sync_factory)


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


def _model_ids_from_payload(payload: Any, provider: str) -> list[str] | None:
    """Extract this provider's model ids from an OpenAI-shaped ``/v1/models``
    body, as SF ``<provider>/<model>`` strings.

    The endpoint aggregates every loaded provider and tags each entry with
    ``owned_by``; we keep only ``owned_by == provider`` and normalize the id to
    the SF ``<provider>/<model>`` form the backend sends. Prefixing is
    idempotent: gateway registries are inconsistent — anthropic ids are bare
    (``claude-sonnet-4-5``) while codex/gemini ids already carry the prefix
    (``codex/gpt-5.5``) — so we only prepend when it isn't already there.
    Returns ``None`` if the payload isn't the expected ``{"data": [...]}`` shape.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None
    prefix = f"{provider}/"
    ids: list[str] = []
    for item in data:
        if not isinstance(item, dict) or item.get("owned_by") != provider:
            continue
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id:
            ids.append(model_id if model_id.startswith(prefix) else f"{prefix}{model_id}")
    return _dedupe_preserving_order(ids)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _gateway_url(app: FastAPI | None, settings: AigwBackendApiSettingsBase) -> str:
    if app is None:
        return settings.gateway_url
    return resolve_aigw_runtime_config(app).gateway_url
