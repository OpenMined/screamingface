"""Tests for ModelRegistry."""

from __future__ import annotations

import pytest

from screamingface.plugins.state.registry import ModelRegistry


def test_register_then_build_config() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["screamingface.plugins.eval_runs.models"])
    cfg = reg.build_config(db_url="sqlite:///:memory:")
    assert cfg["connections"]["default"] == "sqlite:///:memory:"
    assert cfg["apps"]["eval_runs"] == {
        "models": ["screamingface.plugins.eval_runs.models"],
        "default_connection": "default",
    }
    assert cfg["use_tz"] is True
    assert cfg["timezone"] == "UTC"


def test_register_multiple_app_labels() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["screamingface.plugins.eval_runs.models"])
    reg.register("sessions", ["screamingface.plugins.sessions.models"])
    cfg = reg.build_config(db_url="sqlite:///:memory:")
    assert set(cfg["apps"].keys()) == {"eval_runs", "sessions"}


def test_register_duplicate_app_label_raises() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["a"])
    with pytest.raises(ValueError, match="already registered"):
        reg.register("eval_runs", ["b"])


def test_register_empty_modules_raises() -> None:
    reg = ModelRegistry()
    with pytest.raises(ValueError, match="at least one module"):
        reg.register("eval_runs", [])


def test_register_after_init_raises() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["a"])
    reg.mark_initialized()
    with pytest.raises(RuntimeError, match="already initialized"):
        reg.register("sessions", ["b"])


def test_is_empty_flag() -> None:
    reg = ModelRegistry()
    assert reg.is_empty is True
    reg.register("eval_runs", ["a"])
    assert reg.is_empty is False
