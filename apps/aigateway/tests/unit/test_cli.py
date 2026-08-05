"""`aigateway migrate` — the shared local, Docker, and Helm migration entry point.

FEATURE: local dev and plain-Docker runs of aigateway have no schema-bootstrap path outside
Helm's pre-install/pre-upgrade Job. Every environment now calls this command, so a fresh SQLite
DB stops failing with "no such table: credential_blobs" on first boot and migration configuration
cannot drift between launchers.
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from aigateway import cli


def test_migrate_runs_the_canonical_tortoise_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs == {"check": False}
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    cli.main(["migrate"])

    assert calls == [
        [sys.executable, "-m", "tortoise", "-c", "aigateway.db.TORTOISE_CONFIG", "migrate"]
    ]


def test_migrate_raises_on_a_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, returncode=1)

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["migrate"])
    assert exc_info.value.code == 1


def test_no_argv_serves_rather_than_migrating(monkeypatch: pytest.MonkeyPatch) -> None:
    serve = MagicMock()
    monkeypatch.setattr(cli, "_serve", serve)

    cli.main([])

    serve.assert_called_once()


def test_the_serve_subcommand_also_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    serve = MagicMock()
    monkeypatch.setattr(cli, "_serve", serve)

    cli.main(["serve"])

    serve.assert_called_once()
