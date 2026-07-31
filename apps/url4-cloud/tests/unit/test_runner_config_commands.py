"""`[commands]` parsing in the Runner's declared world.

FEATURE: subprocess endpoint routes in a Runner Job (blocker B2 of the benchmark execution
verdict). STORY: as an operator, I declare a local backend in url4.toml so a deployed run can
address it, exactly as `url4 serve` already allows.

Its own module rather than an append to `test_runner_config.py`: prior tests are append-only
(sdlc rule 5), and a new surface earns a new file instead of editing a passing one.
"""

from __future__ import annotations

import pytest

from url4_cloud.runner.config import CommandSpec, RunnerConfig, RunnerConfigError, parse_config

_MINIMAL = """
[aigateway]
base_url = "http://aigateway.test"
default_route = "/claude-haiku-4-5"
models = ["claude-haiku-4-5", "codex/gpt-5.5"]
"""


def _parse(toml_text: str, env: dict[str, str] | None = None) -> RunnerConfig:
    import tomllib

    return parse_config(tomllib.loads(toml_text), env or {})


def test_bare_list_declares_a_command_route() -> None:
    config = _parse(_MINIMAL + '\n[commands]\n"/upper" = ["tr", "a-z", "A-Z"]\n')

    assert config.commands == (
        CommandSpec(path="/upper", argv=("tr", "a-z", "A-Z"), timeout_s=120.0),
    )


def test_bare_string_is_shlex_split() -> None:
    """Parity with `url4 serve`'s `_as_argv`, so one url4.toml dialect serves both."""
    config = _parse(_MINIMAL + '\n[commands]\n"/echo" = "bash -lc {intent}"\n')

    assert config.commands[0].argv == ("bash", "-lc", "{intent}")


def test_table_form_carries_a_per_route_timeout() -> None:
    # WHY per route: a rubric judge with web tools outruns the 120s default that must keep
    # bounding a fast `load`.
    config = _parse(
        _MINIMAL
        + '\n[commands]\n"/benchmark" = { argv = ["python3", "run.py"], timeout_s = 300.0 }\n'
    )

    assert config.commands == (
        CommandSpec(path="/benchmark", argv=("python3", "run.py"), timeout_s=300.0),
    )


def test_table_form_without_timeout_uses_the_default() -> None:
    config = _parse(_MINIMAL + '\n[commands]\n"/b" = { argv = ["python3", "run.py"] }\n')

    assert config.commands[0].timeout_s == 120.0


def test_commands_only_config_is_valid() -> None:
    """INVARIANT: `[aigateway]` stays optional — a tokenless, model-free world is legitimate."""
    config = _parse('[commands]\n"/upper" = ["tr", "a-z", "A-Z"]\n')

    assert config.aigateway is None
    assert config.commands[0].path == "/upper"


def test_no_commands_table_yields_no_commands() -> None:
    assert _parse(_MINIMAL).commands == ()


def test_command_path_must_start_with_a_slash() -> None:
    with pytest.raises(RunnerConfigError, match="must start with '/'"):
        _parse(_MINIMAL + '\n[commands]\nupper = ["tr", "a-z", "A-Z"]\n')


def test_empty_argv_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="empty argv"):
        _parse(_MINIMAL + '\n[commands]\n"/upper" = []\n')


def test_non_positive_timeout_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="timeout_s"):
        _parse(_MINIMAL + '\n[commands]\n"/b" = { argv = ["x"], timeout_s = 0 }\n')


def test_unknown_key_in_a_command_table_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="unknown key"):
        _parse(_MINIMAL + '\n[commands]\n"/b" = { argv = ["x"], web_tools = true }\n')


def test_command_table_missing_argv_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="argv"):
        _parse(_MINIMAL + '\n[commands]\n"/b" = { timeout_s = 5.0 }\n')


def test_command_colliding_with_a_model_route_is_a_config_error() -> None:
    # INVARIANT: a route path has exactly one owner. Registering both would raise deep in the
    # engine at world-build time; catching it here names the offending config line instead.
    with pytest.raises(RunnerConfigError, match="already declared"):
        _parse(_MINIMAL + '\n[commands]\n"/claude-haiku-4-5" = ["cat"]\n')


def test_commands_is_no_longer_reserved_but_the_others_still_are() -> None:
    # AIDEV-NOTE: `data` was in this list until `[data]` was landed in the next cycle; it moved
    # out because it is now supported, not because the rule weakened. `[data]`'s own reserved
    # coverage lives in `test_runner_config_data`.
    for table in ("holdings", "identities"):
        with pytest.raises(RunnerConfigError, match="reserved"):
            _parse(_MINIMAL + f'\n[{table}]\n"/x" = "y"\n')
