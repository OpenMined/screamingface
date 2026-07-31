"""`[data]` parsing in the Runner's declared world.

FEATURE: every benchmark artifact is a first-class url4 address (`/draco/cases`,
`/draco/rubrics/42`), declared one per entry and generated at image build.
STORY: as a benchmark author, I declare my cases and rubrics in url4.toml so an expression can
address them directly and a reader can diff the image's declared world.

Its own module rather than an append to `test_runner_config.py`: prior tests are append-only
(sdlc rule 5), and a new surface earns a new file.
"""

from __future__ import annotations

import pytest

from url4_cloud.runner.config import DataSpec, RunnerConfig, RunnerConfigError, parse_config

_MINIMAL = """
[aigateway]
base_url = "http://aigateway.test"
default_route = "/claude-haiku-4-5"
models = ["claude-haiku-4-5", "codex/gpt-5.5"]
"""


def _parse(toml_text: str, env: dict[str, str] | None = None) -> RunnerConfig:
    import tomllib

    return parse_config(tomllib.loads(toml_text), env or {})


# --- shapes ---------------------------------------------------------------------


def test_inline_string_is_a_value_provider() -> None:
    config = _parse(_MINIMAL + '\n[data]\n"/motd" = "hello"\n')

    assert config.data == (DataSpec(path="/motd", value="hello"),)


def test_file_provider_with_media_type() -> None:
    config = _parse(
        _MINIMAL
        + '\n[data]\n"/draco/cases" = { file = "cases.json", media_type = "application/json" }\n'
    )

    assert config.data == (
        DataSpec(path="/draco/cases", file="cases.json", media_type="application/json"),
    )


def test_command_provider() -> None:
    config = _parse(_MINIMAL + '\n[data]\n"/rows" = { command = ["./rows.sh"] }\n')

    assert config.data[0].command == ("./rows.sh",)


def test_several_artifacts_keep_their_declared_order() -> None:
    # INVARIANT: order is preserved so a generated table diffs stably against the dataset.
    config = _parse(_MINIMAL + '\n[data]\n"/r/1" = "one"\n"/r/2" = "two"\n"/r/3" = "three"\n')

    assert [spec.path for spec in config.data] == ["/r/1", "/r/2", "/r/3"]


def test_data_only_config_is_valid() -> None:
    """A world of pure artifacts, no models and no commands, is legitimate."""
    config = _parse('[data]\n"/motd" = "hello"\n')

    assert config.aigateway is None
    assert config.commands == ()
    assert config.data[0].path == "/motd"


def test_no_data_table_yields_no_data() -> None:
    assert _parse(_MINIMAL).data == ()


# --- validation -----------------------------------------------------------------


def test_path_must_start_with_a_slash() -> None:
    with pytest.raises(RunnerConfigError, match="must start with '/'"):
        _parse(_MINIMAL + '\n[data]\nmotd = "hello"\n')


def test_zero_providers_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="exactly one"):
        _parse(_MINIMAL + '\n[data]\n"/x" = { media_type = "text/plain" }\n')


def test_two_providers_is_a_config_error() -> None:
    # INVARIANT: exactly one source. Two would make the served bytes depend on lookup order.
    with pytest.raises(RunnerConfigError, match="exactly one"):
        _parse(_MINIMAL + '\n[data]\n"/x" = { value = "a", file = "b" }\n')


def test_unknown_key_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="unknown key"):
        _parse(_MINIMAL + '\n[data]\n"/x" = { value = "a", web_tools = true }\n')


def test_empty_command_argv_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="empty argv"):
        _parse(_MINIMAL + '\n[data]\n"/x" = { command = [] }\n')


def test_non_positive_timeout_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="timeout_s"):
        _parse(_MINIMAL + '\n[data]\n"/x" = { command = ["y"], timeout_s = 0 }\n')


# --- collisions -----------------------------------------------------------------


def test_data_colliding_with_a_model_route_is_a_config_error() -> None:
    with pytest.raises(RunnerConfigError, match="already declared"):
        _parse(_MINIMAL + '\n[data]\n"/claude-haiku-4-5" = "x"\n')


def test_data_colliding_with_a_command_route_is_a_config_error() -> None:
    # INVARIANT: one owner per path across ALL three route families, named at parse time rather
    # than surfacing as a ValueError from deep inside the engine's registry.
    with pytest.raises(RunnerConfigError, match="already declared"):
        _parse(_MINIMAL + '\n[commands]\n"/read" = ["cat"]\n\n[data]\n"/read" = "x"\n')


def test_holdings_and_identities_are_still_reserved() -> None:
    for table in ("holdings", "identities"):
        with pytest.raises(RunnerConfigError, match="reserved"):
            _parse(_MINIMAL + f'\n[{table}]\ndefault = "y"\n')
