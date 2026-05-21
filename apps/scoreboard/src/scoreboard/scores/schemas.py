from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ClientInfo(BaseModel):
    """Optional client metadata for a score submission."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    version: str | None = None
    platform: str | None = None


class ScoreSubmission(BaseModel):
    """Input DTO for score ingestion."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    benchmark_id: str
    spec_id: str
    url4_expression: str
    submitted_by: str | None = None
    accuracy: float
    total_questions: int
    correct_questions: int
    ran_with_providers: list[str]
    ran_at_local: datetime | None = None
    client_name: str | None = None
    client_version: str | None = None
    client_platform: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("url4_expression")
    @classmethod
    def validate_url4_expression(cls, value: str) -> str:
        if not value:
            raise ValueError("url4_expression must be non-empty")
        return value

    @field_validator("benchmark_id", "spec_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        if not value:
            raise ValueError("identifier fields must be non-empty")
        return value

    @field_validator("accuracy")
    @classmethod
    def validate_accuracy(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("accuracy must be between 0 and 1")
        return value

    @field_validator("total_questions")
    @classmethod
    def validate_total_questions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("total_questions must be positive")
        return value

    @field_validator("correct_questions")
    @classmethod
    def validate_correct_questions(cls, value: int) -> int:
        if value < 0:
            raise ValueError("correct_questions must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_questions(self) -> ScoreSubmission:
        if self.correct_questions > self.total_questions:
            raise ValueError("correct_questions cannot exceed total_questions")
        return self


class BenchmarkSchema(BaseModel):
    """Read DTO for benchmarks."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    description: str | None
    dataset_url: str | None
    created_at: datetime


class ScoreSchema(BaseModel):
    """Read DTO for a score."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    version: int
    benchmark_id: str
    spec_id: str
    url4_expression: str
    submitted_by: str | None
    submitted_at: datetime
    accuracy: float
    total_questions: int
    correct_questions: int
    ran_with_providers: list[str]
    ran_at_local: datetime | None
    client_name: str | None
    client_version: str | None
    client_platform: str | None
    verified_by_openmined: bool
    metadata: dict[str, Any] | None


class LeaderboardEntry(BaseModel):
    """Read DTO for a leaderboard row before route rank assignment."""

    model_config = ConfigDict(extra="forbid")

    spec_id: str
    accuracy: float
    total_questions: int
    ran_with_providers: list[str]
    submitted_at: datetime
    submitted_by: str | None
    verified_by_openmined: bool
    url4_expression: str
