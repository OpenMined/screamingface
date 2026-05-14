"""Tests for python_runner.runner — error type + cache helper."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    _cache_script,
    run_script_source,
)


def test_error_str_includes_kind_and_message() -> None:
    err = PythonRunnerError(kind="timeout", message="boom")
    assert str(err) == "PythonRunnerError(timeout): boom"


def test_error_carries_optional_fields() -> None:
    err = PythonRunnerError(
        kind="nonzero_exit",
        message="bad",
        stdout="out",
        stderr="err",
        exit_code=7,
    )
    assert err.stdout == "out"
    assert err.stderr == "err"
    assert err.exit_code == 7


def test_cache_script_writes_and_returns_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    p = _cache_script("print(1)\n")
    assert p.parent == tmp_path
    assert p.suffix == ".py"
    assert p.read_text() == "print(1)\n"


def test_cache_script_same_source_same_path_no_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    p1 = _cache_script("print(1)\n")
    mtime1 = p1.stat().st_mtime_ns
    p2 = _cache_script("print(1)\n")
    assert p1 == p2
    assert p2.stat().st_mtime_ns == mtime1


def test_cache_script_different_sources_different_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    p1 = _cache_script("print(1)\n")
    p2 = _cache_script("print(2)\n")
    assert p1 != p2


def test_cache_dir_and_file_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "nested" / "cache"
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(cache_root))
    p = _cache_script("print('x')\n")
    assert (cache_root.stat().st_mode & 0o777) == 0o700
    assert (p.stat().st_mode & 0o777) == 0o600


_ECHO_SCRIPT = textwrap.dedent(
    """\
    import json, sys
    data = json.load(sys.stdin)
    print(json.dumps({"ok": True, "got": data}))
    """
)


async def test_happy_path_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    result = await run_script_source(_ECHO_SCRIPT, {"a": 1, "b": [2, 3]})
    assert result == {"ok": True, "got": {"a": 1, "b": [2, 3]}}


async def test_stderr_logged_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = textwrap.dedent(
        """\
        import json, sys
        print("warn:something", file=sys.stderr)
        print(json.dumps({"ok": True}))
        """
    )
    with caplog.at_level(logging.DEBUG, logger="screamingface.plugins.python_runner.runner"):
        result = await run_script_source(script, {})
    assert result == {"ok": True}
    assert any("warn:something" in rec.message for rec in caplog.records)


async def test_nonzero_exit_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = textwrap.dedent(
        """\
        import sys
        print("error happened", file=sys.stderr)
        sys.exit(1)
        """
    )
    with pytest.raises(PythonRunnerError) as ei:
        await run_script_source(script, {})
    assert ei.value.kind == "nonzero_exit"
    assert ei.value.exit_code == 1
    assert "error happened" in ei.value.stderr


async def test_invalid_output_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = "print('not json')\n"
    with pytest.raises(PythonRunnerError) as ei:
        await run_script_source(script, {})
    assert ei.value.kind == "invalid_output"
    assert "not json" in ei.value.stdout


async def test_timeout_raises_and_kills_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = textwrap.dedent(
        """\
        import time
        time.sleep(5)
        """
    )
    with pytest.raises(PythonRunnerError) as ei:
        await run_script_source(script, {}, timeout=0.5)
    assert ei.value.kind == "timeout"
