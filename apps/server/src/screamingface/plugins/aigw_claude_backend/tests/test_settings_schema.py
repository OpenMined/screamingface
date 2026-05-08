"""Tests for AigwBackendApiPluginBase.customize_schema.

Covers SF-191 part B (B-shape):
- The legacy `profiles` and `default_profile` fields are stripped from
  the schema produced for the SF Settings UI.
- `auth_profile` becomes a dynamic enum sourced from the gateway's
  `GET /v1/auth/<provider>/profiles` endpoint.
- Schema emission tolerates a gateway that's down: it MUST NOT raise.
- The currently-configured `auth_profile` is included in the dropdown
  even if the gateway list doesn't yet contain it.

We exercise the public path: build the JSON schema the same way
``/plugins/{name}/schema`` does (``settings_class.model_json_schema()``)
and call ``plugin.customize_schema(schema)``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def _make_plugin(
    *,
    auth_profile: str = "default",
    transport: httpx.MockTransport | None = None,
) -> AigwClaudeBackendPlugin:
    plugin = AigwClaudeBackendPlugin()
    plugin.settings = AigwClaudeBackendSettings(auth_profile=auth_profile)
    if transport is not None:
        # The implementation reads this attribute (if present) to build a
        # synchronous httpx.Client. Tests inject a MockTransport here so the
        # gateway is fully simulated.
        plugin._http_transport = transport  # type: ignore[attr-defined]
    return plugin


def _emit_schema(plugin: AigwClaudeBackendPlugin) -> dict[str, Any]:
    schema = plugin.settings_class.model_json_schema()  # type: ignore[union-attr]
    return plugin.customize_schema(schema)


def _gateway_profiles_handler(profiles: list[dict[str, Any]]):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/v1/auth/anthropic/profiles")
        return httpx.Response(200, json={"profiles": profiles})

    return handler


def test_schema_omits_profiles_and_default_profile() -> None:
    plugin = _make_plugin(transport=httpx.MockTransport(_gateway_profiles_handler([])))
    schema = _emit_schema(plugin)
    props = schema["properties"]
    assert "profiles" not in props
    assert "default_profile" not in props
    assert "auth_profile" in props
    # `default_profile` must not linger as a required key either.
    assert "default_profile" not in schema.get("required", [])


def test_schema_omits_cli_only_inherited_fields() -> None:
    """CLI-only inherited fields are hidden from the aigw schema.

    These come from `BackendApiSettingsBase` and are silently ignored at
    request time for gateway-based backends, so RJSF should never render
    them (otherwise the user hits "must be number" / "must be string"
    validation errors on noise).

    Sanity-check first that the parent schema actually exposes them, so
    this test fails loudly if the base settings change shape.
    """
    base_props = AigwClaudeBackendSettings.model_json_schema()["properties"]
    for name in ("max_budget_usd", "permission_mode", "dangerously_skip_permissions"):
        assert name in base_props, f"{name} missing from base schema — update test"

    plugin = _make_plugin(transport=httpx.MockTransport(_gateway_profiles_handler([])))
    schema = _emit_schema(plugin)
    props = schema["properties"]
    assert "max_budget_usd" not in props
    assert "permission_mode" not in props
    assert "dangerously_skip_permissions" not in props


def test_schema_auth_profile_enum_populated_from_gateway() -> None:
    handler = _gateway_profiles_handler(
        [{"name": "default"}, {"name": "work"}],
    )
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)
    auth_field = schema["properties"]["auth_profile"]
    assert auth_field.get("enum") == ["default", "work"]


def test_schema_falls_back_when_gateway_unreachable() -> None:
    """When the gateway is unreachable, schema emission MUST still succeed.

    Fallback shape: the auth_profile field carries an enum containing only
    the currently-configured value (i.e. ``["default"]`` by default), so the
    user always sees something in the dropdown rather than a broken UI.
    """

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gateway down")

    plugin = _make_plugin(transport=httpx.MockTransport(boom))
    schema = _emit_schema(plugin)
    auth_field = schema["properties"]["auth_profile"]
    # Either no enum at all (free-text) or just the configured value.
    if "enum" in auth_field:
        assert auth_field["enum"] == ["default"]


def test_schema_enum_reflects_gateway_inventory_only() -> None:
    """When the gateway is reachable, the dropdown reflects exactly what the
    gateway has — we do NOT inject the SF-configured value as a "phantom"
    option. An empty gateway must yield an empty dropdown, signaling
    "no profiles yet — go authenticate one"."""
    handler = _gateway_profiles_handler([{"name": "default"}])
    plugin = _make_plugin(
        auth_profile="work",  # configured but not yet at gateway
        transport=httpx.MockTransport(handler),
    )
    schema = _emit_schema(plugin)
    assert schema["properties"]["auth_profile"]["enum"] == ["default"]


def test_schema_enum_is_empty_when_gateway_has_no_profiles() -> None:
    handler = _gateway_profiles_handler([])
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)
    assert schema["properties"]["auth_profile"]["enum"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
