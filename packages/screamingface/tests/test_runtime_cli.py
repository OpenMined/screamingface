from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from screamingface._runtime import cli, runtime_logging
from screamingface._runtime.bootstrap import enable_local_providers, scoreboard_seed_json
from screamingface._runtime.config import RuntimeConfig


def test_parser_exposes_public_commands() -> None:
    parser = cli._parser()

    for command in ("up", "down", "restart", "status", "logs", "prepare", "doctor"):
        assert parser.parse_args([command]).command == command


def test_data_dir_is_accepted_before_or_after_the_command(tmp_path: Path) -> None:
    parser = cli._parser()

    assert parser.parse_args(["--data-dir", str(tmp_path), "up"]).data_dir == tmp_path
    assert parser.parse_args(["up", "--data-dir", str(tmp_path)]).data_dir == tmp_path


def test_runtime_data_is_user_scoped(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    assert config.state_path == tmp_path / "runtime.json"
    assert config.log_path == tmp_path / "runtime.log"
    assert config.assets_dir == tmp_path / "benchmark-assets"


def test_runtime_ports_are_configurable_and_unique(tmp_path: Path) -> None:
    config = RuntimeConfig(
        data_dir=tmp_path, gateway_port=19105, scoreboard_port=19106, engine_port=19108
    )

    assert config.services == {
        "gateway": "http://127.0.0.1:19105",
        "scoreboard": "http://127.0.0.1:19106",
        "engine": "http://127.0.0.1:19108",
    }
    with pytest.raises(ValueError, match="unique"):
        RuntimeConfig(data_dir=tmp_path, gateway_port=19105, scoreboard_port=19105)


def test_port_configuration_prefers_flags_then_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCREAMINGFACE_GATEWAY_PORT", "18105")
    args = cli._parser().parse_args(["--data-dir", str(tmp_path), "up", "--gateway-port", "19105"])

    config = cli._config(args)

    assert config.gateway_port == 19105
    assert config.scoreboard_port == 9106


def test_owned_state_is_removed_but_foreign_state_is_preserved(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)
    config.state_path.write_text(json.dumps({"pid": 42, "owner_token": "ours"}))

    cli._remove_owned_state(config, "theirs")
    assert config.state_path.exists()
    cli._remove_owned_state(config, "ours")
    assert not config.state_path.exists()


def test_state_is_written_atomically_with_private_permissions(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    cli._write_state(config, {"pid": 42, "owner_token": "secret"})

    assert json.loads(config.state_path.read_text()) == {"pid": 42, "owner_token": "secret"}
    if os.name != "nt":
        assert config.state_path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_control_endpoint_proves_identity_and_accepts_authenticated_shutdown() -> None:
    stopped = threading.Event()
    server = cli._control_server("ours", stopped)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    state: dict[str, object] = {
        "pid": os.getpid(),
        "owner_token": "ours",
        "control_url": f"http://127.0.0.1:{server.server_port}",
    }
    try:
        assert cli._verify_owner(state)
        foreign = dict(state)
        foreign["owner_token"] = "theirs"
        assert not cli._verify_owner(foreign)
        cli._request_shutdown(state)
        assert stopped.wait(1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_json_status_is_stable_and_redacts_the_owner_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = RuntimeConfig(data_dir=tmp_path)
    state = {
        "schema_version": 1,
        "pid": 42,
        "started_at": "now",
        "owner_token": "secret",
        "services": config.services,
    }
    cli._write_state(config, state)
    monkeypatch.setattr(cli, "_verify_owner", lambda _state: True)
    monkeypatch.setattr(cli, "_health", lambda services: dict.fromkeys(services, True))

    assert cli._print_status(config, json_output=True) == 0

    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output)["schema"] == "screamingface.runtime-status.v1"


def test_logs_rejects_negative_tail(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    with pytest.raises(RuntimeError, match="zero or greater"):
        cli._logs(config, tail=-1, follow=False)


def test_runtime_log_prefixes_services_and_rotates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "runtime.log"
    monkeypatch.setattr(runtime_logging, "MAX_LOG_BYTES", 100)
    monkeypatch.setattr(runtime_logging, "LOG_BACKUPS", 2)
    log = runtime_logging.RuntimeLog(path)

    with runtime_logging.log_service("engine"):
        log.write("first engine line\n")
        log.write("x" * 100 + "\n")
    with runtime_logging.log_service("gateway"):
        log.write("gateway line\n")
    log.close()

    rendered = "".join(candidate.read_text() for candidate in cli._log_paths(path))
    assert "[engine] first engine line" in rendered
    assert "[gateway] gateway line" in rendered
    assert path.with_name("runtime.log.1").exists()


def test_logs_filter_by_service(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = RuntimeConfig(data_dir=tmp_path)
    config.log_path.write_text("time [engine] one\ntime [gateway] two\n")

    cli._logs(config, tail=10, follow=False, service="engine")

    assert capsys.readouterr().out == "time [engine] one\n"


def test_benchmark_manifest_distinguishes_prepared_stale_and_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = RuntimeConfig(data_dir=tmp_path)
    destination = config.assets_dir / "draco"
    destination.mkdir(parents=True)
    monkeypatch.setattr(cli, "_benchmark_fingerprint", lambda _name: "draco:revision")

    assert cli._benchmark_status(config, "draco") == "incomplete"
    for relative in ("criteria", "rubrics"):
        (destination / relative).mkdir()
    (destination / "cases.json").write_text('[{"id":1}]')
    cli._write_json_atomic(
        cli._benchmark_manifest_path(destination),
        {"fingerprint": "draco:old"},
    )
    assert cli._benchmark_status(config, "draco") == "stale"
    cli._write_json_atomic(
        cli._benchmark_manifest_path(destination),
        {"fingerprint": "draco:revision"},
    )
    assert cli._benchmark_status(config, "draco") == "prepared"


def test_prepare_list_rejects_mutating_options(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    with pytest.raises(RuntimeError, match="cannot be combined"):
        cli._prepare(
            config,
            "draco",
            all_benchmarks=False,
            list_benchmarks=True,
            force=False,
        )


def test_plain_sdk_import_does_not_load_server_packages() -> None:
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import sys, screamingface; "
            "print(any(name in sys.modules "
            "for name in ('uvicorn', 'aigateway', 'screamingface_engine')))",
        ],
        text=True,
    )

    assert output.strip() == "False"


def test_local_runtime_enables_openrouter_without_overriding_an_explicit_choice() -> None:
    default_environment: dict[str, str] = {}
    disabled_environment = {"AIGW_OPENROUTER_ENABLED": "false"}

    enable_local_providers(default_environment)
    enable_local_providers(disabled_environment)

    assert default_environment == {"AIGW_OPENROUTER_ENABLED": "true"}
    assert disabled_environment == {"AIGW_OPENROUTER_ENABLED": "false"}


def test_scoreboard_seed_is_derived_from_engine_benchmark_identity() -> None:
    class Benchmark:
        id = "ifeval"
        title = "IFEval"
        description = "Deterministic instruction following"
        revision = "revision-from-engine"

    assert json.loads(scoreboard_seed_json([Benchmark()])) == [
        {
            "id": "ifeval",
            "display_name": "IFEval",
            "description": "Deterministic instruction following",
            "revision": "revision-from-engine",
        }
    ]
