"""Shared lifecycle base for aigw_*_backend plugins.

Subclasses each provider's `*_backend.plugin` mirror of
`claude_backend_api/plugin.py` style: declare class-level metadata
(name, backend_call_paths, schema_link_base, settings_class,
create_router) and inherit `_make_interpreter` here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from screamingface.plugins.backend_api_base.plugin_base import BackendApiPluginBase

from .backend import AigwBackend
from .interpreter import AigwInterpreter

if TYPE_CHECKING:
    from fastapi import FastAPI


class AigwBackendApiPluginBase(BackendApiPluginBase):
    """Base class for every aigw_*_backend plugin."""

    tags: ClassVar[list[str]] = ["product:aigw"]
    depends: ClassVar[list[str]] = ["llm-base", "backend-api-base", "aigw-base"]
    conflicts: ClassVar[list[str]] = []

    def _make_interpreter(self, app: FastAPI):
        settings = self.settings  # type: ignore[assignment]
        backend = AigwBackend(
            gateway_url=settings.gateway_url,
            profile_name=settings.auth_profile,
        )
        return AigwInterpreter(app=app, settings=settings, backend=backend)
