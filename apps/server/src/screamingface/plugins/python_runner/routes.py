"""Routes for the python-runner plugin.

Exposes ``GET /data/code/{name}.py`` — the local source-of-truth surface
URL4 expressions reference. Source comes from
``python-runner.scripts.<name>`` settings (DEMO-009); the script-name
validator in :class:`PythonRunnerSettings` already enforces the
``^[a-zA-Z_][a-zA-Z0-9_]*$`` pattern at write-time, so this route only
needs to look the name up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.plugins.python_runner.plugin import PythonRunnerSettings


def _get_python_runner_settings(app: FastAPI) -> PythonRunnerSettings:
    plugin = app.state.plugins.active_plugins["python-runner"]
    return plugin.settings


def create_router(app: FastAPI) -> APIRouter:
    del app  # we read settings off request.app at request time, not bind time
    router = APIRouter(tags=["python-runner"])

    @router.get("/data/code/{name}.py", response_class=PlainTextResponse)
    async def serve_script(name: str, request: Request) -> PlainTextResponse:
        settings = _get_python_runner_settings(request.app)
        if name not in settings.scripts:
            raise HTTPException(status_code=404, detail=f"No script named {name!r}")
        return PlainTextResponse(
            settings.scripts[name],
            media_type="text/x-python",
        )

    return router
