"""Plugin class declares the right surface (DEMO-009 acceptance criteria)."""

from __future__ import annotations

from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)


def test_plugin_class_imports() -> None:
    assert PythonRunnerPlugin is not None


def test_plugin_metadata() -> None:
    assert PythonRunnerPlugin.name == "python-runner"
    assert PythonRunnerPlugin.backend_call_paths == ["/python"]
    assert PythonRunnerPlugin.settings_class is PythonRunnerSettings
    assert "product:python" in PythonRunnerPlugin.tags


def test_settings_schema_has_x_code_editor() -> None:
    schema = PythonRunnerSettings.model_json_schema()
    scripts_field = schema["properties"]["scripts"]
    assert scripts_field.get("x-code-editor") == {"language": "python"}
