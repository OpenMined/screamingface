"""Unit tests for aigw_runner — Popen and threading mocked."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
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


def test_preflight_uses_configured_uv_bin(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, uv_bin="/custom/uv")
    with patch("shutil.which", return_value=None):
        ok, reason = plugin.preflight()
    assert ok, reason
    assert plugin._uv_bin == "/custom/uv"


def test_optional_string_settings_have_defaults() -> None:
    settings = AigwRunnerSettings(
        aigateway_dir=cast(Any, None), database_path="", uv_bin=cast(Any, None)
    )

    assert settings.aigateway_dir == "../aigateway"
    assert settings.database_path == ".sf/aigateway.db"
    assert settings.uv_bin == "uv"


def test_settings_schema_hides_deprecated_controls() -> None:
    plugin = AigwRunnerPlugin()
    schema = plugin.customize_schema(AigwRunnerSettings.model_json_schema())
    props = schema["properties"]

    assert props["aigateway_dir"]["default"] == "../aigateway"
    assert props["database_path"]["default"] == ".sf/aigateway.db"
    assert props["uv_bin"]["default"] == "uv"
    assert "auth_enabled" not in props
    assert "enabled" not in props
    assert "port" not in props


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
    db_path = fake_aigw_dir / "aigateway.db"
    plugin = _make_plugin(fake_aigw_dir, database_path=str(db_path), uv_bin="/custom/uv")

    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None  # still running
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.__iter__.return_value = iter([])
    fake_proc.pid = 12345

    fake_hooks = MagicMock()
    fake_app = MagicMock()

    with (
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch(
            "screamingface.plugins.aigw_runner.plugin.subprocess.Popen",
            return_value=fake_proc,
        ) as mock_popen,
        patch("screamingface.plugins.aigw_runner.plugin._wait_for_health", return_value=True),
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=False),
        patch("screamingface.plugins.aigw_runner.plugin.atexit.register") as mock_atexit,
        patch("screamingface.plugins.aigw_runner.plugin.threading.Thread") as mock_thread,
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        plugin.preflight()
        plugin.setup(cast(Any, fake_app), fake_hooks, MagicMock(), MagicMock())

    assert plugin._process is fake_proc
    mock_run.assert_called_once()
    migrate_args = mock_run.call_args.args[0]
    assert migrate_args[:4] == ["/custom/uv", "run", "--directory", str(fake_aigw_dir.resolve())]
    migrate_env = mock_run.call_args.kwargs["env"]
    assert migrate_env["AIGATEWAY_DATABASE_URL"] == f"sqlite://{db_path.resolve()}"
    assert migrate_env["AIGATEWAY_AUTH_ENABLED"] == "false"
    assert "VIRTUAL_ENV" not in migrate_env
    mock_popen.assert_called_once()
    popen_args = mock_popen.call_args.args[0]
    assert popen_args[:4] == ["/custom/uv", "run", "--directory", str(fake_aigw_dir.resolve())]
    assert popen_args[popen_args.index("--host") + 1] == "127.0.0.1"
    assert mock_popen.call_args.kwargs["env"] is migrate_env
    fake_hooks.register.assert_called_once()
    register_args = fake_hooks.register.call_args
    assert register_args.args[0] == "app.shutdown"
    mock_atexit.assert_called_once()
    mock_thread.assert_called_once()


def test_setup_injects_aigw_env_into_gateway_subprocess(fake_aigw_dir: Path) -> None:
    """``aigw_env`` from plugin config must reach the aigateway subprocess.

    Real-world repro: the SF server is launched by the Electron desktop app,
    which strips the user's shell env. Without this config channel there is
    no way to configure AIGW_PROVIDER_MAX_CONCURRENCY (and friends) for the
    spawned gateway.
    """
    db_path = fake_aigw_dir / "aigateway.db"
    plugin = _make_plugin(
        fake_aigw_dir,
        database_path=str(db_path),
        uv_bin="/custom/uv",
        aigw_env={
            "AIGW_PROVIDER_MAX_CONCURRENCY": "1",
            "AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES": '{"gemini":1}',
        },
    )

    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.__iter__.return_value = iter([])
    fake_proc.pid = 12346

    with (
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch(
            "screamingface.plugins.aigw_runner.plugin.subprocess.Popen",
            return_value=fake_proc,
        ) as mock_popen,
        patch("screamingface.plugins.aigw_runner.plugin._wait_for_health", return_value=True),
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=False),
        patch("screamingface.plugins.aigw_runner.plugin.atexit.register"),
        patch("screamingface.plugins.aigw_runner.plugin.threading.Thread"),
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        plugin.preflight()
        plugin.setup(cast(Any, MagicMock()), MagicMock(), MagicMock(), MagicMock())

    env = mock_popen.call_args.kwargs["env"]
    assert env["AIGW_PROVIDER_MAX_CONCURRENCY"] == "1"
    assert env["AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES"] == '{"gemini":1}'
    # AIGATEWAY_* defaults still applied — aigw_env injects, doesn't replace.
    assert env["AIGATEWAY_AUTH_ENABLED"] == "false"


def test_setup_stops_stale_local_gateway_before_spawning(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, uv_bin="/custom/uv")
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.__iter__.return_value = iter([])
    fake_proc.pid = 12345

    with (
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=True),
        patch(
            "screamingface.plugins.aigw_runner.plugin._existing_local_gateway_status",
            return_value="local_no_auth",
        ) as mock_existing_status,
        patch(
            "screamingface.plugins.aigw_runner.plugin._terminate_processes_on_port",
            return_value=True,
        ) as mock_terminate,
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch(
            "screamingface.plugins.aigw_runner.plugin.subprocess.Popen",
            return_value=fake_proc,
        ) as mock_popen,
        patch("screamingface.plugins.aigw_runner.plugin._wait_for_health", return_value=True),
        patch("screamingface.plugins.aigw_runner.plugin.atexit.register"),
        patch("screamingface.plugins.aigw_runner.plugin.threading.Thread"),
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        plugin.preflight()
        plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    mock_existing_status.assert_called_once_with("http://127.0.0.1:9105")
    mock_terminate.assert_called_once_with(9105)
    mock_run.assert_called_once()
    mock_popen.assert_called_once()


def test_setup_raises_when_stale_local_gateway_cannot_be_stopped(
    fake_aigw_dir: Path,
) -> None:
    plugin = _make_plugin(fake_aigw_dir, uv_bin="/custom/uv")

    with (
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=True),
        patch(
            "screamingface.plugins.aigw_runner.plugin._existing_local_gateway_status",
            return_value="local_no_auth",
        ),
        patch(
            "screamingface.plugins.aigw_runner.plugin._terminate_processes_on_port",
            return_value=False,
        ),
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.Popen") as mock_popen,
    ):
        plugin.preflight()
        with pytest.raises(RuntimeError, match="could not stop"):
            plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_setup_raises_when_port_has_auth_enabled_aigateway(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, uv_bin="/custom/uv")

    with (
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=True),
        patch(
            "screamingface.plugins.aigw_runner.plugin._existing_local_gateway_status",
            return_value="auth_enabled",
        ),
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.Popen") as mock_popen,
    ):
        plugin.preflight()
        with pytest.raises(RuntimeError, match="auth-enabled AIGateway"):
            plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_setup_raises_when_port_has_non_gateway_service(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, uv_bin="/custom/uv")

    with (
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=True),
        patch(
            "screamingface.plugins.aigw_runner.plugin._existing_local_gateway_status",
            return_value="not_gateway",
        ),
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.Popen") as mock_popen,
    ):
        plugin.preflight()
        with pytest.raises(RuntimeError, match="does not look like"):
            plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_external_mode_does_not_run_migrations_or_spawn(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir, uv_bin="/custom/uv")
    fake_hooks = MagicMock()
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            config=SimpleNamespace(
                plugin_config={
                    "aigw-base": {
                        "mode": "external",
                        "gateway_url": "https://gateway.example.com",
                    }
                }
            ),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )

    with (
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.Popen") as mock_popen,
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open") as mock_is_port_open,
    ):
        plugin.setup(cast(Any, fake_app), fake_hooks, MagicMock(), MagicMock())

    mock_run.assert_not_called()
    mock_popen.assert_not_called()
    mock_is_port_open.assert_not_called()
    fake_hooks.register.assert_not_called()
    assert plugin._process is None


def test_setup_raises_if_subprocess_exits_immediately(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)

    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = 1  # exited
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.read.return_value = "boom"
    fake_proc.pid = 12345

    with (
        patch("shutil.which", return_value="/usr/local/bin/uv"),
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch(
            "screamingface.plugins.aigw_runner.plugin.subprocess.Popen",
            return_value=fake_proc,
        ),
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=False),
        patch("screamingface.plugins.aigw_runner.plugin._wait_for_health", return_value=False),
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        plugin.preflight()
        with pytest.raises(RuntimeError, match="exited immediately"):
            plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())


def test_setup_raises_when_migrations_fail(fake_aigw_dir: Path) -> None:
    plugin = _make_plugin(fake_aigw_dir)

    with (
        patch("shutil.which", return_value="/usr/local/bin/uv"),
        patch("screamingface.plugins.aigw_runner.plugin._is_port_open", return_value=False),
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.run") as mock_run,
        patch("screamingface.plugins.aigw_runner.plugin.subprocess.Popen") as mock_popen,
    ):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "boom"
        plugin.preflight()
        with pytest.raises(RuntimeError, match="gateway migrations failed"):
            plugin.setup(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    mock_popen.assert_not_called()


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
