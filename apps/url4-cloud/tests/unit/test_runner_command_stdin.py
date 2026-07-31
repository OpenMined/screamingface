"""`stdin = "intent"` on a Runner `[commands]` route — parsing and registration.

FEATURE: a Runner Job's command route can receive the intent on stdin (gap A1).
STORY: as an operator I declare `/benchmark` with `stdin = "intent"`, and a 100-case reducer
payload reaches the aggregate script instead of dying at exec with "Argument list too long".

Its own module rather than an append to `test_runner_config_commands.py` or
`test_runner_commands.py`: prior tests are append-only, and a new surface earns a new file.

INVARIANT under test: the runner validates the TYPE and the ENGINE owns the VALUE SET.
`config.py` may not import url4 (`test_only_url4_executor_module_imports_url4` pins the importer
set), so restating the legal values there would be a second copy free to drift from
`make_command_handler`. `register_commands` translates the engine's `ValueError` instead — the
same move it already makes for `node.endpoint`'s registrability rules.
"""

from __future__ import annotations

import sys
import tomllib

import pytest

from url4_cloud.runner.config import (
    CommandSpec,
    ModelSpec,
    RunnerConfig,
    RunnerConfigError,
    parse_config,
)
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world

_MINIMAL = """
[aigateway]
base_url = "http://aigateway.test"
default_route = "/claude-haiku-4-5"
models = ["claude-haiku-4-5"]
"""

_ECHO_STDIN = (sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())")


def _parse(toml_text: str) -> RunnerConfig:
    return parse_config(tomllib.loads(toml_text), {})


def _aigateway_config() -> AigatewayConfig:
    return AigatewayConfig(
        default_model="claude-haiku-4-5", models=(ModelSpec(id="claude-haiku-4-5"),)
    )


# --- parsing --------------------------------------------------------------------


def test_stdin_intent_parses() -> None:
    config = _parse(_MINIMAL + '\n[commands]\n"/bench" = { argv = ["cat"], stdin = "intent" }\n')

    assert config.commands == (CommandSpec(path="/bench", argv=("cat",), stdin="intent"),)


def test_stdin_defaults_to_context() -> None:
    """The default is what every existing url4.toml relies on — notably `/read` (`cat`), whose
    only job is echoing the piped context."""
    config = _parse(_MINIMAL + '\n[commands]\n"/read" = ["cat"]\n')

    assert config.commands[0].stdin == "context"


def test_non_string_stdin_is_rejected_at_parse() -> None:
    """The TYPE is the config's business, and a bare `true` is a plausible typo."""
    with pytest.raises(RunnerConfigError, match="stdin"):
        _parse(_MINIMAL + '\n[commands]\n"/bench" = { argv = ["cat"], stdin = true }\n')


def test_stdin_is_an_accepted_command_key() -> None:
    """Guards the inverse failure: an unknown-key check that never learned about `stdin` would
    reject the very declaration this change adds."""
    config = _parse(
        _MINIMAL
        + '\n[commands]\n"/bench" = { argv = ["cat"], timeout_s = 30.0, stdin = "intent" }\n'
    )

    assert config.commands[0].timeout_s == 30.0
    assert config.commands[0].stdin == "intent"


def test_unknown_command_key_is_still_rejected() -> None:
    with pytest.raises(RunnerConfigError, match="unknown key"):
        _parse(_MINIMAL + '\n[commands]\n"/bench" = { argv = ["cat"], stdinn = "intent" }\n')


# --- registration ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_stdin_value_fails_at_world_build() -> None:
    """Translated from the engine's ValueError, never restated in `config.py`."""
    with pytest.raises(RunnerConfigError, match="/bench"):
        await build_aigateway_world(
            _aigateway_config(),
            commands=(CommandSpec(path="/bench", argv=("cat",), stdin="params"),),
        )


@pytest.mark.asyncio
async def test_declared_route_pipes_the_intent_not_the_context() -> None:
    """END TO END on a real node, through the real subprocess handler.

    The expression makes the two channels distinguishable: `aggregate` is the CONTEXT (the
    source list) and `the-payload` is the INTENT. A route that ignored its declaration would
    echo `aggregate` — which is exactly the live failure shape, since the reducer's context is
    the operation token and scoring it would produce an empty run reported as a success.

    The kernel-ceiling proof lives in `packages/url4/tests/unit/test_serve_command_stdin.py`,
    where the handler is reachable directly: the limit belongs to the handler, and forcing a
    200 KB payload through an expression here would mostly be testing the parser.
    """
    world = await build_aigateway_world(
        _aigateway_config(),
        commands=(CommandSpec(path="/bench", argv=_ECHO_STDIN, stdin="intent"),),
    )
    try:
        out = await world.node.fetch("/bench?q=(aggregate)!%27the-payload%27", relative=True)
    finally:
        await world.aclose()

    # Asserted as a discriminator rather than an equality: the intent arrives as its SURFACE
    # literal, quotes included, because this expression writes one. The real reducer hop has no
    # quotes — the engine REPLACES a relative-expression reducer's intent with the JSON array of
    # row results — so pinning the exact quoted string here would encode a detail of the probe
    # instead of the behaviour, and would fail for the wrong reason if the surface form changed.
    assert "the-payload" in out
    assert "aggregate" not in out
