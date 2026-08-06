"""Small immutable values shared by public Report objects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from screamingface._immutable_json import freeze_mapping, thaw_mapping

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
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": None if self.cost_usd is None else str(self.cost_usd),
        }


@dataclass(frozen=True, slots=True, init=False)
class Failure:
    """One typed domain failure retained inside a valid Report."""

    stage: FailureStage
    code: str
    message: str
    retryable: bool | None
    operation_id: str | None
    case_id: int | str | None
    metadata: Mapping[str, object]

    def __init__(
        self,
        *,
        stage: FailureStage,
        code: str,
        message: str,
        retryable: bool | None = None,
        operation_id: str | None = None,
        case_id: int | str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if stage not in {"candidate", "grading", "aggregation"}:
            raise ValueError("Failure stage must be 'candidate', 'grading', or 'aggregation'")
        selected_code = _nonblank(code, "Failure code")
        if re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", selected_code) is None:
            raise ValueError("Failure code must be lowercase snake_case")
        values = {
            "stage": stage,
            "code": selected_code,
            "message": _nonblank(message, "Failure message"),
            "retryable": _optional_retryable(retryable),
            "operation_id": _optional_operation_id(operation_id),
            "case_id": _failure_case_id(case_id),
            "metadata": freeze_mapping(metadata or {}, "Failure metadata"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
        }
        if self.retryable is not None:
            value["retryable"] = self.retryable
        if self.operation_id is not None:
            value["operation_id"] = self.operation_id
        if self.case_id is not None:
            value["case_id"] = self.case_id
        if self.metadata:
            value["metadata"] = thaw_mapping(self.metadata)
        return value


def _optional_retryable(value: object) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise TypeError("Failure retryable must be a boolean or None")
    return value


def _optional_operation_id(value: object) -> str | None:
    return None if value is None else _nonblank(value, "Failure operation_id")


def _failure_case_id(value: object) -> int | str | None:
    if isinstance(value, bool):
        raise TypeError("Failure case_id must be a positive integer, string, or None")
    if isinstance(value, int):
        if value < 1:
            raise ValueError("Failure case_id must be a positive integer, string, or None")
        return value
    if isinstance(value, str):
        return _nonblank(value, "Failure case_id")
    if value is None:
        return None
    raise TypeError("Failure case_id must be a positive integer, string, or None")


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
