"""Unit tests for aigw_runner — Popen and threading mocked."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from screamingface.plugins.aigw_runner.plugin import AigwRunnerPlugin, AigwRunnerSettings


@pytest.fixture
def fake_aigw_dir(tmp_path: Path) -> Path:
    """Create a directory that looks like apps/aigateway/ to satisfy preflight."""
    d = tmp_path / "aigateway"
    d.mkdir()
    (d / "pyproject.toml").write_text("[project]\nname='aigateway'\n")
    return d


def _make_plugin(fake_dir: Path, **overrides) -> AigwRunnerPlugin:
    plugin = AigwRunnerPlugin()
    settings_kwargs = {"aigateway_dir": str(fake_dir), **overrides}
    plugin.settings = AigwRunnerSettings(**settings_kwargs)  # type: ignore[assignment]
    return plugin


def test_preflight_succeeds_when_aigw_dir_exists(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)
    with patch("shutil.which", return_value="/usr/local/bin/uv"):
        ok, reason = plugin.preflight()
    assert ok, reason


def test_preflight_fails_when_aigw_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-aigateway"
    plugin = _make_plugin(missing)
    ok, reason = plugin.preflight()
    assert not ok
    assert "aigateway directory not found" in reason


def test_preflight_fails_without_uv(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)
    with patch("shutil.which", return_value=None):
        ok, reason = plugin.preflight()
    assert not ok
    assert "`uv` command not found" in reason


def test_preflight_skipped_when_disabled(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, enabled=False)
    ok, _ = plugin.preflight()
    assert ok


def test_setup_skipped_when_disabled(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, enabled=False)
    plugin.preflight()
    fake_app = MagicMock()
    fake_hooks = MagicMock()
    plugin.setup(fake_app, fake_hooks, MagicMock(), MagicMock())
    assert plugin._process is None
    fake_hooks.register.assert_not_called()


def test_setup_spawns_subprocess_and_registers_hooks(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)

    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None  # still running
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.__iter__.return_value = iter([])
    fake_proc.pid = 12345

    fake_hooks = MagicMock()
    fake_app = MagicMock()

    with (
        patch("shutil.which", return_value="/usr/local/bin/uv"),
        patch(
            "screamingface.plugins.aigw_runner.plugin.subprocess.Popen",
            return_value=fake_proc,
        ),
        patch("screamingface.plugins.aigw_runner.plugin.atexit.register") as mock_atexit,
        patch("screamingface.plugins.aigw_runner.plugin.threading.Thread") as mock_thread,
    ):
        plugin.preflight()
        plugin.setup(fake_app, fake_hooks, MagicMock(), MagicMock())

    assert plugin._process is fake_proc
    fake_hooks.register.assert_called_once()
    register_args = fake_hooks.register.call_args
    assert register_args.args[0] == "app.shutdown"
    mock_atexit.assert_called_once()
    mock_thread.assert_called_once()


def test_setup_raises_if_subprocess_exits_immediately(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)

    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = 1  # exited
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.read.return_value = "boom"
    fake_proc.pid = 12345

    with (
        patch("shutil.which", return_value="/usr/local/bin/uv"),
        patch(
            "screamingface.plugins.aigw_runner.plugin.subprocess.Popen",
            return_value=fake_proc,
        ),
    ):
        plugin.preflight()
        with pytest.raises(RuntimeError, match="exited immediately"):
            plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())


def test_stop_terminates_process(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.pid = 12345
    plugin._process = fake_proc

    plugin._stop()

    fake_proc.terminate.assert_called_once()
    fake_proc.wait.assert_called_once_with(timeout=5)
    assert plugin._process is None


def test_stop_kills_on_timeout(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.pid = 12345
    fake_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=5), None]
    plugin._process = fake_proc

    plugin._stop()

    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()
    assert plugin._process is None


def test_stop_is_noop_when_no_process(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)
    # _process starts as None
    plugin._stop()  # must not raise
