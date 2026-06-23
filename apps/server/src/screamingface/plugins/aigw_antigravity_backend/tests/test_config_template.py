"""Fresh-template config coverage (plan §5).

The fresh `sf.json` template must enable `aigw-antigravity-backend` and ship a
default `plugin_config` block so new Desktop/server installs get the
experimental provider. (Existing-user auto-enable is intentionally NOT done in
the always-run runtime-config migration — that is a documented follow-up.)
"""

from __future__ import annotations

import json
from pathlib import Path

# apps/server/sf.json — five parents up from this test file:
# .../aigw_antigravity_backend/tests/test_config_template.py
_SF_JSON = Path(__file__).resolve().parents[5] / "sf.json"


def _load() -> dict:
    return json.loads(_SF_JSON.read_text())


def test_sf_json_enables_antigravity_backend() -> None:
    config = _load()
    assert "aigw-antigravity-backend" in config["plugins"]


def test_sf_json_does_not_globally_enable_callback_bridge() -> None:
    # aigw-callback must NOT be in the global plugins list — enabling it
    # globally flips gemini/codex/anthropic onto the loopback bridge in hosted
    # mode (cross-backend regression, review #6). It is instead auto-activated
    # via aigw-antigravity-backend's `depends` only when antigravity is enabled.
    config = _load()
    assert "aigw-callback" not in config["plugins"]


def test_sf_json_has_antigravity_default_config_block() -> None:
    config = _load()
    block = config["plugin_config"]["aigw-antigravity-backend"]
    assert block["default_model"] == "antigravity/gemini-3.5-flash"
    assert block["gateway_url"] == "http://127.0.0.1:9105"


def test_antigravity_does_not_replace_gemini_backend() -> None:
    # The experimental provider is additive; the gemini backend stays enabled
    # so users can compare/migrate.
    config = _load()
    assert "aigw-gemini-backend" in config["plugins"]
    assert "aigw-antigravity-backend" in config["plugins"]
