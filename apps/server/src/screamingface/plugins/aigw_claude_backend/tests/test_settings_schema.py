"""Tests for AigwBackendApiPluginBase.customize_schema.

Covers SF-191 part B (B-shape):
- The legacy `profiles` and `default_profile` fields are stripped from
  the schema produced for the SF Settings UI.
- `auth_profile` becomes a dynamic enum sourced from gateway profiles
  plus active OAuthConnection labels.
- Schema emission tolerates a gateway that's down: it MUST NOT raise.
- The currently-configured `auth_profile` is included in the dropdown
  even if the gateway list doesn't yet contain it.

We exercise the public path: build the JSON schema the same way
``/plugins/{name}/schema`` does (``settings_class.model_json_schema()``)
and call ``plugin.customize_schema(schema)``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from screamingface.plugins.aigw_base.client import gateway_session_state
from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def _make_plugin(
    *,
    auth_profile: str = "default",
    transport: httpx.MockTransport | None = None,
    mode: str = "local_managed",
) -> AigwClaudeBackendPlugin:
    plugin = AigwClaudeBackendPlugin()
    plugin.settings = AigwClaudeBackendSettings(auth_profile=auth_profile)
    plugin._app = SimpleNamespace(  # type: ignore[attr-defined]
        state=SimpleNamespace(
            config=SimpleNamespace(
                plugin_config={
                    "aigw-base": {
                        "mode": mode,
                        "gateway_url": "http://gateway",
                    }
                }
            ),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )
    if transport is not None:
        # The implementation reads this attribute (if present) to build a
        # synchronous httpx.Client. Tests inject a MockTransport here so the
        # gateway is fully simulated.
        plugin._http_transport = transport  # type: ignore[attr-defined]
    return plugin


def _emit_schema(plugin: AigwClaudeBackendPlugin) -> dict[str, Any]:
    schema = plugin.settings_class.model_json_schema()  # type: ignore[union-attr]
    return plugin.customize_schema(schema)


def _gateway_profiles_handler(
    profiles: list[dict[str, Any]],
    connections: list[dict[str, Any]] | None = None,
    models: list[dict[str, Any]] | None = None,
):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/v1/auth/anthropic/profiles"):
            return httpx.Response(200, json={"profiles": profiles})
        if req.url.path.endswith("/v1/oauth/connections"):
            assert req.url.params["provider"] == "anthropic"
            assert req.url.params["status"] == "active"
            return httpx.Response(200, json={"connections": connections or []})
        if req.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": models or []})
        raise AssertionError(f"unexpected gateway request: {req.url}")

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


def test_schema_auth_profile_enum_includes_active_oauth_connection_labels() -> None:
    handler = _gateway_profiles_handler(
        [{"name": "default"}],
        [
            {"label": "work-anthropic", "status": "active"},
            {"label": "default", "status": "active"},
        ],
    )
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)

    assert schema["properties"]["auth_profile"]["enum"] == ["default", "work-anthropic"]


def test_schema_fetch_uses_gateway_session_token_in_external_mode() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer session-token"
        if req.url.path.endswith("/v1/auth/anthropic/profiles"):
            return httpx.Response(200, json={"profiles": [{"name": "work"}]})
        if req.url.path.endswith("/v1/oauth/connections"):
            return httpx.Response(200, json={"connections": []})
        if req.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"unexpected gateway request: {req.url}")

    plugin = _make_plugin(mode="external", transport=httpx.MockTransport(handler))
    gateway_session_state(plugin._app).set_token(  # type: ignore[attr-defined]
        "session-token",
        datetime.now(UTC) + timedelta(minutes=5),
    )

    schema = _emit_schema(plugin)

    assert schema["properties"]["auth_profile"]["enum"] == ["work"]


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


# --------------------------------------------------------------------------- #
# SF-284: default_model / fallback_model `examples` are derived from the
# gateway's live /v1/models registry instead of a hard-coded SF-side copy.
# --------------------------------------------------------------------------- #


def _anthropic_models(*ids: str) -> list[dict[str, Any]]:
    return [{"id": i, "object": "model", "owned_by": "anthropic"} for i in ids]


def test_model_fields_have_no_static_examples_before_customization() -> None:
    """The plugin must NOT bake a hard-coded model list into the field schema.

    Guards the DRY contract: suggestions come from the gateway at schema time,
    not a constant duplicating the gateway registry.
    """
    base_props = AigwClaudeBackendSettings.model_json_schema()["properties"]
    assert not base_props["default_model"].get("examples")
    assert not base_props["fallback_model"].get("examples")


def test_model_examples_derived_from_gateway_models() -> None:
    handler = _gateway_profiles_handler(
        [{"name": "default"}],
        models=_anthropic_models("claude-opus-4-8", "claude-sonnet-4-5", "claude-haiku-4-5"),
    )
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)

    # Bare gateway ids are prefixed with the provider key to match the SF
    # `<provider>/<model>` form the backend sends.
    expected = [
        "anthropic/claude-opus-4-8",
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-haiku-4-5",
    ]
    assert schema["properties"]["default_model"]["examples"] == expected
    assert schema["properties"]["fallback_model"]["examples"] == expected


def test_model_examples_exclude_other_providers() -> None:
    """/v1/models aggregates every provider; only this backend's are suggested."""
    models = _anthropic_models("claude-opus-4-8") + [
        {"id": "gpt-5.4-mini", "object": "model", "owned_by": "codex"},
        {"id": "gemini-2.5-flash", "object": "model", "owned_by": "gemini-cli"},
    ]
    handler = _gateway_profiles_handler([{"name": "default"}], models=models)
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)

    assert schema["properties"]["default_model"]["examples"] == ["anthropic/claude-opus-4-8"]


def test_model_examples_do_not_double_prefix_already_prefixed_ids() -> None:
    """Gateway registries are inconsistent: codex/gemini model ids already carry
    the `<provider>/` prefix while anthropic's are bare. Prefixing must be
    idempotent so a `codex/...` id never becomes `codex/codex/...`."""
    models = [{"id": "anthropic/claude-opus-4-8", "object": "model", "owned_by": "anthropic"}]
    handler = _gateway_profiles_handler([{"name": "default"}], models=models)
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)

    assert schema["properties"]["default_model"]["examples"] == ["anthropic/claude-opus-4-8"]


def test_model_examples_remain_free_text_no_enum() -> None:
    """Suggestions use `examples` (datalist), never `enum` — a brand-new
    snapshot the gateway already supports must still be typeable."""
    handler = _gateway_profiles_handler(
        [{"name": "default"}], models=_anthropic_models("claude-opus-4-8")
    )
    plugin = _make_plugin(transport=httpx.MockTransport(handler))
    schema = _emit_schema(plugin)

    assert "enum" not in schema["properties"]["default_model"]
    assert "enum" not in schema["properties"]["fallback_model"]


def test_model_examples_fall_back_to_configured_value_when_gateway_down() -> None:
    """Offline: the dropdown shows each field's currently-configured value so
    the user isn't staring at an empty list. Free-text still works."""

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gateway down")

    plugin = _make_plugin(transport=httpx.MockTransport(boom))
    schema = _emit_schema(plugin)

    settings = cast(AigwClaudeBackendSettings, plugin.settings)
    assert schema["properties"]["default_model"]["examples"] == [settings.default_model]
    assert schema["properties"]["fallback_model"]["examples"] == [settings.fallback_model]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
