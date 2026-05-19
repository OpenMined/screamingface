"""Unit + integration tests for the python_runner sandbox helper.

Integration tests are darwin-only and rely on /usr/bin/sandbox-exec.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from screamingface.plugins.python_runner.sandbox import (
    SANDBOX_PROFILE_PATH,
    build_subprocess_argv,
    sandbox_is_enabled,
)

darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="sandbox-exec is darwin-only")


# ---------- helper unit tests ---------------------------------------------


def test_profile_file_ships_with_package() -> None:
    assert SANDBOX_PROFILE_PATH.is_file()
    assert SANDBOX_PROFILE_PATH.name == "macos.sb"


def test_sandbox_is_enabled_default_true_on_darwin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert sandbox_is_enabled() is True


def test_sandbox_is_enabled_false_when_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__SANDBOX", "off")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert sandbox_is_enabled() is False


def test_sandbox_is_enabled_false_on_non_darwin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert sandbox_is_enabled() is False


def test_build_argv_wraps_on_darwin_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    script = tmp_path / "x.py"
    script.write_text("pass\n")

    argv = build_subprocess_argv(script)

    assert argv[0] == "sandbox-exec"
    assert "-f" in argv
    assert str(SANDBOX_PROFILE_PATH) in argv
    assert "-D" in argv
    assert any(a.startswith("SPEC_ROOT=") for a in argv)
    assert any(a.startswith("PY_PREFIX=") for a in argv)
    # Interpreter + script come after the sandbox-exec options.
    assert argv[-2] == sys.executable
    assert argv[-1] == str(script)


def test_build_argv_plain_when_sandbox_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__SANDBOX", "off")
    monkeypatch.setattr(sys, "platform", "darwin")
    script = tmp_path / "x.py"
    script.write_text("pass\n")
    assert build_subprocess_argv(script) == [sys.executable, str(script)]


def test_build_argv_plain_on_non_darwin_logs_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from screamingface.plugins.python_runner import sandbox as sandbox_mod

    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sandbox_mod, "_warned_unsupported", False)
    script = tmp_path / "x.py"
    script.write_text("pass\n")

    with caplog.at_level("WARNING", logger="screamingface.plugins.python_runner.sandbox"):
        argv = build_subprocess_argv(script)

    assert argv == [sys.executable, str(script)]
    assert any("unsandboxed" in r.message.lower() for r in caplog.records)


def test_build_argv_non_darwin_warning_is_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from screamingface.plugins.python_runner import sandbox as sandbox_mod

    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sandbox_mod, "_warned_unsupported", False)
    script = tmp_path / "x.py"
    script.write_text("pass\n")

    build_subprocess_argv(script)  # first call: warns and sets flag
    caplog.clear()

    with caplog.at_level("WARNING", logger="screamingface.plugins.python_runner.sandbox"):
        build_subprocess_argv(script)  # second call: should NOT warn again

    assert not any("unsandboxed" in r.message.lower() for r in caplog.records)
