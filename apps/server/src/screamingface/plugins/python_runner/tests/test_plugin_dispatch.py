"""Tests for PythonRunnerPlugin.handle_backend_call (SF-159 / DEMO-013)."""

from __future__ import annotations

import json
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException

from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)
from screamingface.plugins.python_runner.routes import create_router

ECHO_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"got": data}))
"""

SYNTAX_ERROR_SCRIPT = "this is not valid python(\n"


def _make_app(scripts: dict[str, str]) -> FastAPI:
    app = FastAPI()
    plugin = PythonRunnerPlugin()
    plugin.settings = PythonRunnerSettings(scripts=scripts)

    class _Registry:
        active_plugins = {"python-runner": plugin}

    app.state.plugins = _Registry()
    app.include_router(create_router(app))
    return app


@pytest.mark.asyncio
async def test_handle_backend_call_relative_source_runs_and_returns_json() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    result = await plugin.handle_backend_call(
        json.dumps({"a": 1}),
        sources="/data/code/echo.py",
        app=app,
    )

    assert json.loads(result) == {"got": {"a": 1}}


@pytest.mark.asyncio
async def test_handle_backend_call_empty_intent_passes_empty_dict() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    result = await plugin.handle_backend_call(
        "",
        sources="/data/code/echo.py",
        app=app,
    )

    assert json.loads(result) == {"got": {}}


@pytest.mark.asyncio
async def test_handle_backend_call_http_source_fetched_via_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app({})
    plugin = app.state.plugins.active_plugins["python-runner"]

    async def fake_fetch_url(url: str) -> str:
        assert url == "https://example.com/echo.py"
        return ECHO_SCRIPT

    monkeypatch.setattr(
        "screamingface.plugins.python_runner.plugin._fetch_url",
        fake_fetch_url,
    )

    result = await plugin.handle_backend_call(
        json.dumps({"b": 2}),
        sources="https://example.com/echo.py",
        app=app,
    )

    assert json.loads(result) == {"got": {"b": 2}}


@pytest.mark.asyncio
async def test_handle_backend_call_unsupported_scheme_raises_http_400() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    with pytest.raises(HTTPException) as excinfo:
        await plugin.handle_backend_call("", sources="ftp://example.com/echo.py", app=app)
    assert excinfo.value.status_code == 400
    detail = cast(dict[str, str], excinfo.value.detail)
    assert detail["kind"] == "io_error"


@pytest.mark.asyncio
async def test_handle_backend_call_syntax_error_surfaces_as_http_500() -> None:
    app = _make_app({"broken": SYNTAX_ERROR_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    with pytest.raises(HTTPException) as excinfo:
        await plugin.handle_backend_call("{}", sources="/data/code/broken.py", app=app)
    assert excinfo.value.status_code == 500
    detail = cast(dict[str, str], excinfo.value.detail)
    assert detail["kind"] == "nonzero_exit"
    assert "SyntaxError" in detail["stderr"]


@pytest.mark.asyncio
async def test_handle_backend_call_fetch_404_propagates_as_http_400() -> None:
    app = _make_app({})  # /data/code/missing.py 404s
    plugin = app.state.plugins.active_plugins["python-runner"]

    with pytest.raises(HTTPException) as excinfo:
        await plugin.handle_backend_call("", sources="/data/code/missing.py", app=app)
    assert excinfo.value.status_code == 400
    detail = cast(dict[str, str], excinfo.value.detail)
    assert detail["kind"] == "io_error"
