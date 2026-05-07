"""Shared lifecycle base for aigw_*_backend plugins.

Subclasses each provider's `*_backend.plugin` mirror of
`claude_backend_api/plugin.py` style: declare class-level metadata
(name, backend_call_paths, schema_link_base, settings_class,
create_router) and inherit `_make_interpreter` here.
"""

from __future__ import annotations

import logging
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
        backend = AigwBackend(
            gateway_url=settings.gateway_url,
            profile_name=settings.auth_profile,
        )
        return AigwInterpreter(app=app, settings=settings, backend=backend)

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

    def customize_schema(self, schema: dict) -> dict:
        # Skip the parent's customize_schema — it injects an enum / x-link-base
        # on `default_profile` / `profiles`, both of which we're about to drop.
        props = schema.setdefault("properties", {})
        props.pop("profiles", None)
        props.pop("default_profile", None)
        required = schema.get("required")
        if isinstance(required, list) and "default_profile" in required:
            required.remove("default_profile")

        if "auth_profile" in props:
            self._inject_auth_profile_enum(props["auth_profile"])
        return schema

    def _inject_auth_profile_enum(self, auth_profile_field: dict[str, Any]) -> None:
        settings = cast(AigwBackendApiSettingsBase, self.settings)
        current = settings.auth_profile if settings else "default"

        names = self._fetch_gateway_profile_names()
        if names is None:
            # Gateway unreachable: still hand the user something useful so the
            # dropdown isn't empty. We populate the enum with the currently
            # configured value only (typically "default" on first run).
            auth_profile_field["enum"] = [current]
            return

        # Gateway reachable. Make sure the configured value is selectable even
        # if the gateway hasn't seen it yet (first-run / not-yet-created).
        merged: list[str] = list(names)
        if current and current not in merged:
            merged.append(current)
        # If the gateway returned no profiles at all, fall back to the
        # configured value plus "default" so the picker is never empty.
        if not merged:
            merged = [current] if current else ["default"]
            if "default" not in merged:
                merged.append("default")
        auth_profile_field["enum"] = merged

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
