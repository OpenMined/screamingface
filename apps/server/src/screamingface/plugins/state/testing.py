"""Pytest fixtures plugins can import for their own tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig


@pytest.fixture
def temp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point SF_STATE__PATH at a fresh sqlite file under tmp_path."""
    db = tmp_path / "state.db"
    monkeypatch.setenv("SF_STATE__PATH", str(db))
    return db


@pytest.fixture
async def initialized_state(temp_state_path: Path) -> AsyncIterator[FastAPI]:
    """Boot a minimal FastAPI app with the state plugin active.

    Yields the app *after* the startup hook has run (Tortoise initialized),
    and runs the shutdown hook on teardown.
    """
    config = AppConfig(plugins=["state"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app
