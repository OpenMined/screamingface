"""Backend endpoint handlers for `url4 serve` (url4._serve).

STORY: a served model route calls the aigateway and returns the completion text;
a served command route runs a local subprocess (doctrine N4) and returns its
stdout. Both surface upstream failures as ResolutionError so the node maps them
to the right HTTP status.
"""

from __future__ import annotations

import json

import httpx
import pytest

from url4._serve import _merge, make_command_handler, make_llm_handler
from url4.errors import ResolutionError
from url4.server import Request

pytestmark = pytest.mark.asyncio


def _req(context: str = "the data", intent: str = "do it") -> Request:
    return Request(path="/claude", context=context, intent=intent, params={})


def _gateway_client(recorder: list[httpx.Request], response: httpx.Response) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.append(request)
        return response

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_merge_matches_engine_convention() -> None:
    assert _merge("do it", "data") == "do it\n\ndata"
    assert _merge("", "data") == "data"
    assert _merge("do it", "") == "do it"
    assert _merge("", "") == ""


async def test_llm_handler_calls_aigateway_with_model_prompt_and_auth() -> None:
    seen: list[httpx.Request] = []
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "ANSWER"}}]})
    async with _gateway_client(seen, ok) as client:
        handler = make_llm_handler(client, "http://gw:9105", "claude/opus", token="secret")
        result = await handler(_req(context="ctx", intent="summarize"))
    assert result == "ANSWER"
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "http://gw:9105/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer secret"
    body = json.loads(request.content)
    assert body["model"] == "claude/opus"
    assert body["stream"] is False
    assert body["messages"] == [{"role": "user", "content": "summarize\n\nctx"}]


async def test_llm_handler_omits_auth_header_without_token() -> None:
    seen: list[httpx.Request] = []
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})
    async with _gateway_client(seen, ok) as client:
        handler = make_llm_handler(client, "http://gw", "m", token=None)
        await handler(_req())
    assert "authorization" not in seen[0].headers


async def test_llm_handler_upstream_error_becomes_resolution_error() -> None:
    async with _gateway_client([], httpx.Response(500, text="boom")) as client:
        handler = make_llm_handler(client, "http://gw", "m", token=None)
        with pytest.raises(ResolutionError, match="aigateway call for model 'm' failed"):
            await handler(_req())


async def test_llm_handler_unexpected_shape_becomes_resolution_error() -> None:
    async with _gateway_client([], httpx.Response(200, json={"nope": 1})) as client:
        handler = make_llm_handler(client, "http://gw", "m", token=None)
        with pytest.raises(ResolutionError, match="unexpected response"):
            await handler(_req())


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
