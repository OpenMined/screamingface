from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from pypika_tortoise.analytics import RowNumber
from pypika_tortoise.enums import Order
from pypika_tortoise.queries import Query, QueryBuilder
from tortoise import Tortoise
from tortoise.exceptions import IntegrityError
from tortoise.query_api import execute_pypika
from tortoise.transactions import in_transaction

from .models import Benchmark, IdempotencyKey, Score
from .schemas import BenchmarkSchema, LeaderboardEntry, ScoreSchema, ScoreSubmission

IDEMPOTENCY_TTL = timedelta(hours=24)


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


def _submission_to_kwargs(submission: ScoreSubmission, content_hash: str) -> dict[str, object]:
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
        "client_name": submission.client.name if submission.client else None,
        "client_version": submission.client.version if submission.client else None,
        "client_platform": submission.client.platform if submission.client else None,
        "metadata": submission.metadata,
        "content_hash": content_hash,
    }


def _content_hash(submission: ScoreSubmission) -> str:
    # WHY: identity is the recipe (what was run + its result), not who ran it or
    # when — submitted_by/client_*/ran_at_local/metadata are deliberately excluded.
    # Provider order is kept as submitted (not sorted) since it's part of what
    # actually happened, not incidental serialization (OME-391 / C28). `version` is
    # also excluded — currently a no-op since ScoreSubmission.version is pinned to
    # Literal[1], but revisit this if a future schema version is ever accepted, since
    # two payloads differing only in version would otherwise dedupe together.
    identity = {
        "benchmark_id": submission.benchmark_id,
        "spec_id": submission.spec_id,
        "url4_expression": submission.url4_expression,
        "accuracy": submission.accuracy,
        "total_questions": submission.total_questions,
        "correct_questions": submission.correct_questions,
        "ran_with_providers": submission.ran_with_providers,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_leaderboard_query(benchmark_id: str, top_n: int) -> QueryBuilder:
    scores = Score.get_table()
    row_number = (
        RowNumber()
        .over(scores.spec_id)
        .orderby(scores.accuracy, order=Order.desc)
        .orderby(scores.submitted_at, order=Order.desc)
        .as_("rn")
    )
    ranked = (
        Query.from_(scores)
        .select(
            scores.spec_id,
            scores.accuracy,
            scores.total_questions,
            scores.ran_with_providers,
            scores.submitted_at,
            scores.submitted_by,
            scores.verified_by_openmined,
            scores.url4_expression,
            row_number,
        )
        .where(scores.benchmark_id == benchmark_id)
    ).as_("ranked")

    return (
        Query.from_(ranked)
        .select(
            ranked.spec_id,
            ranked.accuracy,
            ranked.total_questions,
            ranked.ran_with_providers,
            ranked.submitted_at,
            ranked.submitted_by,
            ranked.verified_by_openmined,
            ranked.url4_expression,
        )
        .where(ranked.rn == 1)
        .orderby(ranked.accuracy, order=Order.desc)
        .limit(top_n)
    )


class ScoreStore:
    async def register_benchmark(
        self,
        benchmark_id: str,
        display_name: str,
        description: str | None = None,
        dataset_url: str | None = None,
    ) -> BenchmarkSchema:
        benchmark, _ = await Benchmark.update_or_create(
            defaults={
                "display_name": display_name,
                "description": description,
                "dataset_url": dataset_url,
            },
            id=benchmark_id,
        )
        return _benchmark_to_schema(benchmark)

    async def list_benchmarks(self) -> list[BenchmarkSchema]:
        rows = await Benchmark.all().order_by("id")
        return [_benchmark_to_schema(benchmark) for benchmark in rows]

    async def _resolve_existing(
        self,
        idempotency_key: str | None,
        content_hash: str,
    ) -> Score | None:
        # Shared by the pre-insert check and the post-IntegrityError race handler —
        # idempotency_key (a fast path keyed to one client's retry) takes priority
        # when present; content_hash is the unconditional backstop (OME-391 / C28).
        if idempotency_key is not None:
            linked = await IdempotencyKey.get_or_none(
                key=idempotency_key,
                expires_at__gt=datetime.now(UTC),
            ).prefetch_related("score")
            if linked is not None:
                return linked.score

        return await Score.get_or_none(content_hash=content_hash)

    async def submit(
        self,
        submission: ScoreSubmission,
        idempotency_key: str | None = None,
    ) -> ScoreSchema:
        now_ts = datetime.now(UTC)
        content_hash = _content_hash(submission)

        existing = await self._resolve_existing(idempotency_key, content_hash)
        if existing is not None:
            return _score_to_schema(existing)

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
                    **_submission_to_kwargs(submission, content_hash),
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
            # A concurrent request may have won the race on either constraint.
            existing = await self._resolve_existing(idempotency_key, content_hash)
            if existing is not None:
                return _score_to_schema(existing)
            raise

    async def find_existing(
        self,
        submission: ScoreSubmission,
        idempotency_key: str | None = None,
    ) -> ScoreSchema | None:
        # Public entry point for a caller (the route) that needs to know up front
        # whether a submission would dedupe, e.g. to answer 200 vs 201 — reuses the
        # exact same idempotency-key-then-content-hash priority as submit()'s own
        # pre-check, via one hash computation, instead of two separate lookups
        # (OME-391 / C28).
        existing = await self._resolve_existing(idempotency_key, _content_hash(submission))
        return _score_to_schema(existing) if existing is not None else None

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
        result = await execute_pypika(
            _build_leaderboard_query(benchmark_id, top_n),
            using_db=conn,
        )
        rows = result.rows
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
