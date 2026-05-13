"""Unit tests for StatePlugin / StateSettings (no DB yet)."""

from __future__ import annotations

from pathlib import Path

from screamingface.plugins.state.plugin import StatePlugin, StateSettings


def test_settings_defaults(monkeypatch) -> None:
    # Strip any host-env overrides
    monkeypatch.delenv("SF_STATE__PATH", raising=False)
    monkeypatch.delenv("SF_STATE__ECHO", raising=False)
    s = StateSettings()
    assert s.path == Path.home() / ".screamingface" / "state.db"
    assert s.echo is False


def test_settings_env_override(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "x.db"
    monkeypatch.setenv("SF_STATE__PATH", str(target))
    monkeypatch.setenv("SF_STATE__ECHO", "true")
    s = StateSettings()
    assert s.path == target
    assert s.echo is True


def test_plugin_class_attrs() -> None:
    assert StatePlugin.name == "state"
    assert StatePlugin.settings_class is StateSettings
    assert StatePlugin.depends == []
