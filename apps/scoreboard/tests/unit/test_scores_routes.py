from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise.exceptions import OperationalError

from scoreboard.config import Settings
from scoreboard.main import create_app
from scoreboard.scores.models import Benchmark, IdempotencyKey
from scoreboard.scores.store import ScoreStore

pytestmark = pytest.mark.asyncio


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "benchmark_id": "hle",
        "spec_id": "spec-1",
        "url4_expression": "url4://benchmark/spec-1",
        "submitted_by": "tester",
        "accuracy": 0.75,
        "total_questions": 4,
        "correct_questions": 3,
        "ran_with_providers": ["openai"],
        "ran_at_local": "2026-05-21T12:00:00+00:00",
        "client": {"name": "scoreboard-test", "version": "0.1.0", "platform": "test"},
        "metadata": {"source": "unit"},
    }
    payload.update(overrides)
    return payload


@pytest_asyncio.fixture
async def app_with_benchmark(tortoise_db: None) -> FastAPI:
    settings = Settings(database_url="sqlite://:memory:", cors_origins=[])
    app = create_app(settings)
    await Benchmark.create(
        id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    return app


@pytest_asyncio.fixture
async def score_client(app_with_benchmark: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_benchmark),
        base_url="http://test",
    ) as client:
        yield client


async def test_post_score_creates_new_row_201(score_client: AsyncClient) -> None:
    response = await score_client.post("/v1/scores", json=_valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["benchmark_id"] == "hle"
    assert body["spec_id"] == "spec-1"
    assert body["submitted_at"]
    assert body["verified_by_openmined"] is False


async def test_post_score_without_idempotency_key_always_creates_new_row(
    score_client: AsyncClient,
) -> None:
    first = await score_client.post(
        "/v1/scores", json=_valid_payload(accuracy=0.5, correct_questions=2)
    )
    second = await score_client.post(
        "/v1/scores", json=_valid_payload(accuracy=0.5, correct_questions=2)
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


async def test_post_score_with_live_idempotency_key_returns_200(
    score_client: AsyncClient,
) -> None:
    headers = {"Idempotency-Key": "repeat-key"}
    first = await score_client.post("/v1/scores", json=_valid_payload(), headers=headers)
    second = await score_client.post("/v1/scores", json=_valid_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["submitted_at"] == first.json()["submitted_at"]


async def test_post_score_with_expired_idempotency_key_creates_new_row(
    score_client: AsyncClient,
) -> None:
    headers = {"Idempotency-Key": "expired-key"}
    first = await score_client.post("/v1/scores", json=_valid_payload(), headers=headers)
    await IdempotencyKey.filter(key="expired-key").update(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert await ScoreStore().get_by_idempotency_key("expired-key") is None

    second = await score_client.post("/v1/scores", json=_valid_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


async def test_post_score_accuracy_mismatch_returns_400(score_client: AsyncClient) -> None:
    response = await score_client.post(
        "/v1/scores",
        json=_valid_payload(accuracy=0.5, total_questions=100, correct_questions=10),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["field"] == "accuracy"


async def test_post_score_accuracy_at_edge_tolerance_passes(score_client: AsyncClient) -> None:
    response = await score_client.post(
        "/v1/scores",
        json=_valid_payload(accuracy=0.82, total_questions=1000, correct_questions=810),
    )

    assert response.status_code == 201


async def test_post_score_accuracy_just_outside_tolerance_returns_400(
    score_client: AsyncClient,
) -> None:
    response = await score_client.post(
        "/v1/scores",
        json=_valid_payload(
            accuracy=0.8200000000005,
            total_questions=1000,
            correct_questions=810,
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["field"] == "accuracy"


async def test_post_score_unknown_benchmark_id_returns_404(score_client: AsyncClient) -> None:
    response = await score_client.post(
        "/v1/scores",
        json=_valid_payload(benchmark_id="missing"),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["field"] == "benchmark_id"


async def test_post_score_future_version_returns_422(score_client: AsyncClient) -> None:
    response = await score_client.post("/v1/scores", json=_valid_payload(version=2))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "version"]


async def test_post_score_url4_expression_too_long_returns_422(
    score_client: AsyncClient,
) -> None:
    response = await score_client.post(
        "/v1/scores",
        json=_valid_payload(url4_expression="x" * 32_001),
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "url4_expression"]


async def test_post_score_invalid_accuracy_returns_422(score_client: AsyncClient) -> None:
    response = await score_client.post("/v1/scores", json=_valid_payload(accuracy=1.5))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "accuracy"]


async def test_post_score_store_unavailable_returns_503(
    score_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raise_operational_error(*args: object, **kwargs: object) -> bool:
        raise OperationalError("database is locked")

    monkeypatch.setattr(Benchmark, "exists", raise_operational_error)

    response = await score_client.post("/v1/scores", json=_valid_payload())

    assert response.status_code == 503
    assert response.json() == {"detail": "score store unavailable"}


async def test_get_score_by_id_returns_row(score_client: AsyncClient) -> None:
    created = await score_client.post("/v1/scores", json=_valid_payload())

    response = await score_client.get(f"/v1/scores/{created.json()['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]
    assert response.json()["benchmark_id"] == "hle"


async def test_get_score_unknown_id_returns_404(score_client: AsyncClient) -> None:
    response = await score_client.get(f"/v1/scores/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "score not found"}


async def test_openapi_schema_includes_new_endpoints(score_client: AsyncClient) -> None:
    response = await score_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    post_score = paths["/v1/scores"]["post"]
    get_score = paths["/v1/scores/{score_id}"]["get"]

    assert post_score["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ScoreSubmission",
    )
    assert post_score["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ScoreSchema",
    )
    assert post_score["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ScoreSchema",
    )
    assert post_score["responses"]["400"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/FieldErrorResponse",
    )
    assert post_score["responses"]["404"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/FieldErrorResponse",
    )
    assert post_score["responses"]["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MessageErrorResponse",
    )
    assert get_score["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ScoreSchema",
    )
    assert get_score["responses"]["404"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MessageErrorResponse",
    )
    assert get_score["responses"]["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MessageErrorResponse",
    )
