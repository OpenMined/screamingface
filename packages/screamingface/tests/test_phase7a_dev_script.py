from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "apps" / "screamingface-engine" / "dev.sh"


def _run(tmp_path: Path, *arguments: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    docker = binary_dir / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_CALLS"\n')
    docker.chmod(0o755)
    calls = tmp_path / "docker-calls.txt"
    environment = {
        **os.environ,
        "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}",
        "DOCKER_CALLS": str(calls),
    }
    completed = subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    recorded = calls.read_text().splitlines() if calls.exists() else []
    return completed, recorded


@pytest.mark.parametrize("arguments", [(), ("start",)])
def test_start_is_detached_built_and_health_gated(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    completed, calls = _run(tmp_path, *arguments)

    assert completed.returncode == 0
    assert calls == ["compose up --build --detach --wait --wait-timeout 180"]


def test_restart_recreates_only_this_project_then_waits_for_health(tmp_path: Path) -> None:
    completed, calls = _run(tmp_path, "restart")

    assert completed.returncode == 0
    assert calls == [
        "compose down --remove-orphans",
        "compose up --build --detach --wait --wait-timeout 180",
    ]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("down", "compose down --remove-orphans"),
        ("status", "compose ps"),
        ("logs", "compose logs --follow --tail 100"),
    ],
)
def test_management_commands_are_explicit_and_non_destructive(
    tmp_path: Path,
    command: str,
    expected: str,
) -> None:
    completed, calls = _run(tmp_path, command)

    assert completed.returncode == 0
    assert calls == [expected]
    # INVARIANT: Ordinary lifecycle operations never erase the encrypted connection volume.
    assert "--volumes" not in expected.split()
    assert "-v" not in expected.split()


def test_unknown_command_fails_before_docker_with_actionable_usage(tmp_path: Path) -> None:
    completed, calls = _run(tmp_path, "restarts")

    assert completed.returncode == 2
    assert calls == []
    assert "Usage:" in completed.stderr
    assert "start|restart|down|status|logs" in completed.stderr
