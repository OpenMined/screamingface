"""Unit tests for AigwInterpreter — verifies process() semantics."""

from __future__ import annotations

import httpx
import pytest

from screamingface.plugins.aigw_base.backend import AigwBackend
from screamingface.plugins.aigw_base.interpreter import AigwInterpreter


def _factory_returning(text: str):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    def factory(timeout: float):
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout))

    return factory


@pytest.mark.anyio
async def test_process_combines_intent_and_sources() -> None:
    backend = AigwBackend(http_client_factory=_factory_returning("answer"))
    interp = AigwInterpreter(backend=backend)
    out = await interp.process(sources="cats are mammals", intent="what are cats?")
    assert out == "answer"


@pytest.mark.anyio
async def test_process_returns_empty_when_no_input() -> None:
    backend = AigwBackend(http_client_factory=_factory_returning("X"))
    interp = AigwInterpreter(backend=backend)
    assert await interp.process(sources="", intent=None) == ""
