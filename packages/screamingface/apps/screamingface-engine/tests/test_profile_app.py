from __future__ import annotations

import json

import httpx
import pytest
from screamingface import Case

from screamingface_engine.app import create_app


@pytest.mark.asyncio
async def test_profile_serves_registry_manifests_and_normalized_cases_as_plaintext() -> None:
    app = create_app(
        case_loaders={
            "gpqa@1": lambda: (Case("q1", "Question", reference="A"),),
            "draco@1": lambda: (
                Case(
                    "d1",
                    "Research question",
                    reference={"sections": []},
                    metadata={"domain": "science"},
                ),
            ),
        }
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        health = await client.get("/healthz")
        registry_response = await client.get("/.well-known/screamingface")
        manifest_response = await client.get("/sf/benchmarks/draco@1")
        cases_response = await client.get("/sf/benchmarks/draco@1/cases")

    registry = json.loads(registry_response.text)
    manifest = json.loads(manifest_response.text)
    cases = [json.loads(line) for line in cases_response.text.splitlines()]

    assert health.text == "ok"
    assert registry["schema"] == "screamingface.registry.v1"
    assert registry["benchmarks"][1]["tools"] == ["web_search"]
    assert manifest["grader"]["type"] == "rubric"
    assert cases == [
        {
            "id": "d1",
            "input": "Research question",
            "reference": {"sections": []},
            "metadata": {"domain": "science"},
        }
    ]
    assert registry_response.headers["content-type"].startswith("text/plain")
