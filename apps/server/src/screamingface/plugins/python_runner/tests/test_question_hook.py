"""Tests for python-runner emitting eval.question.checked (SF-165)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI

from screamingface.core.hooks import HookRegistry
from screamingface.plugins.eval_runs._hook_payloads import HOOK_QUESTION_CHECKED
from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)
from screamingface.plugins.python_runner.routes import create_router
from screamingface.plugins.url4_executor.scope import Env

CHECK_CORRECT_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({
    "question": data.get("question", ""),
    "expected": data.get("expected", ""),
    "predicted": data.get("predicted", ""),
    "correct": data.get("predicted") == data.get("expected"),
    "raw_output": data.get("predicted", ""),
}))
"""

ECHO_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"got": data}))
"""


def _make_app(scripts: dict[str, str]) -> FastAPI:
    app = FastAPI()
    plugin = PythonRunnerPlugin()
    plugin.settings = PythonRunnerSettings(scripts=scripts)

    class _Registry:
        active_plugins = {"python-runner": plugin}

    app.state.plugins = _Registry()
    app.state.hooks = HookRegistry()
    app.include_router(create_router(app))
    return app


@pytest.mark.asyncio
async def test_check_correct_invocation_with_run_id_emits_question_checked() -> None:
    app = _make_app({"check_correct": CHECK_CORRECT_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    fired: list[dict] = []
    app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )

    payload = {"question": "2+2", "expected": "4", "predicted": "4"}
    env = Env.root().child(__run_id__="abc", __run_spec__="hle")

    await plugin.handle_backend_call(
        json.dumps(payload),
        sources="/data/code/check_correct.py",
        app=app,
        env=env,
    )

    assert len(fired) == 1
    ev = fired[0]
    assert ev["run_id"] == "abc"
    assert ev["question"] == "2+2"
    assert ev["expected"] == "4"
    assert ev["predicted"] == "4"
    assert ev["correct"] is True
    assert ev["error"] is None


@pytest.mark.asyncio
async def test_check_correct_without_run_id_does_not_emit() -> None:
    app = _make_app({"check_correct": CHECK_CORRECT_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    fired: list[dict] = []
    app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )

    await plugin.handle_backend_call(
        json.dumps({"question": "q", "expected": "e", "predicted": "p"}),
        sources="/data/code/check_correct.py",
        app=app,
        env=None,
    )

    assert fired == []


@pytest.mark.asyncio
async def test_non_check_correct_script_with_run_id_does_not_emit() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    fired: list[dict] = []
    app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )

    env = Env.root().child(__run_id__="abc", __run_spec__="hle")
    await plugin.handle_backend_call(
        json.dumps({"x": 1}),
        sources="/data/code/echo.py",
        app=app,
        env=env,
    )

    assert fired == []
