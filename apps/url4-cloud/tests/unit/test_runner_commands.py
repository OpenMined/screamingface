from __future__ import annotations

import json
import sys

import pytest

from url4.core.errors import ResolutionError
from url4.peer.server import Request
from url4_cloud.runner.commands import make_command_handler


@pytest.mark.asyncio
async def test_command_handler_exposes_the_complete_url4_request_without_a_shell() -> None:
    program = (
        "import json,sys;"
        "print(json.dumps({'argv':sys.argv[1:],'stdin':sys.stdin.read()},sort_keys=True))"
    )
    handler = make_command_handler(
        (
            sys.executable,
            "-c",
            program,
            "{intent}",
            "{context}",
            "{param:case}",
            "{param:missing}",
            "{params}",
        ),
        timeout_s=2,
    )

    result = await handler(
        Request(
            path="/benchmark",
            context="resolved context",
            intent="grade",
            params={"z": "last", "case": "7"},
        )
    )

    assert json.loads(result) == {
        "argv": [
            "grade",
            "resolved context",
            "7",
            "",
            '{"case": "7", "z": "last"}',
        ],
        "stdin": "resolved context",
    }


@pytest.mark.asyncio
async def test_substitution_is_single_pass_for_caller_controlled_values() -> None:
    handler = make_command_handler(
        (sys.executable, "-c", "import sys;print(sys.argv[1])", "{context}"),
        timeout_s=2,
    )

    result = await handler(
        Request(path="/benchmark", context="{intent}", intent="must-not-expand", params={})
    )

    assert result.strip() == "{intent}"


@pytest.mark.asyncio
async def test_nonzero_command_exit_is_a_typed_resolution_failure() -> None:
    handler = make_command_handler(
        (
            sys.executable,
            "-c",
            "import sys;sys.stderr.write('broken benchmark');sys.exit(3)",
        ),
        timeout_s=2,
    )

    with pytest.raises(ResolutionError, match="exited 3: broken benchmark"):
        await handler(Request(path="/benchmark", context="", intent="", params={}))
