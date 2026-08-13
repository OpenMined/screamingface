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
from scoreboard.routes.scores import MISSING_IDENTITY_DETAIL
from scoreboard.scores.models import Benchmark, IdempotencyKey, Score
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


@pytest_asyncio.fixture
async def app_with_cloudflare_auth(tortoise_db: None, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # WHY monkeypatch FORWARDED_ALLOW_IPS explicitly, not left at ambient/unset env: unset
    # falls back to uvicorn's own default "127.0.0.1" (see main.py), which is the EXACT SAME
    # address as this fixture's allowed_networks below — chosen because ASGITransport's default
    # fake peer is ("127.0.0.1", 123). create_app's overlap guard now refuses exactly that
    # combination (FORWARDED_ALLOW_IPS overlapping allowed_networks), so this fixture must pin
    # FORWARDED_ALLOW_IPS to something genuinely disjoint instead of relying on the implicit
    # uvicorn default no longer being safe to assume here.
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "192.0.2.1")
    # model_validate, not the constructor: allowed_networks arrives as a comma-separated
    # STRING (as the environment supplies it) and is parsed into networks by the
    # mode="before" validator — the behavior under test, same idiom aigateway's own
    # allowed_networks tests use.
    settings = Settings.model_validate(
        {
            "database_url": "sqlite://:memory:",
            "cors_origins": [],
            "auth_mode": "cloudflare_headers",
            "allowed_networks": "127.0.0.1/32",
        }
    )
    app = create_app(settings)
    await Benchmark.create(
        id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    return app


@pytest_asyncio.fixture
async def cloudflare_score_client(
    app_with_cloudflare_auth: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    # WHY: httpx's ASGITransport reports a fixed peer, ("127.0.0.1", 123) by default —
    # matches the fixture's allowed_networks above so the trusted-peer path is exercised.
    async with AsyncClient(
        transport=ASGITransport(app=app_with_cloudflare_auth),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def untrusted_peer_score_client(
    app_with_cloudflare_auth: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    # A peer address deliberately outside app_with_cloudflare_auth's allowed_networks
    # (127.0.0.1/32), to exercise the 403 "untrusted peer" path.
    async with AsyncClient(
        transport=ASGITransport(app=app_with_cloudflare_auth, client=("203.0.113.5", 443)),
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
    # OME-820: verified now defaults to True and asserts "ran on OpenMined
    # infrastructure". Unverified stays covered by the explicit-False row test.
    assert body["verified_by_openmined"] is True


async def test_post_score_without_idempotency_key_dedupes_identical_recipe(
    score_client: AsyncClient,
) -> None:
    # WHY: dedup is server-enforced by recipe content hash, independent of any
    # client-supplied header — a resubmitted identical recipe returns the existing
    # row instead of creating a duplicate (OME-391 / C28).
    first = await score_client.post(
        "/v1/scores", json=_valid_payload(accuracy=0.5, correct_questions=2)
    )
    second = await score_client.post(
        "/v1/scores", json=_valid_payload(accuracy=0.5, correct_questions=2)
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


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

    # A genuinely different recipe (not just a different key) — proves the expired
    # key no longer blocks resubmission, without colliding with the unrelated
    # content-hash dedup guard this test isn't exercising.
    second = await score_client.post(
        "/v1/scores",
        json=_valid_payload(accuracy=1.0, correct_questions=4),
        headers=headers,
    )

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


async def test_post_score_default_auth_mode_disabled_trusts_free_text(
    score_client: AsyncClient,
) -> None:
    # WHY: SCOREBOARD_AUTH_MODE unset (local dev, and every fixture above) must stay a
    # true no-op — the client-supplied submitted_by is trusted unchanged (OME-404's
    # documented default, so no existing deployment/test breaks from this change).
    response = await score_client.post("/v1/scores", json=_valid_payload(submitted_by="tester"))

    assert response.status_code == 201
    assert response.json()["submitted_by"] == "tester"


async def test_post_score_with_identity_header_stores_header_email(
    cloudflare_score_client: AsyncClient,
) -> None:
    response = await cloudflare_score_client.post(
        "/v1/scores",
        json=_valid_payload(submitted_by="someone-else"),
        headers={"X-User-Email": "researcher@example.test"},
    )

    assert response.status_code == 201
    # WHY: the header always wins over whatever the request body claims — a caller
    # cannot submit under another person's name. The body claimed "someone-else", so
    # seeing the header's identity here still proves that.
    #
    # OME-834: the published form is the local part only — the read API is public and
    # unauthenticated, so the domain is withheld to keep addresses out of scrapers.
    assert response.json()["submitted_by"] == "researcher"
    # ...and the row keeps the full address, which is what this test's name claims and
    # the response alone never verified. OpenMined must still be able to contact and
    # audit the verified identity behind a score (OME-404).
    stored = await Score.get(id=response.json()["id"])
    assert stored.submitted_by == "researcher@example.test"


async def test_post_score_missing_identity_header_returns_401(
    cloudflare_score_client: AsyncClient,
) -> None:
    response = await cloudflare_score_client.post("/v1/scores", json=_valid_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": MISSING_IDENTITY_DETAIL}


async def test_post_score_blank_identity_header_returns_401(
    cloudflare_score_client: AsyncClient,
) -> None:
    response = await cloudflare_score_client.post(
        "/v1/scores",
        json=_valid_payload(),
        headers={"X-User-Email": "   "},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": MISSING_IDENTITY_DETAIL}


async def test_post_score_missing_identity_header_wins_over_bad_accuracy(
    cloudflare_score_client: AsyncClient,
) -> None:
    # WHY: pins the exact regression round-1 self-review found and fixed — identity must be
    # checked before business-rule validation, so an unauthenticated caller never learns
    # anything about why its payload would otherwise be rejected. A future reorder that moves
    # the accuracy check back above _resolve_submitter must fail this test (400, not 401).
    response = await cloudflare_score_client.post(
        "/v1/scores",
        json=_valid_payload(accuracy=0.5, total_questions=100, correct_questions=10),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": MISSING_IDENTITY_DETAIL}


async def test_post_score_untrusted_peer_wins_over_unknown_benchmark(
    untrusted_peer_score_client: AsyncClient,
) -> None:
    # WHY: same regression class as above, for the 403/peer-check path against the
    # benchmark-existence check instead of the accuracy check.
    response = await untrusted_peer_score_client.post(
        "/v1/scores",
        json=_valid_payload(benchmark_id="missing"),
        headers={"X-User-Email": "researcher@example.test"},
    )

    assert response.status_code == 403


async def test_get_score_remains_public_when_cloudflare_headers_configured(
    cloudflare_score_client: AsyncClient,
) -> None:
    # WHY: GET has no auth wiring at all — pinned so a future refactor that shares a
    # dependency between routes can't silently make score reads non-public.
    created = await cloudflare_score_client.post(
        "/v1/scores",
        json=_valid_payload(),
        headers={"X-User-Email": "researcher@example.test"},
    )

    response = await cloudflare_score_client.get(f"/v1/scores/{created.json()['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]


async def test_post_score_untrusted_peer_returns_403_even_with_valid_header(
    untrusted_peer_score_client: AsyncClient,
) -> None:
    response = await untrusted_peer_score_client.post(
        "/v1/scores",
        json=_valid_payload(),
        headers={"X-User-Email": "researcher@example.test"},
    )

    assert response.status_code == 403


async def test_post_score_forwarded_for_header_never_substitutes_for_real_peer(
    untrusted_peer_score_client: AsyncClient,
) -> None:
    # WHY: X-Forwarded-For is exactly as forgeable as X-User-Email itself — trusting it
    # to decide whether to trust the identity header would be circular.
    response = await untrusted_peer_score_client.post(
        "/v1/scores",
        json=_valid_payload(),
        headers={"X-User-Email": "researcher@example.test", "X-Forwarded-For": "127.0.0.1"},
    )

    assert response.status_code == 403


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
    assert post_score["responses"]["401"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MessageErrorResponse",
    )
    assert post_score["responses"]["403"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MessageErrorResponse",
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
