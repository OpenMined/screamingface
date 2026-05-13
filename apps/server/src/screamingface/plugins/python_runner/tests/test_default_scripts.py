"""``load_vendored_defaults`` reads ``_vendored/*.py`` (DEMO-009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from screamingface.plugins.python_runner import _default_scripts
from screamingface.plugins.python_runner._default_scripts import load_vendored_defaults


def test_returns_empty_dict_when_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_default_scripts, "VENDOR_ROOT", tmp_path / "does_not_exist")
    assert load_vendored_defaults() == {}


def test_returns_empty_dict_when_dir_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_default_scripts, "VENDOR_ROOT", tmp_path)
    assert load_vendored_defaults() == {}


def test_loads_py_files_keyed_by_stem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bar_baz.py").write_text("X = 42\n", encoding="utf-8")
    monkeypatch.setattr(_default_scripts, "VENDOR_ROOT", tmp_path)

    result = load_vendored_defaults()

    assert result == {
        "foo": "def foo():\n    return 1\n",
        "bar_baz": "X = 42\n",
    }


def test_ignores_non_py_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "keep.py").write_text("Y = 1\n", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not python\n", encoding="utf-8")
    monkeypatch.setattr(_default_scripts, "VENDOR_ROOT", tmp_path)

    assert load_vendored_defaults() == {"keep": "Y = 1\n"}
