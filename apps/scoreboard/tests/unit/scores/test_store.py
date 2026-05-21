from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from tortoise import Tortoise

from scoreboard.scores.models import IdempotencyKey, Score
from scoreboard.scores.schemas import ScoreSubmission
from scoreboard.scores.store import ScoreStore

pytestmark = pytest.mark.asyncio


def _submission(
    *,
    spec_id: str = "spec-1",
    accuracy: float = 0.75,
    providers: list[str] | None = None,
) -> ScoreSubmission:
    correct_questions = int(accuracy * 100)
    return ScoreSubmission(
        benchmark_id="hle",
        spec_id=spec_id,
        url4_expression=f"url4://benchmark/{spec_id}/{accuracy}",
        submitted_by="tester",
        accuracy=accuracy,
        total_questions=100,
        correct_questions=correct_questions,
        ran_with_providers=providers or ["openai"],
        ran_at_local=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
        client_name="scoreboard-test",
        client_version="0.1.0",
        client_platform="test",
        metadata={"source": "unit"},
    )


async def _store_with_benchmark() -> ScoreStore:
    store = ScoreStore()
    await store.register_benchmark(
        benchmark_id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    return store


async def test_register_benchmark_and_list_benchmarks(tortoise_db: None) -> None:
    store = ScoreStore()

    registered = await store.register_benchmark(
        benchmark_id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    benchmarks = await store.list_benchmarks()

    assert registered.id == "hle"
    assert benchmarks == [registered]


async def test_submit_inserts_and_returns_score(tortoise_db: None) -> None:
    store = await _store_with_benchmark()

    score = await store.submit(_submission())

    assert score.benchmark_id == "hle"
    assert score.spec_id == "spec-1"
    assert score.accuracy == 0.75
    assert score.total_questions == 100
    assert score.correct_questions == 75
    assert score.ran_with_providers == ["openai"]
    assert score.client_name == "scoreboard-test"
    assert score.verified_by_openmined is False
    assert await Score.all().count() == 1


async def test_submit_with_live_idempotency_key_returns_existing_score(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()

    first = await store.submit(_submission(accuracy=0.5), idempotency_key="repeat-key")
    second = await store.submit(_submission(accuracy=0.9), idempotency_key="repeat-key")

    assert second.id == first.id
    assert second.submitted_at == first.submitted_at
    assert second.accuracy == 0.5
    assert await Score.all().count() == 1


async def test_submit_with_expired_idempotency_key_creates_new_score(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    first = await store.submit(_submission(accuracy=0.5), idempotency_key="expired-key")
    await IdempotencyKey.filter(key="expired-key").update(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    second = await store.submit(_submission(accuracy=0.9), idempotency_key="expired-key")

    assert second.id != first.id
    assert second.accuracy == 0.9
    assert await Score.all().count() == 2


async def test_get_by_idempotency_key_respects_expiry_and_cleanup(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    score = await store.submit(_submission(), idempotency_key="lookup-key")

    assert await store.get_by_idempotency_key("lookup-key") == score

    past = datetime.now(UTC) - timedelta(seconds=1)
    await IdempotencyKey.filter(key="lookup-key").update(expires_at=past)

    assert await store.get_by_idempotency_key("lookup-key") is None
    assert await store.cleanup_expired_idempotency_keys(datetime.now(UTC)) == 1
    assert await IdempotencyKey.all().count() == 0


async def test_leaderboard_returns_best_score_per_spec_in_rank_order(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    await store.submit(_submission(spec_id="spec-a", accuracy=0.6, providers=["openai"]))
    await store.submit(_submission(spec_id="spec-a", accuracy=0.9, providers=["anthropic"]))
    await store.submit(_submission(spec_id="spec-b", accuracy=0.95, providers=["openai", "gemini"]))
    await store.submit(_submission(spec_id="spec-c", accuracy=0.7, providers=["gemini"]))

    rows = await store.leaderboard("hle", top_n=2)

    assert [row.spec_id for row in rows] == ["spec-b", "spec-a"]
    assert [row.accuracy for row in rows] == [0.95, 0.9]
    assert rows[0].ran_with_providers == ["openai", "gemini"]
    assert isinstance(rows[0].ran_with_providers, list)


async def test_leaderboard_uses_newer_submission_as_accuracy_tie_breaker(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    older = await store.submit(_submission(spec_id="spec-a", accuracy=0.9, providers=["older"]))
    newer = await store.submit(_submission(spec_id="spec-a", accuracy=0.9, providers=["newer"]))
    await Score.filter(id=older.id).update(
        submitted_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
    )
    await Score.filter(id=newer.id).update(
        submitted_at=datetime(2026, 5, 21, 13, 0, tzinfo=UTC),
    )

    rows = await store.leaderboard("hle")

    assert len(rows) == 1
    assert rows[0].ran_with_providers == ["newer"]


async def test_list_for_spec_returns_history_newest_first(tortoise_db: None) -> None:
    store = await _store_with_benchmark()
    older = await store.submit(_submission(spec_id="spec-history", accuracy=0.5))
    newer = await store.submit(_submission(spec_id="spec-history", accuracy=0.8))
    await Score.filter(id=older.id).update(
        submitted_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
    )
    await Score.filter(id=newer.id).update(
        submitted_at=datetime(2026, 5, 21, 13, 0, tzinfo=UTC),
    )

    rows = await store.list_for_spec("hle", "spec-history")

    assert [row.id for row in rows] == [newer.id, older.id]


async def test_mark_verified_flips_score_flag(tortoise_db: None) -> None:
    store = await _store_with_benchmark()
    score = await store.submit(_submission())

    await store.mark_verified(score.id)

    verified = await Score.get(id=score.id)
    assert verified.verified_by_openmined is True


async def test_postgres_concurrent_idempotency_submissions_share_winner(
    tortoise_db: None,
) -> None:
    if Tortoise.get_connection("default").capabilities.dialect != "postgres":
        pytest.skip("requires Postgres")

    store = await _store_with_benchmark()
    results = await asyncio.gather(
        *(
            store.submit(
                _submission(accuracy=0.5 + (index / 100)),
                idempotency_key="race-key",
            )
            for index in range(10)
        ),
    )

    assert len({result.id for result in results}) == 1
    assert await Score.all().count() == 1
