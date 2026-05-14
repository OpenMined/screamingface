"""Shared lifecycle base for aigw_*_backend plugins.

Subclasses each provider's `*_backend.plugin` mirror of
`claude_backend_api/plugin.py` style: declare class-level metadata
(name, backend_call_paths, schema_link_base, settings_class,
create_router) and inherit `_make_interpreter` here.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, ClassVar, cast

import httpx

from screamingface.plugins.backend_api_base.plugin_base import BackendApiPluginBase

from .backend import AigwBackend
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

    # Provider key used by the AI Gateway (e.g. "anthropic", "openai").
    # Subclasses MUST set this if they want the auth-proxy router mounted.
    gateway_provider: ClassVar[str | None] = None

    def _make_interpreter(self, app: FastAPI):
        settings = cast(AigwBackendApiSettingsBase, self.settings)
        assert self.gateway_provider, f"{type(self).__name__} must declare gateway_provider"
        backend = AigwBackend(
            gateway_url=settings.gateway_url,
            profile_name=settings.auth_profile,
            gateway_provider=self.gateway_provider,
        )
        return AigwInterpreter(app=app, settings=settings, backend=backend)

    def setup(self, app: FastAPI, hooks, classes, routes) -> None:  # type: ignore[override]
        _assert_loopback_sf_bind(app)
        super().setup(app=app, hooks=hooks, classes=classes, routes=routes)

    # ------------------------------------------------------------------ #
    # Schema customization
    #
    # The aigw_*_backend plugins delegate profile state to the gateway, so
    # the legacy `profiles: dict[str, BackendProfile]` and
    # `default_profile: str` fields inherited from `BackendApiSettingsBase`
    # don't make sense in the SF Settings UI. Strip them from the schema and
    # turn `auth_profile` into a dynamic enum sourced live from the gateway's
    # `GET /v1/auth/<provider>/profiles` endpoint.
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
        # profile inventory. We DO surface the currently-configured value if
        # the gateway already lists it (so it shows as selected), but we do
        # NOT inject "default" or the configured value when the gateway has
        # nothing — an empty dropdown correctly tells the user "no profiles
        # yet, go authenticate one".
        auth_profile_field["enum"] = list(names)

    def _fetch_gateway_profile_names(self) -> list[str] | None:
        """Return profile names from the gateway, or ``None`` on any error.

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
        url = f"{settings.gateway_url.rstrip('/')}/v1/auth/{self.gateway_provider}/profiles"
        transport = getattr(self, "_http_transport", None)
        try:
            with httpx.Client(
                timeout=_SCHEMA_FETCH_TIMEOUT_S,
                transport=transport,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            _log.debug(
                "aigw schema: gateway profile-list fetch failed (%s); "
                "falling back to current auth_profile only",
                exc,
            )
            return None

        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        if not isinstance(profiles, list):
            return None
        names: list[str] = []
        for p in profiles:
            if isinstance(p, dict):
                name = p.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
        return names


def _assert_loopback_sf_bind(app: FastAPI) -> None:
    if os.environ.get("SF_AIGW_ALLOW_LAN") == "1":
        return
    config = getattr(app.state, "config", None)
    server = getattr(config, "server", None)
    host = getattr(server, "host", "127.0.0.1")
    if host in {"127.0.0.1", "localhost", "::1"}:
        return
    raise RuntimeError(
        "gateway-backed backends require SF to bind loopback only; "
        "start with --host 127.0.0.1 or set SF_AIGW_ALLOW_LAN=1 to override"
    )
