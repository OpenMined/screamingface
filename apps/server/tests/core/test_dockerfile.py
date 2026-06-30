"""Tests for the server container contract."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from screamingface.cli.main import app


def _json_instruction(name: str) -> list[str]:
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    prefix = f"{name} "
    for line in dockerfile.read_text().splitlines():
        if line.startswith(prefix):
            value = json.loads(line.removeprefix(prefix))
            assert isinstance(value, list)
            assert all(isinstance(item, str) for item in value)
            return value
    raise AssertionError(f"Dockerfile is missing {name}")


def test_runtime_command_invokes_registered_sf_command() -> None:
    entrypoint = _json_instruction("ENTRYPOINT")
    command = _json_instruction("CMD")

    assert entrypoint == ["sf"]

    result = CliRunner().invoke(app, [*command, "--help"])

    assert result.exit_code == 0, result.output
