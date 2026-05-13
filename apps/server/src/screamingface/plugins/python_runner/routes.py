"""Routes for the python-runner plugin.

Scaffold only — the real ``/data/code/<name>.py`` serve route and the body of
``handle_backend_call`` land in DEMO-013.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_router(app: FastAPI) -> APIRouter:
    """Return the plugin's APIRouter. Empty until DEMO-013 wires real routes."""
    del app  # consumed by DEMO-013
    return APIRouter()
