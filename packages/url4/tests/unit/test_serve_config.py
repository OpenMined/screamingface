"""ServeConfig resolution + validation for `url4 serve` (url4._serve).

STORY: as an operator I configure the node via flags, URL4_* env, and url4.toml —
flags win, then env, then toml, then defaults — and unusable settings fail fast
before the server binds, not mid-request.
"""

from __future__ import annotations

import pytest

from url4._serve import DEFAULT_ROUTES, ConfigError, ServeConfig, resolve


def test_defaults_when_nothing_supplied() -> None:
    config = resolve({}, {}, None)
    assert config.host == "127.0.0.1"
    assert config.port == 4404
    assert config.processor == "/claude"
    assert dict(config.routes) == DEFAULT_ROUTES
    assert dict(config.commands) == {}


def test_flag_beats_env_beats_toml(tmp_path) -> None:
    toml = tmp_path / "url4.toml"
    toml.write_text('host = "toml-host"\nport = 1\n', encoding="utf-8")
    env = {"URL4_HOST": "env-host", "URL4_PORT": "2"}
    config = resolve({"host": "flag-host", "port": None}, env, toml)
    assert config.host == "flag-host"  # flag wins
    assert config.port == 2  # no flag -> env wins over toml


def test_env_typed_coercion_and_bad_value() -> None:
    assert resolve({}, {"URL4_CONCURRENCY": "7"}, None).concurrency == 7
    with pytest.raises(ConfigError, match="concurrency must be an integer"):
        resolve({}, {"URL4_CONCURRENCY": "not-an-int"}, None)


def test_routes_merge_defaults_then_toml_then_flags(tmp_path) -> None:
    toml = tmp_path / "url4.toml"
    toml.write_text('[routes]\n"/gemini" = "gemini/custom"\n', encoding="utf-8")
    config = resolve({"routes": ["/claude=claude/override"]}, {}, toml)
    assert config.routes["/claude"] == "claude/override"  # flag
    assert config.routes["/gemini"] == "gemini/custom"  # toml
    assert config.routes["/codex"] == DEFAULT_ROUTES["/codex"]  # default survives


def test_bad_route_flag_format() -> None:
    with pytest.raises(ConfigError, match="PATH=MODEL"):
        resolve({"routes": ["no-equals-sign"]}, {}, None)


def test_bad_float_and_command_type(tmp_path) -> None:
    with pytest.raises(ConfigError, match="timeout must be a number"):
        resolve({"timeout": "not-a-number"}, {}, None)
    toml = tmp_path / "c.toml"
    toml.write_text('[commands]\n"/x" = 5\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="command must be a string or list"):
        resolve({}, {}, toml)


def test_commands_from_toml_string_and_list(tmp_path) -> None:
    toml = tmp_path / "url4.toml"
    toml.write_text(
        '[commands]\n"/py" = "python3 -"\n"/sh" = ["bash", "-c", "cat"]\n', encoding="utf-8"
    )
    config = resolve({}, {}, toml)
    assert config.commands["/py"] == ("python3", "-")
    assert config.commands["/sh"] == ("bash", "-c", "cat")


def test_token_from_env_and_file_and_stdin(tmp_path, monkeypatch) -> None:
    assert resolve({}, {"URL4_BACKEND_TOKEN": "envtok"}, None).backend_token == "envtok"
    token_file = tmp_path / "tok"
    token_file.write_text("filetok\n", encoding="utf-8")
    assert resolve({"backend_token": str(token_file)}, {}, None).backend_token == "filetok"
    monkeypatch.setattr("sys.stdin", _FakeStdin("stdintok\n"))
    assert resolve({"backend_token": "-"}, {}, None).backend_token == "stdintok"


def test_token_file_missing_is_config_error() -> None:
    with pytest.raises(ConfigError, match="cannot read backend-token file"):
        resolve({"backend_token": "/no/such/token/file"}, {}, None)


def test_unreadable_toml_is_config_error(tmp_path) -> None:
    toml = tmp_path / "bad.toml"
    toml.write_text("this = = broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="cannot read config"):
        resolve({}, {}, toml)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"concurrency": 0}, "concurrency must be >= 1"),
        ({"max_inflight": 0}, "max-inflight must be >= 1"),
        ({"timeout": 0.0}, "timeout must be > 0"),
        ({"routes": {"noslash": "m"}, "processor": "noslash"}, "must start with '/'"),
        ({"processor": "/absent"}, "not a configured route"),
    ],
)
def test_validate_rejects(kwargs, match) -> None:
    with pytest.raises(ConfigError, match=match):
        ServeConfig(**kwargs).validate()


def test_validate_rejects_route_command_collision() -> None:
    config = ServeConfig(routes={"/x": "m"}, commands={"/x": ("true",)}, processor="/x")
    with pytest.raises(ConfigError, match="collide"):
        config.validate()


def test_validate_rejects_reserved_path_and_empty_argv() -> None:
    with pytest.raises(ConfigError, match="reserved"):
        ServeConfig(routes={"/claude": "m", "/healthz": "m"}, processor="/claude").validate()
    with pytest.raises(ConfigError, match="empty argv"):
        ServeConfig(routes={"/claude": "m"}, commands={"/py": ()}, processor="/claude").validate()


def test_valid_config_passes() -> None:
    ServeConfig().validate()  # defaults are self-consistent


class _FakeStdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def readline(self) -> str:
        return self._text

    def read(self) -> str:
        return self._text
