"""python-runner plugin — scaffold (DEMO-009 / SF-156).

Registers the ``/python`` URL4 backend dispatch path and exposes a
``scripts: dict[str, str]`` settings field — Python source as config, edited
via the SF settings UI and persisted to ``sf.json``. No execution logic
yet; that lands in DEMO-010 / DEMO-012 / DEMO-013.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING

import httpx
from fastapi import HTTPException
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.eval_runs._hook_payloads import HOOK_QUESTION_CHECKED
from screamingface.plugins.python_runner._default_scripts import load_vendored_defaults
from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    _script_defines_main,
    run_script_main,
    run_script_source,
)
from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
from screamingface.plugins.url4_executor.url4_resolve import (
    _fetch_relative,
    _fetch_url,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry
    from screamingface.plugins.url4_executor.scope import Env


logger = logging.getLogger(__name__)

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
    # Executes scripts; no credentials and no /health route, so it must be
    # excluded from the /backends/status credential walk (SF-246).
    requires_auth: bool = False

    async def handle_backend_call(
        self,
        intent: str,
        *,
        sources: str = "",
        app: FastAPI,
        env: Env | None = None,
    ) -> str:
        """Fetch the script at ``sources``, run it sandboxed, return JSON.

        ``sources`` is the source URL (relative ``/data/code/<name>.py`` or
        absolute ``http(s)://...``). ``intent`` is the JSON payload that the
        script reads from stdin; an empty string means an empty dict.
        """
        with traced("python.handle_backend_call", kind="internal"):
            set_span_attrs({"python.source_url": sources[:500]})

            try:
                if sources.startswith(("http://", "https://")):
                    source = await _fetch_url(sources)
                elif sources.startswith("/"):
                    source = await _fetch_relative(app, sources)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "kind": "io_error",
                            "message": f"Unsupported source URL scheme: {sources!r}",
                        },
                    )
            except HTTPException:
                raise
            except httpx.HTTPError as e:
                logger.warning("python-runner fetch failed for %s: %s", sources, e)
                raise HTTPException(
                    status_code=400,
                    detail={
                        "kind": "io_error",
                        "message": f"Failed to fetch source {sources!r}: {e}",
                    },
                ) from e

            try:
                payload = json.loads(intent) if intent else {}
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "kind": "io_error",
                        "message": f"intent is not valid JSON: {e}",
                    },
                ) from e

            t0 = time.monotonic()
            try:
                if _script_defines_main(source):
                    result = await run_script_main(source, payload)
                else:
                    result = await run_script_source(source, payload)
            except PythonRunnerError as e:
                duration_ms = int((time.monotonic() - t0) * 1000)
                set_span_attrs(
                    {
                        "python.duration_ms": duration_ms,
                        "python.exit_code": e.exit_code or -1,
                        "python.error_kind": e.kind,
                    }
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "kind": e.kind,
                        "message": e.message,
                        "stderr": e.stderr,
                    },
                ) from e

            duration_ms = int((time.monotonic() - t0) * 1000)
            set_span_attrs({"python.duration_ms": duration_ms})

            # eval-runs integration: emit question.checked when this run has
            # a __run_id__ in env AND the script is a check_correct.py-shaped
            # invocation. Other scripts and untagged calls don't touch the
            # eval pipeline.
            run_id: str | None = None
            if env is not None:
                try:
                    looked_up = env.lookup("__run_id__")
                    if isinstance(looked_up, str):
                        run_id = looked_up
                except KeyError:
                    run_id = None

            if run_id is not None and sources.endswith("/check_correct.py"):
                question = ""
                expected = ""
                try:
                    payload_obj = json.loads(intent) if intent else {}
                    if isinstance(payload_obj, dict):
                        question = str(payload_obj.get("question", ""))
                        expected = str(payload_obj.get("expected", ""))
                except (json.JSONDecodeError, TypeError):
                    pass

                if isinstance(result, dict):
                    result_dict: dict = result
                else:
                    result_dict = {}

                await app.state.hooks.emit_async(
                    HOOK_QUESTION_CHECKED,
                    run_id=run_id,
                    question=question,
                    expected=expected,
                    predicted=result_dict.get("predicted"),
                    correct=result_dict.get("correct"),
                    raw_output=result_dict.get("raw_output"),
                    error=None,
                )

            return json.dumps(result)

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
