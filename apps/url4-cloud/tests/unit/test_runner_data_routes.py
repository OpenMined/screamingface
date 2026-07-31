"""Declared `[data]` artifacts on a Runner world — registration and serving.

FEATURE: benchmark artifacts as url4 addresses (see `test_runner_config_data`).
STORY: as a benchmark author, `/draco/cases` iterates into one row per case and
`/draco/rubrics/42` serves that case's rubric, live, without a restart.

These drive the REAL provider factory (`url4.cli._serve.make_data_provider`) rather than a stub —
the unit under test is that the runner's config reaches the engine's registry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from url4_cloud.runner.config import CommandSpec, DataSpec, ModelSpec, RunnerConfig
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world
from url4_cloud.runner.main import build_executor


def _aigateway_config() -> AigatewayConfig:
    return AigatewayConfig(
        default_model="claude-haiku-4-5", models=(ModelSpec(id="claude-haiku-4-5"),)
    )


async def _fetch(world, target: str) -> str:
    return await world.node.fetch(target, relative=True)


# --- serving --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inline_value_is_served_at_its_path() -> None:
    world = await build_aigateway_world(
        _aigateway_config(), data=(DataSpec(path="/draco/rubrics/42", value="RUBRIC-42"),)
    )
    try:
        assert await _fetch(world, "/draco/rubrics/42") == "RUBRIC-42"
    finally:
        await world.aclose()


@pytest.mark.asyncio
async def test_file_provider_is_reread_per_request(tmp_path: Path) -> None:
    """INVARIANT: `file` is live — editing a rubric must not need an image rebuild to take
    effect within a running node. This is the property that makes artifacts editable at all."""
    rubric = tmp_path / "42.md"
    rubric.write_text("FIRST", encoding="utf-8")
    world = await build_aigateway_world(
        _aigateway_config(), data=(DataSpec(path="/r/42", file=str(rubric)),)
    )
    try:
        assert await _fetch(world, "/r/42") == "FIRST"
        rubric.write_text("SECOND", encoding="utf-8")
        assert await _fetch(world, "/r/42") == "SECOND"
    finally:
        await world.aclose()


@pytest.mark.asyncio
async def test_command_provider_stdout_is_served() -> None:
    world = await build_aigateway_world(
        _aigateway_config(),
        data=(DataSpec(path="/rows", command=(sys.executable, "-c", "print('ROWS')")),),
    )
    try:
        assert (await _fetch(world, "/rows")).strip() == "ROWS"
    finally:
        await world.aclose()


@pytest.mark.asyncio
async def test_media_type_drives_collection_splitting() -> None:
    """A JSON array must iterate into N rows, not collapse into one.

    WHY declared rather than sniffed: a one-line JSON array served as text/plain is a single
    element, which would silently benchmark once against a blob instead of N times.
    """
    cases = json.dumps([{"id": 1}, {"id": 2}, {"id": 3}])
    world = await build_aigateway_world(
        _aigateway_config(),
        data=(DataSpec(path="/cases", value=cases, media_type="application/json"),),
    )
    try:
        result = await world.node.evaluate("/cases*(i:1.0:$item.id)!'row'")
    finally:
        await world.aclose()

    assert json.loads(result.text) == ["row\n\ni: 1", "row\n\ni: 2", "row\n\ni: 3"]


# --- registration ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_models_commands_and_data_coexist_on_one_node() -> None:
    world = await build_aigateway_world(
        _aigateway_config(),
        commands=(CommandSpec(path="/read", argv=("cat",)),),
        data=(DataSpec(path="/motd", value="hi"),),
    )
    try:
        routes = world.node.processor_routes()
        assert "/claude-haiku-4-5" in routes
        assert "/read" in routes
        assert await _fetch(world, "/motd") == "hi"
    finally:
        await world.aclose()


@pytest.mark.asyncio
async def test_data_colliding_with_the_eval_path_is_a_config_error() -> None:
    from url4_cloud.runner.config import RunnerConfigError

    with pytest.raises(RunnerConfigError, match="/v1"):
        await build_aigateway_world(_aigateway_config(), data=(DataSpec(path="/v1", value="x"),))


# --- the `/read` bridge ---------------------------------------------------------


@pytest.mark.asyncio
async def test_read_bridge_resolves_a_dynamic_artifact_path() -> None:
    """The load-bearing shape of the benchmark design.

    WHY it must be written this way: a reduce dispatches to the processor only when EVERY source
    is a call, but `$` is illegal in a CALL path and legal only in a bare data path. Wrapping the
    dynamic fetch as a source of a static call satisfies both — `/read` is the bridge.

    Asserting on what reaches the MODEL is the point: a bare `/rubrics/$item.id` source would
    make the reduce degrade to a text join and never dispatch at all, so a per-row model request
    carrying the right rubric is the only evidence that both halves held.
    """
    seen: list[httpx.Request] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "GRADED"}}], "usage": {}}
        )

    cases = json.dumps([{"id": 42}, {"id": 43}])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_handle), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            _aigateway_config(),
            client=client,
            commands=(CommandSpec(path="/read", argv=("cat",)),),
            data=(
                DataSpec(path="/cases", value=cases, media_type="application/json"),
                DataSpec(path="/rubrics/42", value="RUBRIC-42"),
                DataSpec(path="/rubrics/43", value="RUBRIC-43"),
            ),
        )
        try:
            result = await world.node.evaluate(
                "/cases*(rubric:1.0:/read(/rubrics/$item.id)!'get')!'grade'"
            )
        finally:
            await world.aclose()

    # The resolved sources land in the SYSTEM message, the intent in `[Instruction]`; assert over
    # every message rather than a fixed index, so this does not break on prompt-shape changes.
    prompts = ["\n".join(m["content"] for m in json.loads(r.content)["messages"]) for r in seen]
    assert any("RUBRIC-42" in p for p in prompts)
    assert any("RUBRIC-43" in p for p in prompts)
    assert json.loads(result.text) == ["GRADED", "GRADED"]


# --- the aigateway-less world ---------------------------------------------------


@pytest.mark.asyncio
async def test_data_only_config_still_builds_a_serving_world() -> None:
    executor = build_executor({}, config=RunnerConfig(data=(DataSpec(path="/motd", value="hi"),)))
    io, aclose = await executor._world_factory()  # type: ignore[misc]
    try:
        assert await io.fetch("/motd", relative=True) == "hi"
    finally:
        if aclose is not None:
            await aclose()


@pytest.mark.asyncio
async def test_data_reaches_the_world_alongside_aigateway() -> None:
    from url4_cloud.runner.config import AigatewaySection

    executor = build_executor(
        {},
        config=RunnerConfig(
            aigateway=AigatewaySection(
                base_url="http://aigateway.test",
                default_model="claude-haiku-4-5",
                models=(ModelSpec(id="claude-haiku-4-5"),),
            ),
            data=(DataSpec(path="/motd", value="hi"),),
        ),
    )
    io, aclose = await executor._world_factory()  # type: ignore[misc]
    try:
        assert await io.fetch("/motd", relative=True) == "hi"
    finally:
        if aclose is not None:
            await aclose()
