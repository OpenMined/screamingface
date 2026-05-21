from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from .models import Benchmark, IdempotencyKey, Score
from .schemas import BenchmarkSchema, LeaderboardEntry, ScoreSchema, ScoreSubmission

IDEMPOTENCY_TTL = timedelta(hours=24)


LEADERBOARD_SQL_POSTGRES = """
WITH ranked AS (
    SELECT
        spec_id,
        accuracy,
        total_questions,
        ran_with_providers,
        submitted_at,
        submitted_by,
        verified_by_openmined,
        url4_expression,
        ROW_NUMBER() OVER (
            PARTITION BY spec_id
            ORDER BY accuracy DESC, submitted_at DESC
        ) AS rn
    FROM scores
    WHERE benchmark_id = $1
)
SELECT
    spec_id,
    accuracy,
    total_questions,
    ran_with_providers,
    submitted_at,
    submitted_by,
    verified_by_openmined,
    url4_expression
FROM ranked
WHERE rn = 1
ORDER BY accuracy DESC
LIMIT $2
"""

LEADERBOARD_SQL_SQLITE = LEADERBOARD_SQL_POSTGRES.replace("$1", "?").replace("$2", "?")


def _benchmark_to_schema(model: Benchmark) -> BenchmarkSchema:
    return BenchmarkSchema(
        id=model.id,
        display_name=model.display_name,
        description=model.description,
        dataset_url=model.dataset_url,
        created_at=model.created_at,
    )


def _score_to_schema(model: Score) -> ScoreSchema:
    return ScoreSchema(
        id=model.id,
        version=model.version,
        benchmark_id=cast(str, getattr(model, "benchmark_id")),
        spec_id=model.spec_id,
        url4_expression=model.url4_expression,
        submitted_by=model.submitted_by,
        submitted_at=model.submitted_at,
        accuracy=model.accuracy,
        total_questions=model.total_questions,
        correct_questions=model.correct_questions,
        ran_with_providers=model.ran_with_providers,
        ran_at_local=model.ran_at_local,
        client_name=model.client_name,
        client_version=model.client_version,
        client_platform=model.client_platform,
        verified_by_openmined=model.verified_by_openmined,
        metadata=model.metadata,
    )


def _submission_to_kwargs(submission: ScoreSubmission) -> dict[str, object]:
    return {
        "benchmark_id": submission.benchmark_id,
        "version": submission.version,
        "spec_id": submission.spec_id,
        "url4_expression": submission.url4_expression,
        "submitted_by": submission.submitted_by,
        "accuracy": submission.accuracy,
        "total_questions": submission.total_questions,
        "correct_questions": submission.correct_questions,
        "ran_with_providers": submission.ran_with_providers,
        "ran_at_local": submission.ran_at_local,
        "client_name": submission.client_name,
        "client_version": submission.client_version,
        "client_platform": submission.client_platform,
        "metadata": submission.metadata,
    }


class ScoreStore:
    async def register_benchmark(
        self,
        benchmark_id: str,
        display_name: str,
        description: str | None = None,
        dataset_url: str | None = None,
    ) -> BenchmarkSchema:
        benchmark = await Benchmark.create(
            id=benchmark_id,
            display_name=display_name,
            description=description,
            dataset_url=dataset_url,
        )
        return _benchmark_to_schema(benchmark)

    async def list_benchmarks(self) -> list[BenchmarkSchema]:
        rows = await Benchmark.all().order_by("id")
        return [_benchmark_to_schema(benchmark) for benchmark in rows]

    async def submit(
        self,
        submission: ScoreSubmission,
        idempotency_key: str | None = None,
    ) -> ScoreSchema:
        now_ts = datetime.now(UTC)
        if idempotency_key is not None:
            existing = await IdempotencyKey.get_or_none(
                key=idempotency_key,
                expires_at__gt=now_ts,
            ).prefetch_related("score")
            if existing is not None:
                return _score_to_schema(existing.score)

        expires_at = now_ts + IDEMPOTENCY_TTL
        try:
            async with in_transaction() as connection:
                if idempotency_key is not None:
                    await (
                        IdempotencyKey.filter(
                            key=idempotency_key,
                            expires_at__lte=now_ts,
                        )
                        .using_db(connection)
                        .delete()
                    )

                score = await Score.create(
                    using_db=connection,
                    **_submission_to_kwargs(submission),
                )

                if idempotency_key is not None:
                    await IdempotencyKey.create(
                        using_db=connection,
                        key=idempotency_key,
                        score=score,
                        expires_at=expires_at,
                    )

            return _score_to_schema(score)
        except IntegrityError:
            if idempotency_key is None:
                raise

            live = await IdempotencyKey.get_or_none(
                key=idempotency_key,
                expires_at__gt=datetime.now(UTC),
            ).prefetch_related("score")
            if live is not None:
                return _score_to_schema(live.score)

            raise

    async def get_by_idempotency_key(self, key: str) -> ScoreSchema | None:
        now_ts = datetime.now(UTC)
        linked = await IdempotencyKey.get_or_none(
            key=key,
            expires_at__gt=now_ts,
        ).prefetch_related("score")
        if linked is None:
            return None
        return _score_to_schema(linked.score)

    async def cleanup_expired_idempotency_keys(self, now: datetime) -> int:
        return await IdempotencyKey.filter(expires_at__lte=now).delete()

    async def leaderboard(self, benchmark_id: str, top_n: int = 50) -> list[LeaderboardEntry]:
        conn = Tortoise.get_connection("default")
        sql = (
            LEADERBOARD_SQL_POSTGRES
            if conn.capabilities.dialect == "postgres"
            else LEADERBOARD_SQL_SQLITE
        )

        rows = await conn.execute_query_dict(sql, [benchmark_id, top_n])
        providers_field = Score._meta.fields_map["ran_with_providers"]
        for row in rows:
            row["ran_with_providers"] = providers_field.to_python_value(
                row["ran_with_providers"],
            )

        return [LeaderboardEntry(**row) for row in rows]

    async def list_for_spec(
        self,
        benchmark_id: str,
        spec_id: str,
        limit: int = 50,
    ) -> list[ScoreSchema]:
        rows = (
            await Score.filter(benchmark_id=benchmark_id, spec_id=spec_id)
            .order_by("-submitted_at")
            .limit(limit)
        )
        return [_score_to_schema(score) for score in rows]

    async def mark_verified(self, score_id: UUID | str) -> None:
        await Score.filter(id=score_id).update(verified_by_openmined=True)
