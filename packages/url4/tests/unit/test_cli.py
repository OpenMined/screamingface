"""The `url4` CLI entry point (url4.cli).

STORY: `url4 --version` and `url4 eval` work on the base install (no serving extra);
`url4 serve` resolves config, warns on risky exposure, and hands the assembled ASGI
app to uvicorn — failing fast with clear exit codes (0 ok, 1 runtime, 2 usage/config).

These tests are synchronous: `url4 eval` owns its own event loop via evaluate_sync,
so the tests must not run inside one.
"""

from __future__ import annotations

import io

import pytest

import url4._serve as _serve
import url4.cli as cli
from url4 import __version__


def test_version_prints_and_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"url4 {__version__}"


def test_no_subcommand_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert exit_info.value.code == 2


def test_eval_from_argument(capsys) -> None:
    assert cli.main(["eval", "('a', 'b')!'join'"]) == 0
    assert "join" in capsys.readouterr().out


def test_eval_from_stdin(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("('x', 'y')!'merge'"))
    assert cli.main(["eval"]) == 0
    assert "merge" in capsys.readouterr().out


def test_eval_empty_is_usage_error(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("   "))
    assert cli.main(["eval"]) == 2
    assert "no expression" in capsys.readouterr().err


def test_eval_parse_error_is_runtime_error(capsys) -> None:
    assert cli.main(["eval", "(a::)!'x'"]) == 1
    assert "url4 eval:" in capsys.readouterr().err


def test_serve_wires_app_and_calls_uvicorn(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_forever(app, host, port) -> int:
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port
        return 0

    monkeypatch.setattr(_serve, "build_client", lambda _config: object())
    monkeypatch.setattr(cli, "_serve_forever", fake_forever)
    assert cli.main(["serve", "--port", "5001"]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 5001
    assert callable(captured["app"])
    assert "listening on http://127.0.0.1:5001" in capsys.readouterr().err


def test_serve_invalid_config_is_usage_error(capsys) -> None:
    assert cli.main(["serve", "--processor", "/absent"]) == 2
    assert "not a configured route" in capsys.readouterr().err


def test_serve_warns_on_non_loopback_bind(monkeypatch, capsys) -> None:
    monkeypatch.setattr(_serve, "build_client", lambda _config: object())
    monkeypatch.setattr(cli, "_serve_forever", lambda _app, _host, _port: 0)
    cli.main(["serve", "--host", "0.0.0.0"])
    assert "WARNING binding non-loopback" in capsys.readouterr().err


def test_serve_config_flag_warns_on_exposed_commands(monkeypatch, tmp_path, capsys) -> None:
    config_file = tmp_path / "url4.toml"
    config_file.write_text('[commands]\n"/py" = "python3 -"\n', encoding="utf-8")
    monkeypatch.setattr(_serve, "build_client", lambda _config: object())
    monkeypatch.setattr(cli, "_serve_forever", lambda _app, _host, _port: 0)
    assert cli.main(["serve", "--host", "0.0.0.0", "--config", str(config_file)]) == 0
    assert "command routes are enabled" in capsys.readouterr().err


def test_serve_forever_without_uvicorn_prints_hint(capsys) -> None:
    # The dev env has no uvicorn (the optional [server] extra) — the real missing
    # branch, exercised directly.
    assert cli._serve_forever(object(), "127.0.0.1", 4404) == 2
    assert "url4[server]" in capsys.readouterr().err
