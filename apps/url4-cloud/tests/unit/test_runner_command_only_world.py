"""The Engine runner can execute a declared command world without AI Gateway."""

import sys

import pytest

from url4 import RelExpr, expr, render, src, text
from url4.streaming.interfaces import Completed
from url4_cloud.runner.config import CommandSpec, RunnerConfig
from url4_cloud.runner.main import build_executor


@pytest.mark.asyncio
async def test_command_only_world_can_run_as_a_linked_candidate() -> None:
    config = RunnerConfig(
        commands=(
            CommandSpec(
                "/answer",
                (
                    sys.executable,
                    "-c",
                    "import sys;print('candidate:' + sys.stdin.read())",
                ),
            ),
        )
    )
    candidate = RelExpr(path="/answer", context="$input", intent=text("answer"))
    benchmark = RelExpr(path="/candidate", context="case-1", intent=text("$candidate"))
    linked = render(
        expr(
            src(text(render(candidate)), name="candidate", weight=0.0),
            benchmark,
            intent=text(""),
        )
    )
    executor = build_executor({}, config)

    frames = [frame async for frame in executor.execute(linked)]

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.result.body.strip() == "candidate:case-1"
