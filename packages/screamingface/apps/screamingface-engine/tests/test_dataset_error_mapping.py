"""HTTP boundary mapping for engine-owned benchmark dataset failures."""

from __future__ import annotations

import json

import httpx
import pytest
from url4 import Request, ResolutionError, Url4Node

from screamingface_engine.asgi import EngineASGI
from screamingface_engine.gateway import GatewayClient


def _gateway() -> GatewayClient:
    return GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )
        ),
    )


@pytest.mark.asyncio
async def test_dataset_authentication_failure_is_401_for_plain_and_streamed_evaluation() -> None:
    node = Url4Node("test", eval_path="/v1")

    @node.endpoint("/dataset")
    async def dataset(_request: Request) -> str:
        raise ResolutionError(
            "gpqa@1 requires HF_TOKEN in the ScreamingFace engine environment",
            code="dataset_authentication_required",
            permanent=True,
        )

    gateway = _gateway()
    app = EngineASGI(node, gateway, max_inflight=1, timeout=1)
    transport = httpx.ASGITransport(app=app)
    expression = "/dataset?q=()!'load'"
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        plain = await client.get("/v1", params={"q": expression})
        streamed = await client.get(
            "/v1",
            params={"q": expression},
            headers={"accept": "text/event-stream"},
        )
    await gateway.aclose()

    assert plain.status_code == 401
    assert plain.json()["error"]["code"] == "dataset_authentication_required"
    terminal = _terminal_event(streamed.text)
    assert streamed.status_code == 200
    assert terminal["type"] == "error"
    assert terminal["status"] == 401
    error = terminal["error"]
    assert isinstance(error, dict)
    assert error["code"] == "dataset_authentication_required"


def _terminal_event(body: str) -> dict[str, object]:
    block = body.strip().split("\n\n")[-1]
    data = next(line[6:] for line in block.splitlines() if line.startswith("data: "))
    payload = json.loads(data)
    assert isinstance(payload, dict)
    return payload
