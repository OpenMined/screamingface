"""Pydantic response DTOs for the eval_runs HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["running", "done", "failed"]


class EvalQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idx: int
    question: str
    expected: str
    predicted: str | None = None
    correct: bool | None = None
    raw_output: str | None = None
    error: str | None = None


class EvalRunSummaryOut(BaseModel):
    """List view — no questions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    spec_name: str
    url4_expression: str
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = "running"
    accuracy: float | None = None
    total_questions: int | None = None
    correct_questions: int | None = None
    error: str | None = None
    favorite: bool = False


class EvalRunOut(EvalRunSummaryOut):
    """Detail view — includes questions."""

    questions: list[EvalQuestionOut] = []


class EvalRunPatchIn(BaseModel):
    """Mutable fields on an eval run (currently just favorite)."""

    favorite: bool
