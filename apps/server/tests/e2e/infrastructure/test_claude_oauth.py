"""Unit tests for has_claude_code_oauth — purely tests the subprocess path."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth


def test_returns_true_when_security_returncode_zero(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=b"x"),
    ):
        assert has_claude_code_oauth() is True


def test_returns_false_when_security_missing(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value=None):
        assert has_claude_code_oauth() is False


def test_returns_false_when_user_unset(monkeypatch) -> None:
    monkeypatch.delenv("USER", raising=False)
    with patch("shutil.which", return_value="/usr/bin/security"):
        assert has_claude_code_oauth() is False


def test_returns_false_on_timeout(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="security", timeout=3)
    ):
        assert has_claude_code_oauth() is False


def test_conftest_uses_keychain_probe(monkeypatch) -> None:
    """The e2e_live skip reason must reference OAuth, not ANTHROPIC_API_KEY."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-ignored")
    from unittest.mock import patch as _patch

    with _patch(
        "tests.e2e.infrastructure.claude_oauth.has_claude_code_oauth", return_value=False
    ):
        from tests.e2e import conftest as ce2e
        import inspect
        src = inspect.getsource(ce2e.pytest_collection_modifyitems)
        assert "ANTHROPIC_API_KEY" not in src
        assert "Claude Code" in src or "has_claude_code_oauth" in src
