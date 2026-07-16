"""Backend endpoint handlers for `url4 serve` (url4._serve).

STORY: a served command route runs a local subprocess (doctrine N4) and returns
its stdout — the ONLY backend kind `url4 serve` ships; a user's LLM backend is
their own gateway script mounted as a command. Failures surface as
ResolutionError so the node maps them to the right HTTP status.
"""

from __future__ import annotations

import pytest

from url4._serve import make_command_handler
from url4.errors import ResolutionError
from url4.server import Request

pytestmark = pytest.mark.asyncio


def _req(context: str = "the data", intent: str = "do it") -> Request:
    return Request(path="/cmd", context=context, intent=intent, params={})


async def test_command_handler_pipes_context_and_returns_stdout() -> None:
    handler = make_command_handler(
        ["python3", "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"], timeout=5.0
    )
    assert await handler(_req(context="hello")) == "HELLO"


async def test_command_handler_substitutes_intent_and_context_tokens() -> None:
    handler = make_command_handler(["python3", "-c", "print('{intent}')"], timeout=5.0)
    assert (await handler(_req(intent="pong"))).strip() == "pong"


async def test_command_handler_nonzero_exit_becomes_resolution_error() -> None:
    handler = make_command_handler(["python3", "-c", "import sys; sys.exit(3)"], timeout=5.0)
    with pytest.raises(ResolutionError, match="exited 3"):
        await handler(_req())


async def test_command_handler_timeout_becomes_resolution_error() -> None:
    handler = make_command_handler(["python3", "-c", "import time; time.sleep(5)"], timeout=0.1)
    with pytest.raises(ResolutionError, match="timed out"):
        await handler(_req())


async def test_command_handler_start_failure_becomes_resolution_error() -> None:
    handler = make_command_handler(["/nonexistent/url4-binary-xyz"], timeout=5.0)
    with pytest.raises(ResolutionError, match="failed to start"):
        await handler(_req())


async def test_command_handler_non_utf8_stdout_does_not_crash() -> None:
    # Regression: a command that exits 0 with non-UTF-8 stdout must not escape the
    # handler as a raw UnicodeDecodeError (which would bypass Url4Error → HTTP
    # mapping and surface as a bare 500); decode is lenient instead.
    handler = make_command_handler(
        ["python3", "-c", "import sys; sys.stdout.buffer.write(bytes([0xff, 0xfe]))"], timeout=5.0
    )
    result = await handler(_req())
    assert result  # replacement chars, not an exception


async def test_llm_connector_is_gone() -> None:
    # INVARIANT: the aigateway connector was removed from the serve layer —
    # users own their backends entirely (commands only).
    import url4._serve as serve

    for legacy in ("make_llm_handler", "build_client", "DEFAULT_ROUTES", "_merge"):
        assert not hasattr(serve, legacy), legacy
