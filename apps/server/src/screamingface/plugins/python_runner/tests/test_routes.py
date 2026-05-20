"""Tests for the /data/code/{name}.py serve route (SF-159 / DEMO-013)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)
from screamingface.plugins.python_runner.routes import create_router

SCRIPT_BODY = "import json, sys; print(json.dumps({'ok': True}))\n"


@pytest.fixture
def app_with_runner() -> Iterator[FastAPI]:
    """A FastAPI app with python-runner mounted and one script in settings."""
    app = FastAPI()
    plugin = PythonRunnerPlugin()
    plugin.settings = PythonRunnerSettings(scripts={"check_correct": SCRIPT_BODY})

    class _Registry:
        active_plugins = {"python-runner": plugin}

    app.state.plugins = _Registry()
    app.include_router(create_router(app))
    yield app


@pytest.mark.asyncio
async def test_serve_known_script_returns_python_source(app_with_runner: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/check_correct.py")
    assert resp.status_code == 200
    assert resp.text == SCRIPT_BODY
    assert resp.headers["content-type"].startswith("text/x-python")


@pytest.mark.asyncio
async def test_serve_unknown_script_returns_404(app_with_runner: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/nonexistent.py")
    assert resp.status_code == 404
    assert "nonexistent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_serve_invalid_name_with_dashes_returns_404(
    app_with_runner: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/has-dashes.py")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_reflects_settings_edit(app_with_runner: FastAPI) -> None:
    plugin = app_with_runner.state.plugins.active_plugins["python-runner"]
    plugin.settings = PythonRunnerSettings(scripts={"check_correct": "print('updated')\n"})

    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/check_correct.py")
    assert resp.status_code == 200
    assert resp.text == "print('updated')\n"
