"""Regression tests for FrontendPluginBase._current_spec_expressions.

The active-spec enum and url4 resolution both read their ``{name: expression}``
map from this method. It must merge two sources — the in-memory ``url4-specs``
plugin settings (authoritative for the running process) and a fresh on-disk
``load_config()`` read (supplements direct ``sf.json`` edits) — with the
in-memory config winning on name conflicts.

History (SF-231 regression): a disk-first implementation read ``./sf.json``
relative to cwd and returned it whenever non-empty. When the server booted from
inline ``--config-json`` (no matching file on disk, as in e2e) that unrelated
``sf.json`` shadowed the real running specs, so the active spec resolved to
nothing and no url4 context was injected. These tests pin the merge behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import screamingface.core.config as config_mod
from screamingface.core.config import AppConfig
from screamingface.plugins.frontend_base.plugin_base import FrontendPluginBase


def _app_with_inmemory_specs(specs: dict[str, str]) -> Any:
    settings = SimpleNamespace(
        specs={name: SimpleNamespace(expression=expr) for name, expr in specs.items()}
    )
    url4_plugin = SimpleNamespace(settings=settings)
    return SimpleNamespace(
        state=SimpleNamespace(plugins=SimpleNamespace(active_plugins={"url4-specs": url4_plugin}))
    )


def _self_with(app: Any) -> Any:
    """A minimal stand-in: the method only touches ``self._app``."""
    return SimpleNamespace(_app=app)


def _patch_disk(monkeypatch, specs: dict[str, str] | None) -> None:
    plugin_config: dict[str, Any] = {}
    if specs is not None:
        plugin_config["url4-specs"] = {
            "specs": {name: {"expression": expr} for name, expr in specs.items()}
        }
    cfg = AppConfig(plugin_config=plugin_config)
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: cfg)


def test_inmemory_only_when_disk_has_unrelated_specs(monkeypatch) -> None:
    """The running config (in-memory) must surface even when the on-disk
    ``sf.json`` holds a completely different set of specs."""
    _patch_disk(monkeypatch, {"DiskOnly": "(https://disk)!'x'"})
    app = _app_with_inmemory_specs({"httpbin-robots": "(https://robots)!'y'"})

    result = FrontendPluginBase._current_spec_expressions(_self_with(app))

    assert result["httpbin-robots"] == "(https://robots)!'y'"
    # disk spec supplements, does not shadow
    assert result["DiskOnly"] == "(https://disk)!'x'"


def test_inmemory_wins_on_name_conflict(monkeypatch) -> None:
    _patch_disk(monkeypatch, {"shared": "(https://stale-disk)!'old'"})
    app = _app_with_inmemory_specs({"shared": "(https://live)!'new'"})

    result = FrontendPluginBase._current_spec_expressions(_self_with(app))

    assert result["shared"] == "(https://live)!'new'"


def test_disk_supplements_specs_missing_from_memory(monkeypatch) -> None:
    """A spec added by editing sf.json directly (never via the settings POST)
    is still visible even though the in-memory settings don't have it."""
    _patch_disk(monkeypatch, {"DiskAdded": "(https://disk)!'z'"})
    app = _app_with_inmemory_specs({})

    result = FrontendPluginBase._current_spec_expressions(_self_with(app))

    assert result == {"DiskAdded": "(https://disk)!'z'"}


def test_empty_when_no_specs_anywhere(monkeypatch) -> None:
    _patch_disk(monkeypatch, None)
    app = _app_with_inmemory_specs({})

    result = FrontendPluginBase._current_spec_expressions(_self_with(app))

    assert result == {}
