"""Tests for python_runner.runner — error type + cache helper."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    _cache_script,
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


def test_cache_dir_and_file_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / "nested" / "cache"
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(cache_root))
    p = _cache_script("print('x')\n")
    assert (cache_root.stat().st_mode & 0o777) == 0o700
    assert (p.stat().st_mode & 0o777) == 0o600
