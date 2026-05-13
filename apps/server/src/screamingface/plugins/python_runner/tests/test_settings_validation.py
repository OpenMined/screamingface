"""Script-name validator rejects non-identifiers (DEMO-009 acceptance)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from screamingface.plugins.python_runner.plugin import PythonRunnerSettings


@pytest.mark.parametrize("name", ["foo", "foo_bar", "_x1", "X", "snake_case_123"])
def test_valid_names_accepted(name: str) -> None:
    settings = PythonRunnerSettings(scripts={name: "x = 1\n"})
    assert name in settings.scripts


@pytest.mark.parametrize("name", ["foo bar", "123abc", "x-y", "foo.py", "", "with space"])
def test_invalid_names_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="Invalid script name"):
        PythonRunnerSettings(scripts={name: "x = 1\n"})
