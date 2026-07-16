"""ServeConfig resolution + validation for `url4 serve` (url4._serve).

STORY: as an operator I define my backends entirely as [commands] — user-owned
argv templates; an LLM backend is my own gateway script mounted as a command —
and configure the node via flags, URL4_* env, and url4.toml. Flags win, then
env, then toml, then defaults; unusable settings fail fast before the server
binds, not mid-request.
"""

from __future__ import annotations

import pytest

from url4._serve import ConfigError, ServeConfig, resolve

CMDS = {"/upper": ("tr", "a-z", "A-Z"), "/echo": ("cat",)}


def test_defaults_when_only_commands_supplied(tmp_path) -> None:
    toml = tmp_path / "url4.toml"
    toml.write_text('[commands]\n"/upper" = ["tr", "a-z", "A-Z"]\n', encoding="utf-8")
    config = resolve({}, {}, toml)
    assert config.host == "127.0.0.1"
    assert config.port == 4404
    assert config.default_route is None  # unset — resolves to the first command
    assert config.resolved_default_route == "/upper"
    assert config.commands["/upper"] == ("tr", "a-z", "A-Z")


def test_connector_surface_is_gone() -> None:
    # INVARIANT: the aigateway connector was removed — the serve config carries
    # NO route map and no backend url/token; commands are the only backends.
    fields = ServeConfig.__dataclass_fields__
    for legacy in ("routes", "backend_url", "backend_token", "processor"):
        assert legacy not in fields, legacy


def test_flag_beats_env_beats_toml(tmp_path) -> None:
    toml = tmp_path / "url4.toml"
    toml.write_text('host = "toml-host"\nport = 1\n', encoding="utf-8")
    env = {"URL4_HOST": "env-host", "URL4_PORT": "2"}
    config = resolve({"host": "flag-host", "port": None}, env, toml)
    assert config.host == "flag-host"  # flag wins
    assert config.port == 2  # no flag -> env wins over toml


def test_default_route_precedence_flag_env_toml(tmp_path) -> None:
    toml = tmp_path / "url4.toml"
    toml.write_text(
        'default_route = "/toml"\n[commands]\n"/toml" = "cat"\n"/env" = "cat"\n"/flag" = "cat"\n',
        encoding="utf-8",
    )
    assert resolve({}, {}, toml).default_route == "/toml"
    assert resolve({}, {"URL4_DEFAULT_ROUTE": "/env"}, toml).default_route == "/env"
    config = resolve({"default_route": "/flag"}, {"URL4_DEFAULT_ROUTE": "/env"}, toml)
    assert config.default_route == "/flag"
    assert config.resolved_default_route == "/flag"


def test_env_typed_coercion_and_bad_value() -> None:
    assert resolve({}, {"URL4_CONCURRENCY": "7"}, None).concurrency == 7
    with pytest.raises(ConfigError, match="concurrency must be an integer"):
        resolve({}, {"URL4_CONCURRENCY": "not-an-int"}, None)


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


def test_first_declared_command_is_the_default_route(tmp_path) -> None:
    # TOML declaration order is the tie-breaker the operator controls.
    toml = tmp_path / "url4.toml"
    toml.write_text('[commands]\n"/py" = "python3 -"\n"/sh" = "cat"\n', encoding="utf-8")
    assert resolve({}, {}, toml).resolved_default_route == "/py"


def test_unreadable_toml_is_config_error(tmp_path) -> None:
    toml = tmp_path / "bad.toml"
    toml.write_text("this = = broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="cannot read config"):
        resolve({}, {}, toml)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"commands": CMDS, "concurrency": 0}, "concurrency must be >= 1"),
        ({"commands": CMDS, "max_inflight": 0}, "max-inflight must be >= 1"),
        ({"commands": CMDS, "timeout": 0.0}, "timeout must be > 0"),
        ({"commands": {"noslash": ("cat",)}}, "must start with '/'"),
        ({"commands": CMDS, "default_route": "/absent"}, "not a declared command route"),
        ({}, "requires at least one"),
        ({"default_route": "/x"}, "requires at least one"),
    ],
)
def test_validate_rejects(kwargs, match) -> None:
    with pytest.raises(ConfigError, match=match):
        ServeConfig(**kwargs).validate()


def test_validate_rejects_reserved_path_and_empty_argv() -> None:
    with pytest.raises(ConfigError, match="reserved"):
        ServeConfig(commands={"/echo": ("cat",), "/healthz": ("cat",)}).validate()
    with pytest.raises(ConfigError, match="empty argv"):
        ServeConfig(commands={"/py": ()}).validate()


def test_validate_rejects_eval_path_on_reserved_health_path() -> None:
    # Regression: an eval path equal to /healthz would collide with the node's
    # health data route at build time — must fail fast as a clean config error,
    # not an uncaught ValueError once the node is assembled.
    config = ServeConfig(commands=CMDS, eval_path="/healthz")
    with pytest.raises(ConfigError, match="reserved health path"):
        config.validate()


def test_valid_config_passes() -> None:
    config = ServeConfig(commands=CMDS)
    config.validate()
    assert config.resolved_default_route == "/upper"  # first declared command
