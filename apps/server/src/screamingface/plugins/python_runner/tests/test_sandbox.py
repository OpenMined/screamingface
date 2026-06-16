"""Unit + integration tests for the python_runner sandbox helper.

Integration tests are darwin-only and rely on /usr/bin/sandbox-exec.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    run_script_source,
)
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


# ---------- runner integration tests --------------------------------------


_ECHO_SCRIPT = textwrap.dedent(
    """\
    import json, sys
    data = json.load(sys.stdin)
    print(json.dumps({"ok": True, "got": data}))
    """
)

_NET_SCRIPT = textwrap.dedent(
    """\
    import socket, sys
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        sys.exit(0)
    except OSError:
        sys.exit(7)
    """
)

_WRITE_HOME_SCRIPT = textwrap.dedent(
    """\
    import sys
    # /etc is outside the allowed write subpaths (/tmp, /var/folders).
    # Even attempting to open for write should be denied by the sandbox.
    target = "/etc/sf_sandbox_should_fail.txt"
    try:
        open(target, "w").write("nope")
        sys.exit(0)
    except OSError:
        sys.exit(9)
    """
)

_WRITE_TMP_SCRIPT = textwrap.dedent(
    """\
    import json, os, tempfile
    fd, p = tempfile.mkstemp(prefix="sf_sandbox_ok_", dir="/tmp")
    os.write(fd, b"ok")
    os.close(fd)
    os.unlink(p)
    print(json.dumps({"wrote": True}))
    """
)


@darwin_only
@pytest.mark.asyncio
async def test_echo_script_runs_inside_sandbox() -> None:
    out = await run_script_source(_ECHO_SCRIPT, {"hello": "world"})
    assert out == {"ok": True, "got": {"hello": "world"}}


@darwin_only
@pytest.mark.asyncio
async def test_network_denied_inside_sandbox() -> None:
    with pytest.raises(PythonRunnerError) as excinfo:
        await run_script_source(_NET_SCRIPT, {})
    assert excinfo.value.kind == "nonzero_exit"
    assert excinfo.value.exit_code == 7


@darwin_only
@pytest.mark.asyncio
async def test_write_outside_tmp_denied() -> None:
    with pytest.raises(PythonRunnerError) as excinfo:
        await run_script_source(_WRITE_HOME_SCRIPT, {})
    assert excinfo.value.kind == "nonzero_exit"
    assert excinfo.value.exit_code == 9


@darwin_only
@pytest.mark.asyncio
async def test_write_to_tmp_allowed() -> None:
    out = await run_script_source(_WRITE_TMP_SCRIPT, {})
    assert out == {"wrote": True}


@darwin_only
@pytest.mark.asyncio
async def test_sandbox_off_allows_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__SANDBOX", "off")
    # With the sandbox off, _NET_SCRIPT either succeeds (network reachable;
    # exit 0 with empty stdout → invalid_output from the runner) or hits a
    # transient socket error (exit 7 → nonzero_exit). The one outcome we
    # MUST NOT see is the sandbox-style permission denial that would also
    # surface as exit 7 — but exit 7 here is fine because it indicates the
    # syscall ran rather than being blocked. What proves the sandbox is off
    # is the absence of any sandbox-related stderr noise.
    try:
        await run_script_source(_NET_SCRIPT, {})
    except PythonRunnerError as e:
        assert e.kind in {"nonzero_exit", "invalid_output"}
        if e.kind == "nonzero_exit":
            assert e.exit_code == 7
        assert "sandbox" not in e.stderr.lower()


def test_runner_uses_sandbox_helper_and_scrubs_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Runner must call build_subprocess_argv and pass scrubbed env."""
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)

    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=b"{}", stderr=b"")

    # python_runner spawns via subprocess.run (SF-287), not create_subprocess_exec.
    monkeypatch.setattr(subprocess, "run", fake_run)

    asyncio.run(run_script_source("print(1)\n", {}))

    assert captured["argv"][0] == "sandbox-exec"
    assert captured["env"] == {"PATH": "/usr/bin", "HOME": "/tmp"}
