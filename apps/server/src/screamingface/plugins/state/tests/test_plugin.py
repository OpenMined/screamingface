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


# --- Integration tests below ---

import pytest
from fastapi import FastAPI
from tortoise import Tortoise

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.state.tests.fixtures.toy_models import ToyItem


@pytest.fixture
async def app_with_toy(temp_state_path: Path):
    """Boot an app with the state plugin and register the toy model in-test."""
    config = AppConfig(plugins=["state"], plugin_config={})
    app = create_app(config)

    # Reach the StatePlugin instance attached to app.state during setup()
    # (StatePlugin.setup sets app.state.state_plugin = self).
    state: StatePlugin = app.state.state_plugin
    state.register_models(
        "toy",
        ["screamingface.plugins.state.tests.fixtures.toy_models"],
    )

    async with app.router.lifespan_context(app):
        yield app


async def test_startup_initializes_tortoise(app_with_toy: FastAPI) -> None:
    assert app_with_toy.state.state_ready is True
    # ToyItem table exists — a query against an unknown table would raise.
    count = await ToyItem.all().count()
    assert count == 0


async def test_baseStore_roundtrip(app_with_toy: FastAPI) -> None:
    from screamingface.plugins.state.store import BaseStore

    store: BaseStore[ToyItem] = BaseStore(ToyItem)
    created = await store.create(name="alpha", weight=3)
    assert created.id is not None
    assert created.name == "alpha"

    fetched = await store.get(created.id)
    assert fetched is not None
    assert fetched.name == "alpha"
    assert fetched.weight == 3

    listed = await store.list(limit=10)
    assert len(listed) == 1

    updated = await store.update(created.id, weight=99)
    assert updated.weight == 99

    deleted = await store.delete(created.id)
    assert deleted is True
    assert await store.get(created.id) is None


async def test_get_missing_returns_none(app_with_toy: FastAPI) -> None:
    from uuid import uuid4

    from screamingface.plugins.state.store import BaseStore

    store: BaseStore[ToyItem] = BaseStore(ToyItem)
    assert await store.get(uuid4()) is None


async def test_register_after_init_raises(app_with_toy: FastAPI) -> None:
    state: StatePlugin = app_with_toy.state.state_plugin
    with pytest.raises(RuntimeError, match="already initialized"):
        state.register_models("late", ["x"])


async def test_generate_schemas_is_idempotent(temp_state_path: Path) -> None:
    """Booting twice against the same DB file must not error."""
    config = AppConfig(plugins=["state"], plugin_config={})

    for _ in range(2):
        app = create_app(config)
        state: StatePlugin = app.state.state_plugin
        state.register_models(
            "toy",
            ["screamingface.plugins.state.tests.fixtures.toy_models"],
        )
        async with app.router.lifespan_context(app):
            assert app.state.state_ready is True
