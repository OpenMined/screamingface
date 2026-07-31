"""Subprocess endpoint routes on a Runner world — `[commands]` end to end.

FEATURE: a Runner Job can declare a local backend (blocker B2 of the benchmark execution
verdict). STORY: as an operator I declare `/benchmark` in url4.toml and a deployed run can
address it, with the caller's params and context reaching the script.

These drive the REAL subprocess handler (`url4.cli._serve.make_command_handler`) rather than a
stub — the point of the unit is that the runner's config reaches the engine's registration, so
faking the handler would test nothing.
"""

from __future__ import annotations

import sys

import pytest

from url4_cloud.runner.config import AigatewaySection, CommandSpec, ModelSpec, RunnerConfig
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world
from url4_cloud.runner.main import build_executor

# A script that reports what the handler handed it, so one assertion covers the whole
# substitution surface rather than trusting the template was merely non-empty.
_REPORT = "import sys,json;print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}))"


def _report_command(path: str = "/probe", **kwargs: object) -> CommandSpec:
    return CommandSpec(
        path=path,
        argv=(sys.executable, "-c", _REPORT, "{param:operation}", "{context}"),
        **kwargs,  # type: ignore[arg-type]
    )


def _aigateway_config() -> AigatewayConfig:
    return AigatewayConfig(
        default_model="claude-haiku-4-5", models=(ModelSpec(id="claude-haiku-4-5"),)
    )


# --- registration ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_declared_command_registers_its_route() -> None:
    world = await build_aigateway_world(
        _aigateway_config(), commands=(CommandSpec(path="/upper", argv=("cat",)),)
    )
    try:
        routes = world.node.processor_routes()
    finally:
        await world.aclose()

    assert "/upper" in routes
    # INVARIANT: commands are ADDED to the model routes, never instead of them.
    assert "/claude-haiku-4-5" in routes


@pytest.mark.asyncio
async def test_command_route_runs_the_subprocess_and_returns_stdout() -> None:
    world = await build_aigateway_world(
        _aigateway_config(),
        commands=(CommandSpec(path="/echo", argv=(sys.executable, "-c", "print('hi')")),),
    )
    try:
        result = await world.node.fetch("/echo?q=()!%27go%27", relative=True)
    finally:
        await world.aclose()

    assert result.strip() == "hi"


@pytest.mark.asyncio
async def test_params_and_context_reach_the_script() -> None:
    """`{param:…}` and `{context}` are the two channels a benchmark operation needs."""
    import json

    world = await build_aigateway_world(_aigateway_config(), commands=(_report_command(),))
    try:
        raw = await world.node.fetch(
            "/probe?operation=grade&q=(the-answer)!%27go%27", relative=True
        )
    finally:
        await world.aclose()

    seen = json.loads(raw)
    assert seen["argv"] == ["grade", "the-answer"]
    # INVARIANT: the resolved context is ALSO piped to stdin — the wide channel a real payload
    # uses, since argv cannot carry a large answer.
    assert seen["stdin"] == "the-answer"


@pytest.mark.asyncio
async def test_command_colliding_with_the_eval_path_is_a_config_error() -> None:
    # WHY here and not in `config.py`: the eval path is the ENGINE's rule. Converting its
    # ValueError keeps the two from drifting instead of restating the rule in two places.
    from url4_cloud.runner.config import RunnerConfigError

    with pytest.raises(RunnerConfigError, match="/v1"):
        await build_aigateway_world(
            _aigateway_config(), commands=(CommandSpec(path="/v1", argv=("cat",)),)
        )


@pytest.mark.asyncio
async def test_non_zero_exit_surfaces_as_a_resolution_error() -> None:
    from url4.core.errors import ResolutionError

    world = await build_aigateway_world(
        _aigateway_config(),
        commands=(CommandSpec(path="/boom", argv=(sys.executable, "-c", "raise SystemExit(3)")),),
    )
    try:
        with pytest.raises(ResolutionError, match="exited 3"):
            await world.node.fetch("/boom?q=()!%27go%27", relative=True)
    finally:
        await world.aclose()


@pytest.mark.asyncio
async def test_per_route_timeout_is_honored() -> None:
    world = await build_aigateway_world(
        _aigateway_config(),
        commands=(
            CommandSpec(
                path="/slow",
                argv=(sys.executable, "-c", "import time;time.sleep(5)"),
                timeout_s=0.2,
            ),
        ),
    )
    from url4.core.errors import ResolutionError

    try:
        with pytest.raises(ResolutionError, match="timed out"):
            await world.node.fetch("/slow?q=()!%27go%27", relative=True)
    finally:
        await world.aclose()


# --- the commands-only world ----------------------------------------------------


@pytest.mark.asyncio
async def test_commands_only_config_still_builds_a_serving_world() -> None:
    """INVARIANT: no `[aigateway]` is a legitimate world, not an empty one, once commands exist.

    Before commands were parsed, an absent `[aigateway]` could only mean "deny everything".
    A config declaring only commands must reach a node that serves them.
    """
    executor = build_executor(
        {},
        config=RunnerConfig(
            commands=(CommandSpec(path="/echo", argv=(sys.executable, "-c", "print('ok')")),)
        ),
    )
    io, aclose = await executor._world_factory()  # type: ignore[misc]
    try:
        assert (await io.fetch("/echo?q=()!%27go%27", relative=True)).strip() == "ok"
    finally:
        if aclose is not None:
            await aclose()


@pytest.mark.asyncio
async def test_no_aigateway_and_no_commands_still_denies_everything() -> None:
    from url4.core.errors import Url4Error

    executor = build_executor({}, config=RunnerConfig())
    io, _ = await executor._world_factory()  # type: ignore[misc]

    with pytest.raises(Url4Error):
        await io.fetch("/anything", relative=True)


@pytest.mark.asyncio
async def test_commands_reach_the_world_alongside_aigateway() -> None:
    executor = build_executor(
        {},
        config=RunnerConfig(
            aigateway=AigatewaySection(
                base_url="http://aigateway.test",
                default_model="claude-haiku-4-5",
                models=(ModelSpec(id="claude-haiku-4-5"),),
            ),
            commands=(CommandSpec(path="/echo", argv=(sys.executable, "-c", "print('ok')")),),
        ),
    )
    io, aclose = await executor._world_factory()  # type: ignore[misc]
    try:
        assert (await io.fetch("/echo?q=()!%27go%27", relative=True)).strip() == "ok"
    finally:
        if aclose is not None:
            await aclose()
