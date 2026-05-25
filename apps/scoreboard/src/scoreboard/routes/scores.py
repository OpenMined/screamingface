"""Public score submission and score lookup routes.

No authentication is required in v1. The verified_by_openmined response field is
the trust-tier signal for consumers; submitted scores default to unverified.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from tortoise.exceptions import OperationalError

from scoreboard.scores.models import Benchmark, Score
from scoreboard.scores.schemas import (
    FieldErrorDetail,
    FieldErrorResponse,
    MessageErrorResponse,
    ScoreSchema,
    ScoreSubmission,
)
from scoreboard.scores.store import ScoreStore

router = APIRouter(prefix="/v1", tags=["scores"])

ACCURACY_TOLERANCE = Decimal("0.01")
STORE_UNAVAILABLE_DETAIL = "score store unavailable"

SUBMIT_SCORE_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_200_OK: {
        "model": ScoreSchema,
        "description": "Idempotency hit; returns the original persisted score.",
    },
    status.HTTP_400_BAD_REQUEST: {
        "model": FieldErrorResponse,
        "description": "Field-specific validation error.",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": FieldErrorResponse,
        "description": "Unknown benchmark_id.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": MessageErrorResponse,
        "description": "Score store unavailable.",
    },
}
GET_SCORE_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": MessageErrorResponse,
        "description": "Score not found.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: SUBMIT_SCORE_RESPONSES[
        status.HTTP_503_SERVICE_UNAVAILABLE
    ],
}


def _field_error_detail(field: str, message: str) -> dict[str, str]:
    return FieldErrorDetail(field=field, message=message).model_dump()


@router.post(
    "/scores",
    response_model=ScoreSchema,
    status_code=status.HTTP_201_CREATED,
    responses=SUBMIT_SCORE_RESPONSES,
)
async def submit_score(
    submission: ScoreSubmission,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ScoreSchema:
    """Create a public unauthenticated score submission."""

    submitted_accuracy = Decimal(str(submission.accuracy))
    expected_accuracy = Decimal(submission.correct_questions) / Decimal(submission.total_questions)
    if abs(submitted_accuracy - expected_accuracy) > ACCURACY_TOLERANCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_field_error_detail(
                "accuracy",
                (
                    f"accuracy {submission.accuracy} does not match "
                    f"correct_questions/total_questions={expected_accuracy:.6f} "
                    f"within {ACCURACY_TOLERANCE}"
                ),
            ),
        )

    try:
        if not await Benchmark.exists(id=submission.benchmark_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_field_error_detail(
                    "benchmark_id",
                    f"unknown benchmark_id: {submission.benchmark_id!r}",
                ),
            )

        store = cast(ScoreStore, request.app.state.score_store)
        if idempotency_key is not None:
            existing = await store.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                response.status_code = status.HTTP_200_OK
                return existing

        return await store.submit(submission, idempotency_key=idempotency_key)
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=STORE_UNAVAILABLE_DETAIL,
        ) from exc


@router.get("/scores/{score_id}", response_model=ScoreSchema, responses=GET_SCORE_RESPONSES)
async def get_score(score_id: UUID) -> ScoreSchema:
    """Return a public score by id; inspect verified_by_openmined before trusting it."""

    try:
        score = await Score.get_or_none(id=score_id)
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=STORE_UNAVAILABLE_DETAIL,
        ) from exc

    if score is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="score not found")
    return ScoreSchema.model_validate(score, from_attributes=True)
