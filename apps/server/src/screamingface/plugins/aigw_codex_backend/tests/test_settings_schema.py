from __future__ import annotations

from typing import Any

import httpx

from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)


def _emit_schema(plugin: AigwCodexBackendPlugin) -> dict[str, Any]:
    schema = plugin.settings_class.model_json_schema()  # type: ignore[union-attr]
    return plugin.customize_schema(schema)


def test_schema_omits_inapplicable_inherited_fields() -> None:
    plugin = AigwCodexBackendPlugin()
    plugin.settings = AigwCodexBackendSettings()  # type: ignore[assignment]
    plugin._http_transport = httpx.MockTransport(  # type: ignore[attr-defined]
        lambda req: httpx.Response(200, json={"profiles": []})
    )

    schema = _emit_schema(plugin)
    props = schema["properties"]
    assert "profiles" not in props
    assert "default_profile" not in props
    assert "max_budget_usd" not in props
    assert "permission_mode" not in props
    assert "dangerously_skip_permissions" not in props
    assert "auth_profile" in props


def test_schema_auth_profile_enum_uses_codex_gateway_provider() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        return httpx.Response(200, json={"profiles": [{"name": "default"}, {"name": "work"}]})

    plugin = AigwCodexBackendPlugin()
    plugin.settings = AigwCodexBackendSettings()  # type: ignore[assignment]
    plugin._http_transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]

    schema = _emit_schema(plugin)

    assert captured["path"] == "/v1/auth/codex/profiles"
    assert schema["properties"]["auth_profile"]["enum"] == ["default", "work"]
