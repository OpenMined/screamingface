"""Small immutable values shared by public Report objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

type FailureStage = Literal["candidate", "grading", "aggregation"]


@dataclass(frozen=True, slots=True, init=False)
class Usage:
    """Observed token and monetary accounting for one execution subtree."""

    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    reasoning_tokens: int | None
    cost_usd: Decimal | None

    def __init__(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        cost_usd: Decimal | str | None = None,
    ) -> None:
        values = {
            "input_tokens": _optional_count(input_tokens, "input_tokens"),
            "output_tokens": _optional_count(output_tokens, "output_tokens"),
            "cache_read_tokens": _optional_count(cache_read_tokens, "cache_read_tokens"),
            "cache_creation_tokens": _optional_count(
                cache_creation_tokens, "cache_creation_tokens"
            ),
            "reasoning_tokens": _optional_count(reasoning_tokens, "reasoning_tokens"),
            "cost_usd": _cost(cost_usd),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
            "reasoning_tokens",
        ):
            value = getattr(self, name)
            if value is not None:
                values[name] = value
        if self.cost_usd is not None:
            values["cost_usd"] = str(self.cost_usd)
        return values


@dataclass(frozen=True, slots=True)
class Failure:
    """One typed domain failure retained inside a valid Report."""

    stage: FailureStage
    code: str
    message: str
    retryable: bool
    operation_id: str
    case_id: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in {"candidate", "grading", "aggregation"}:
            raise ValueError("Failure stage must be 'candidate', 'grading', or 'aggregation'")
        for name in ("code", "message", "operation_id"):
            object.__setattr__(
                self,
                name,
                _nonblank(getattr(self, name), f"Failure {name}"),
            )
        if re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", self.code) is None:
            raise ValueError("Failure code must be lowercase snake_case")
        if not isinstance(self.retryable, bool):
            raise TypeError("Failure retryable must be a boolean")
        if self.case_id is not None:
            object.__setattr__(
                self,
                "case_id",
                _nonblank(self.case_id, "Failure case_id"),
            )

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "operation_id": self.operation_id,
        }
        if self.case_id is not None:
            value["case_id"] = self.case_id
        return value


def _optional_count(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Usage {label} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"Usage {label} must be a non-negative integer")
    return value


def _cost(value: Decimal | str | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal | str):
        raise TypeError("Usage cost_usd must be a decimal string or Decimal")
    try:
        selected = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Usage cost_usd must be a finite non-negative decimal") from exc
    if not selected.is_finite() or selected < 0:
        raise ValueError("Usage cost_usd must be a finite non-negative decimal")
    return selected


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _duration(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} duration_ms must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{label} duration_ms must be a non-negative integer")
    return value


def _usage(value: object, label: str) -> Usage:
    if not isinstance(value, Usage):
        raise TypeError(f"{label} usage must be an sf.Usage value")
    return value


__all__: list[str] = []
