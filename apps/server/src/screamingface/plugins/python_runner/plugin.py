"""python-runner plugin — scaffold (DEMO-009 / SF-156).

Registers the ``/python`` URL4 backend dispatch path and exposes a
``scripts: dict[str, str]`` settings field — Python source as config, edited
via the SF settings UI and persisted to ``sf.json``. No execution logic
yet; that lands in DEMO-010 / DEMO-012 / DEMO-013.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.python_runner._default_scripts import load_vendored_defaults

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


VALID_SCRIPT_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PythonRunnerSettings(PluginSettings):
    """Settings for the python-runner plugin.

    Scripts are Python source strings keyed by a Python-identifier-safe name.
    The ``x-code-editor`` JSON Schema annotation tells the SF settings UI
    (DEMO-030) to render values in a Monaco editor configured for Python.
    """

    model_config = SettingsConfigDict(
        env_prefix="SF_PYTHON_RUNNER__",
        env_nested_delimiter="__",
    )

    scripts: dict[str, str] = Field(
        default_factory=load_vendored_defaults,
        description=(
            "Named Python scripts servable at /data/code/<name>.py. "
            "Edit through the settings UI; persisted to sf.json."
        ),
        json_schema_extra={
            "x-code-editor": {"language": "python"},
        },
    )

    @field_validator("scripts")
    @classmethod
    def _validate_script_names(cls, v: dict[str, str]) -> dict[str, str]:
        for name in v:
            if not VALID_SCRIPT_NAME.match(name):
                raise ValueError(
                    f"Invalid script name {name!r}: must match {VALID_SCRIPT_NAME.pattern}"
                )
        return v


class PythonRunnerPlugin(Plugin):
    """Plugin scaffold. Execution lands in DEMO-013."""

    name = "python-runner"
    description = "Runs Python scripts referenced by URL4 expressions."
    tags: list[str] = ["product:python"]
    depends: list[str] = []
    conflicts: list[str] = []
    settings_class = PythonRunnerSettings
    backend_call_paths: list[str] = ["/python"]

    async def handle_backend_call(
        self,
        intent: str,
        *,
        sources: str = "",
        app: FastAPI,
    ) -> str:
        del intent, sources, app  # consumed by DEMO-013
        raise NotImplementedError("Wired in DEMO-013")

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        from screamingface.plugins.python_runner.routes import create_router

        del hooks, classes  # required by Plugin contract; unused here
        routes.add_router(self.name, create_router(app), prefix="")
