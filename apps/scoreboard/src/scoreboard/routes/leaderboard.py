from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from scoreboard.scores.models import Benchmark
from scoreboard.scores.schemas import BenchmarkSchema, LeaderboardEntry, ScoreSchema
from scoreboard.scores.store import ScoreStore

MAX_LEADERBOARD_TOP = 200
MAX_HISTORY_LIMIT = 100

router = APIRouter(prefix="/v1")


class BenchmarksResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmarks: list[BenchmarkSchema]


class RankedLeaderboardEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    spec_id: str
    accuracy: float
    total_questions: int
    ran_with_providers: list[str]
    submitted_at: datetime
    submitted_by: str | None
    verified_by_openmined: bool
    url4_expression: str


class LeaderboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark: BenchmarkSchema
    entries: list[RankedLeaderboardEntry]


class HistorySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    accuracy: float
    total_questions: int
    correct_questions: int
    submitted_at: datetime
    submitted_by: str | None
    verified_by_openmined: bool


class HistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    benchmark_id: str
    submissions: list[HistorySubmission]


def _score_store(request: Request) -> ScoreStore:
    return cast(ScoreStore, request.app.state.score_store)


async def _get_benchmark_or_404(benchmark_id: str) -> BenchmarkSchema:
    benchmark = await Benchmark.get_or_none(id=benchmark_id)
    if benchmark is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    return BenchmarkSchema(
        id=benchmark.id,
        display_name=benchmark.display_name,
        description=benchmark.description,
        dataset_url=benchmark.dataset_url,
        created_at=benchmark.created_at,
    )


def _ranked_entry(rank: int, entry: LeaderboardEntry) -> RankedLeaderboardEntry:
    return RankedLeaderboardEntry(rank=rank, **entry.model_dump())


def _history_submission(score: ScoreSchema) -> HistorySubmission:
    return HistorySubmission(
        id=score.id,
        accuracy=score.accuracy,
        total_questions=score.total_questions,
        correct_questions=score.correct_questions,
        submitted_at=score.submitted_at,
        submitted_by=score.submitted_by,
        verified_by_openmined=score.verified_by_openmined,
    )


@router.get("/benchmarks", response_model=BenchmarksResponse, tags=["benchmarks"])
async def list_benchmarks(request: Request) -> BenchmarksResponse:
    """List registered public benchmarks. This endpoint is public and has no auth."""
    benchmarks = await _score_store(request).list_benchmarks()
    return BenchmarksResponse(benchmarks=benchmarks)


@router.get("/leaderboard/{benchmark_id}", response_model=LeaderboardResponse, tags=["leaderboard"])
async def get_leaderboard(
    benchmark_id: str,
    request: Request,
    top: Annotated[
        int,
        Query(
            ge=1,
            description="Maximum entries to return. Values above 200 are clamped.",
        ),
    ] = 50,
) -> LeaderboardResponse:
    """Return the best-per-spec leaderboard for a registered benchmark.

    The response shape is stable for portal clients. Unknown benchmarks return 404,
    and requests above the public maximum are silently clamped to 200 entries.
    """
    benchmark = await _get_benchmark_or_404(benchmark_id)
    entries = await _score_store(request).leaderboard(
        benchmark_id=benchmark_id,
        top_n=min(top, MAX_LEADERBOARD_TOP),
    )
    ranked = [_ranked_entry(index, entry) for index, entry in enumerate(entries, start=1)]
    return LeaderboardResponse(benchmark=benchmark, entries=ranked)


@router.get(
    "/leaderboard/{benchmark_id}/{spec_id}/history",
    response_model=HistoryResponse,
    tags=["leaderboard"],
)
async def get_spec_history(
    benchmark_id: str,
    spec_id: str,
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            description="Maximum submissions to return. Values above 100 are clamped.",
        ),
    ] = 20,
) -> HistoryResponse:
    """Return newest-first submissions for a spec under a registered benchmark.

    The response shape is stable for portal clients. Unknown benchmarks return 404,
    while unknown specs under known benchmarks return an empty submissions list.
    Requests above the public maximum are silently clamped to 100 submissions.
    """
    await _get_benchmark_or_404(benchmark_id)
    submissions = await _score_store(request).list_for_spec(
        benchmark_id=benchmark_id,
        spec_id=spec_id,
        limit=min(limit, MAX_HISTORY_LIMIT),
    )
    return HistoryResponse(
        spec_id=spec_id,
        benchmark_id=benchmark_id,
        submissions=[_history_submission(score) for score in submissions],
    )
